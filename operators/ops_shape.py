"""Create and edit Kanvas shapes."""

import math
import uuid

import bpy

from ..utils import shape_geometry
from ..utils.kanvas_data import get_settings, unique_item_name
from .kanvas_context import KanvasTreeOnly

_PRESET_KINDS = [kind for kind in shape_geometry.KINDS if kind[0] != 'POLYGON']
ARM_HINT = 'Draw shape: drag on the canvas  |  Shift: square  |  Ctrl: from center  |  Esc: cancel'


def kind_label(kind):
    return next((label for identifier, label, _, _ in shape_geometry.KINDS
                 if identifier == kind), 'Shape')


def new_shape(context, settings, kind, center, width, height, attach=True):
    """Add a shape to the board, select it and make it the active item."""
    from ..properties import set_vertex_records
    for item in settings.images:
        item.is_selected = False
    name = unique_item_name(settings, kind_label(kind))
    item = settings.images.add()
    item.item_id = uuid.uuid4().hex
    item.item_type = 'SHAPE'
    item.name = name
    item.shape_kind = kind
    set_vertex_records(item, shape_geometry.preset_records(kind)
                       or shape_geometry.preset_records('RECTANGLE'))
    item.shape_width = max(shape_geometry.MIN_SIZE, width)
    item.shape_height = max(shape_geometry.MIN_SIZE, height)
    item.location = (center[0], center[1])
    item.text_color = (1.0, 1.0, 1.0)
    item.z_index = max((other.z_index for other in settings.images), default=0) + 1
    item.is_selected = True
    settings.active_image_index = len(settings.images) - 1
    if attach:
        attach_new_shape(context, settings, item)
    return item


def attach_new_shape(context, settings, item):
    """Put a freshly drawn shape into the frame under its center, if there is one."""
    from ..utils.gpu import find_frame_at_location, sync_kanvas_frames, update_frame_bounds
    frame = find_frame_at_location(settings, item.location)
    if frame is None:
        return
    tree = getattr(getattr(context, 'space_data', None), 'edit_tree', None)
    item.parent_frame = frame.frame_node_name
    update_frame_bounds(tree, settings, frame.frame_node_name)
    sync_kanvas_frames(tree, settings)


def normalize_shape(item):
    """Make the shape box fit its vertices again after they were edited.

    The vertices always span the unit box, so the box handles, the bounds used by
    frames and the text position stay in step with the drawn outline.
    """
    from ..properties import suspend_frame_geometry_updates
    from ..utils.arrow_geometry import endpoint
    # The outline before rounding: the corner radius is in canvas units, so fitting the
    # box to the rounded outline would change it again on every fit.
    extent = [unit for unit, _, _ in shape_geometry.plain_curve_units(item)]
    result = shape_geometry.normalized([tuple(v.co) for v in item.shape_vertices], extent)
    if result is None:
        return
    vertices, (cx, cy), (span_x, span_y) = result
    # Arrow ends are stored relative to the box, which is about to change.
    settings = get_settings(bpy.context)
    anchored = [(arrow, side, endpoint(settings, arrow, side))
                for arrow in (settings.arrows if settings else ())
                for side in ('start', 'end')
                if getattr(arrow, side + '_item_id') == item.item_id]
    width, height = shape_geometry.shape_extent(item)
    dx, dy = shape_geometry.rotate((cx * width, cy * height), item.rotation)
    with suspend_frame_geometry_updates():
        item.shape_width = max(shape_geometry.MIN_SIZE, item.shape_width * span_x)
        item.shape_height = max(shape_geometry.MIN_SIZE, item.shape_height * span_y)
        item.location = (item.location[0] + dx, item.location[1] + dy)
        for vertex, (x, y) in zip(item.shape_vertices, vertices):
            vertex.co = (x, y)
            # Handles live in the same box, so they follow the same rescale.
            for name in ('handle_left', 'handle_right'):
                hx, hy = getattr(vertex, name)
                setattr(vertex, name, ((hx - cx) / span_x, (hy - cy) / span_y))
    for arrow, side, position in anchored:
        setattr(arrow, side + '_uv', shape_geometry.uv_at(item, position))
    if item.parent_frame:
        from ..utils.gpu import update_frame_bounds
        update_frame_bounds(None, get_settings(bpy.context), item.parent_frame)


def selected_vertex_indices(item):
    return [index for index, vertex in enumerate(item.shape_vertices) if vertex.select]


def select_shape_vertices(item, indices, extend=False):
    """Select the given vertices; without `extend` every other vertex is deselected."""
    wanted = set(indices)
    for index, vertex in enumerate(item.shape_vertices):
        state = True if index in wanted else (vertex.select if extend else False)
        if vertex.select != state:
            vertex.select = state


def vertices_in_rect(item, corner_a, corner_b):
    """Indices of the vertices whose canvas position lies inside the rectangle."""
    left, right = sorted((corner_a[0], corner_b[0]))
    bottom, top = sorted((corner_a[1], corner_b[1]))
    return [index for index, (x, y) in enumerate(shape_geometry.vertex_points(item))
            if left <= x <= right and bottom <= y <= top]


# --- Bezier handles ---------------------------------------------------------------------

def _third(a, b):
    return a[0] + (b[0] - a[0]) / 3.0, a[1] + (b[1] - a[1]) / 3.0


def _auto_handles(records, index):
    co = records[index][0]
    prev = records[shape_geometry.prev_index(records, index)][0]
    nxt = records[shape_geometry.next_index(records, index)][0]
    dx, dy = (nxt[0] - prev[0]) / 6.0, (nxt[1] - prev[1]) / 6.0
    return (co[0] - dx, co[1] - dy), (co[0] + dx, co[1] + dy)


def _opposite(item, co, keep, other):
    """Unit position of `other` turned to point away from `keep`, keeping its length.

    Measured on the canvas, so the handle keeps the length the user sees.
    """
    c = shape_geometry.unit_to_canvas(item, co)
    k = shape_geometry.unit_to_canvas(item, keep)
    o = shape_geometry.unit_to_canvas(item, other)
    dx, dy = c[0] - k[0], c[1] - k[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return tuple(other)
    reach = math.dist(c, o)
    return shape_geometry.canvas_to_unit(item, (c[0] + dx / length * reach,
                                                c[1] + dy / length * reach))


def _mirror(co, handle):
    """The handle reflected through its vertex (same length, opposite direction).

    A point reflection survives the box scale and rotation, so unit coordinates do.
    """
    return 2.0 * co[0] - handle[0], 2.0 * co[1] - handle[1]


def set_vertex_type(item, indices, kind):
    """Change the vertex type of the given vertices without a visible jump when possible.

    Sharp to Free keeps the straight edges (handles a third of the way to the
    neighbours); Sharp to Aligned or Mirrored and Auto to anything start from the
    automatic handles; Free to Aligned keeps the outgoing handle and lines the other one
    up; to Mirrored, the incoming handle becomes the mirror of the outgoing one.
    Returns True when something changed.
    """
    records = shape_geometry.item_records(item)
    handles = shape_geometry.effective_handles(records, shape_geometry.is_closed(item))
    changes = []
    for index in indices:
        old = records[index][1]
        if old == kind:
            continue
        left = right = None
        co = records[index][0]
        if kind in {'ALIGNED', 'MIRRORED', 'FREE'}:
            if old == 'SHARP' and kind == 'FREE':
                left = _third(co, records[shape_geometry.prev_index(records, index)][0])
                right = _third(co, records[shape_geometry.next_index(records, index)][0])
            elif old == 'SHARP':
                left, right = _auto_handles(records, index)
            elif old == 'AUTO':
                left, right = handles[index]
            elif kind == 'MIRRORED':
                right = handles[index][1]
                left = _mirror(co, right)
            elif kind == 'ALIGNED' and old == 'FREE':
                left, right = handles[index]
                left = _opposite(item, co, right, left)
            else:
                left, right = handles[index]  # Mirrored to Aligned or Free: already fine
        changes.append((index, left, right))
    if not changes:
        return False
    if item.shape_kind != 'POLYGON':
        item.shape_kind = 'POLYGON'  # keeps the current vertices
    for index, left, right in changes:
        vertex = item.shape_vertices[index]
        if left is not None:
            vertex.handle_left, vertex.handle_right = left, right
        vertex.handle_type = kind
    normalize_shape(item)
    return True


def prepare_handle_edit(item, index):
    """Before a handle of this vertex is moved by hand: Sharp becomes Free (both
    handles on the vertex, so the other edge stays straight) and Auto becomes Mirrored
    (keeping its current handles, which are already symmetric)."""
    vertex = item.shape_vertices[index]
    if vertex.handle_type == 'SHARP':
        vertex.handle_left = vertex.handle_right = tuple(vertex.co)
        vertex.handle_type = 'FREE'
    elif vertex.handle_type == 'AUTO':
        left, right = _auto_handles(shape_geometry.item_records(item), index)
        vertex.handle_left, vertex.handle_right = left, right
        vertex.handle_type = 'MIRRORED'


def set_handle(item, index, side, unit):
    """Place one handle; an Aligned vertex turns its other handle to stay in line and
    a Mirrored one also gives it the same length."""
    vertex = item.shape_vertices[index]
    setattr(vertex, 'handle_' + side, unit)
    if vertex.handle_type == 'MIRRORED':
        other = 'handle_right' if side == 'left' else 'handle_left'
        setattr(vertex, other, _mirror(tuple(vertex.co), unit))
    elif vertex.handle_type == 'ALIGNED':
        other = 'handle_right' if side == 'left' else 'handle_left'
        setattr(vertex, other, _opposite(item, tuple(vertex.co), unit, tuple(getattr(vertex, other))))


def bend_base(item, edge):
    """Control points an edge bend starts from; a straight edge gets handles at thirds."""
    records = shape_geometry.item_records(item)
    controls = shape_geometry.segment_controls(
        records, shape_geometry.effective_handles(records, shape_geometry.is_closed(item)), edge)
    if shape_geometry.is_straight(controls):
        p0, _, _, p3 = controls
        controls = (p0, _third(p0, p3), _third(p3, p0), p3)
    return controls


def bend_edge(item, edge, t, base, delta):
    """Pull the curve point at t of an edge by `delta` (unit box), from `base` controls."""
    first, second = shape_geometry.bend_offsets(t, delta)
    end = shape_geometry.next_index(shape_geometry.item_records(item), edge)
    set_handle(item, edge, 'right', (base[1][0] + first[0], base[1][1] + first[1]))
    set_handle(item, end, 'left', (base[2][0] + second[0], base[2][1] + second[1]))


def insert_shape_vertex(item, edge, t):
    """Add a vertex on an edge at curve parameter t; a curved edge keeps its shape.

    Returns the index of the new vertex.
    """
    records = shape_geometry.item_records(item)
    handles = shape_geometry.effective_handles(records, shape_geometry.is_closed(item))
    controls = shape_geometry.segment_controls(records, handles, edge)
    end = shape_geometry.next_index(records, edge)
    contour = shape_geometry.record_contour(records[edge])
    if item.shape_kind != 'POLYGON':
        item.shape_kind = 'POLYGON'  # keeps the current vertices
    if shape_geometry.is_straight(controls):
        p0, _, _, p3 = controls
        new = ((p0[0] + (p3[0] - p0[0]) * t, p0[1] + (p3[1] - p0[1]) * t), 'SHARP', (0.0, 0.0), (0.0, 0.0))
    else:
        first, second = shape_geometry.split_cubic(controls, t)
        # The neighbours keep their other handle; Auto ones are frozen as Aligned first,
        # since their automatic handles would change with the new neighbour, and
        # Mirrored ones become Aligned, since the split shortens one handle.
        for index in (edge, end):
            vertex = item.shape_vertices[index]
            if vertex.handle_type == 'AUTO':
                vertex.handle_left, vertex.handle_right = handles[index]
                vertex.handle_type = 'ALIGNED'
            elif vertex.handle_type == 'MIRRORED':
                vertex.handle_type = 'ALIGNED'
        if item.shape_vertices[edge].handle_type != 'SHARP':
            item.shape_vertices[edge].handle_right = first[1]
        if item.shape_vertices[end].handle_type != 'SHARP':
            item.shape_vertices[end].handle_left = second[2]
        new = (first[3], 'ALIGNED', first[2], second[1])
    vertex = item.shape_vertices.add()
    vertex.co, vertex.handle_type, vertex.handle_left, vertex.handle_right = new
    vertex.contour = contour
    # Right after `edge`: also correct for the closing edge of a contour, whose new
    # vertex comes after the contour's last one.
    index = edge + 1
    item.shape_vertices.move(len(item.shape_vertices) - 1, index)
    return index


def add_vertex_at(item, point):
    """Add a vertex at a canvas point away from the outline (Ctrl+click on empty space).

    With one vertex selected, the new vertex comes right after it, so the outline grows
    towards the click; at the end of an open path it extends the path from that end.
    Otherwise it goes into the edge nearest to the click (or extends an open path when
    an end is nearest). The new vertex is a Sharp corner. Returns its index.
    """
    records = shape_geometry.item_records(item)
    closed = shape_geometry.is_closed(item)
    selected = selected_vertex_indices(item)
    ranges = shape_geometry.contour_ranges(records)

    def contour_of(index):
        return next((start, stop) for start, stop in ranges if start <= index < stop)

    if len(selected) == 1:
        anchor = selected[0]
        start, _ = contour_of(anchor)
        index = anchor if (not closed and anchor == start) else anchor + 1
    else:
        units = shape_geometry.curve_units(item)
        nearest = shape_geometry.nearest_outline_edge(item, point)
        if nearest is None:
            anchor, index = len(records) - 1, len(records)
        else:
            anchor = units[nearest[0]][1]
            index = anchor + 1
            if not closed:
                start, stop = contour_of(anchor)
                ends = [(math.dist(point, shape_geometry.unit_to_canvas(item, records[i][0])), i)
                        for i in (start, stop - 1)]
                distance, end = min(ends)
                if distance <= nearest[2] + 1e-9:
                    anchor = end
                    index = end if end == start else end + 1
    if item.shape_kind != 'POLYGON':
        item.shape_kind = 'POLYGON'  # keeps the current vertices
    unit = shape_geometry.canvas_to_unit(item, point)
    vertex = item.shape_vertices.add()
    vertex.co = vertex.handle_left = vertex.handle_right = unit
    vertex.handle_type = 'SHARP'
    vertex.contour = shape_geometry.record_contour(records[anchor]) if records else 0
    item.shape_vertices.move(len(item.shape_vertices) - 1, index)
    return index


def _outline_arrow_ends(settings, item):
    """(arrow, side) of every arrow end that sits on the shape's outline, not inside it."""
    from ..utils.arrow_geometry import endpoint
    if len(shape_geometry.outline(item)) < shape_geometry.min_vertices(item):
        return []
    tolerance = max(1e-4, 1e-3 * max(shape_geometry.shape_extent(item)))
    ends = []
    for arrow in settings.arrows:
        for side in ('start', 'end'):
            if getattr(arrow, side + '_item_id') != item.item_id:
                continue
            nearest = shape_geometry.nearest_outline_edge(item, endpoint(settings, arrow, side))
            if nearest is not None and nearest[2] <= tolerance:
                ends.append((arrow, side))
    return ends


def delete_shape_vertices(item, indices):
    """Remove vertices from a shape. Returns '' when done, or why nothing was removed.

    In an outline, removing a vertex joins its two neighbours, so this is also the
    "dissolve" of a mesh editor. A contour left with fewer than three vertices goes
    away as a whole (a hole closes), as long as another contour remains. Arrow ends
    that sat on the outline stay on it: an end on a removed vertex drops to the nearest
    point of the new outline. Ends placed inside the shape keep their position.
    """
    from ..utils.arrow_geometry import endpoint
    chosen = {i for i in indices if 0 <= i < len(item.shape_vertices)}
    if not chosen:
        return 'Select vertices to delete'
    for start, stop in shape_geometry.item_contour_ranges(item):
        left = [i for i in range(start, stop) if i not in chosen]
        if len(left) < shape_geometry.min_vertices(item):
            chosen.update(range(start, stop))
    if len(chosen) >= len(item.shape_vertices):
        return f'A shape needs at least {shape_geometry.min_vertices(item)} vertices'
    indices = sorted(chosen, reverse=True)
    settings = get_settings(bpy.context)
    on_outline = _outline_arrow_ends(settings, item) if settings else []
    if item.shape_kind != 'POLYGON':
        item.shape_kind = 'POLYGON'  # keeps the current vertices
    for index in indices:
        item.shape_vertices.remove(index)
    normalize_shape(item)
    for arrow, side in on_outline:
        hit = shape_geometry.outline_attach(item, endpoint(settings, arrow, side), float('inf'))
        if hit is not None:
            setattr(arrow, side + '_uv', hit[0])
    return ''


class KANVAS_OT_SetVertexType(KanvasTreeOnly, bpy.types.Operator):
    """Set how the outline passes through the selected vertices."""
    bl_idname = 'kanvas.set_vertex_type'
    bl_label = 'Set Vertex Type'
    bl_description = ('Set how the outline passes through the selected vertices: a sharp corner, '
                      'an automatic curve, or a curve with Aligned or Free handles')
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.EnumProperty(  # type: ignore
        name='Type',
        items=[(identifier, label, description, icon, number)
               for number, (identifier, label, description, icon)
               in enumerate(shape_geometry.HANDLE_TYPES)],
        default='SHARP',
    )

    @classmethod
    def description(cls, context, properties):
        return next(description for identifier, _, description, _
                    in shape_geometry.HANDLE_TYPES if identifier == properties.kind)

    @classmethod
    def poll(cls, context):
        return KANVAS_OT_DeleteShapeVertices.poll(context)

    def execute(self, context):
        from ..utils.gpu.gpu_shape import vertex_edit_shape
        item = vertex_edit_shape(get_settings(context))
        indices = selected_vertex_indices(item)
        if not indices:
            self.report({'INFO'}, 'Select vertices first')
            return {'CANCELLED'}
        if not set_vertex_type(item, indices, self.kind):
            return {'CANCELLED'}
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_MT_vertex_type(bpy.types.Menu):
    bl_label = 'Vertex Type'
    bl_idname = 'KANVAS_MT_vertex_type'

    def draw(self, context):
        layout = self.layout
        for identifier, label, _, icon in shape_geometry.HANDLE_TYPES:
            layout.operator('kanvas.set_vertex_type', text=label, icon=icon).kind = identifier


class KANVAS_OT_DeleteShapeVertices(KanvasTreeOnly, bpy.types.Operator):
    """Delete the selected vertices of the shape in Edit Vertices."""
    bl_idname = 'kanvas.delete_shape_vertices'
    bl_label = 'Delete Vertices'
    bl_description = ('Delete the selected vertices of the shape being edited. Its neighbours are '
                      'joined, and a shape keeps at least three vertices')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils.gpu.gpu_shape import vertex_edit_shape
        settings = get_settings(context) if KanvasTreeOnly.poll(context) else None
        return settings is not None and vertex_edit_shape(settings) is not None

    def execute(self, context):
        from ..utils.gpu.gpu_shape import vertex_edit_shape
        item = vertex_edit_shape(get_settings(context))
        message = delete_shape_vertices(item, selected_vertex_indices(item))
        if message:
            self.report({'INFO'}, message)
            return {'CANCELLED'}
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


# --- compound shapes ---------------------------------------------------------------------

def renumber_contours(item):
    """Number the contours 0, 1, 2... in order, so two contours never share a number."""
    for number, (start, stop) in enumerate(shape_geometry.item_contour_ranges(item)):
        for index in range(start, stop):
            if item.shape_vertices[index].contour != number:
                item.shape_vertices[index].contour = number


def _canvas_records(item):
    """The shape's vertex records with every point on the canvas."""
    def canvas(unit):
        return shape_geometry.unit_to_canvas(item, unit)
    return [(canvas(co), kind, canvas(left), canvas(right), contour)
            for co, kind, left, right, contour in shape_geometry.item_records(item)]


def _shape_arrow_ends(settings, item_ids):
    """(arrow, side, canvas point) of every arrow end attached to one of the items."""
    from ..utils.arrow_geometry import endpoint
    return [(arrow, side, endpoint(settings, arrow, side))
            for arrow in settings.arrows for side in ('start', 'end')
            if getattr(arrow, side + '_item_id') in item_ids]


def _remove_items(context, settings, item_ids):
    """Take items off the board by id, updating the frames that held them."""
    frames = set()
    for item_id in item_ids:
        index = next((i for i, other in enumerate(settings.images)
                      if other.item_id == item_id), -1)
        if index < 0:
            continue
        if settings.images[index].parent_frame:
            frames.add(settings.images[index].parent_frame)
        settings.images.remove(index)
    if frames:
        from ..utils.gpu import sync_kanvas_frames, update_frame_bounds
        tree = getattr(getattr(context, 'space_data', None), 'edit_tree', None)
        for name in frames:
            update_frame_bounds(tree, settings, name)
        sync_kanvas_frames(tree, settings)


def combine_shapes(context, settings, shapes, base=None):
    """Join shapes into one shape with every contour; where they overlap, a hole opens
    (even-odd fill). `base` (default: the first shape) keeps its name, look, text and
    place in the stack; the others are removed. Arrows attached to any of them stay
    where they are, attached to the result. Returns the combined shape.
    """
    from ..properties import set_vertex_records
    base = base or shapes[0]
    base_id = base.item_id
    ids = [shape.item_id for shape in shapes]
    others = [item_id for item_id in ids if item_id != base_id]
    arrows = _shape_arrow_ends(settings, set(ids))
    records = []
    contour = 0
    for shape in [base] + [shape for shape in shapes if shape.item_id != base_id]:
        canvas = _canvas_records(shape)
        for start, stop in shape_geometry.item_contour_ranges(shape):
            records.extend((co, kind, left, right, contour)
                           for co, kind, left, right, _ in canvas[start:stop])
            contour += 1

    def unit(point):
        return shape_geometry.canvas_to_unit(base, point)

    base.shape_kind = 'POLYGON'  # keeps the current vertices
    set_vertex_records(base, [(unit(co), kind, unit(left), unit(right), number)
                              for co, kind, left, right, number in records])
    _remove_items(context, settings, others)
    base = next(item for item in settings.images if item.item_id == base_id)
    for arrow, side, point in arrows:
        setattr(arrow, side + '_item_id', base_id)
        setattr(arrow, side + '_uv', shape_geometry.uv_at(base, point))
    normalize_shape(base)
    for item in settings.images:
        item.is_selected = item.item_id == base_id
    settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                       if item.item_id == base_id)
    return base


def separate_contours(context, settings, item):
    """Give every contour of a shape a shape of its own, with the same look.

    The first contour stays in the shape; the new shapes sit right above it. Arrows
    stay attached to the contour they touch, or to the original shape. Returns the
    shapes, the original first.
    """
    from ..properties import set_vertex_records
    from .ops_image import KANVAS_OT_DuplicateImage
    ranges = shape_geometry.item_contour_ranges(item)
    if len(ranges) < 2:
        return [item]
    item_id = item.item_id
    records = _canvas_records(item)
    arrows = _shape_arrow_ends(settings, {item_id})
    pieces = [records[start:stop] for start, stop in ranges]
    ids = [item_id]
    for _ in pieces[1:]:
        ids.append(KANVAS_OT_DuplicateImage._duplicate(None, context, settings, item_id))
    shapes = []
    for shape_id, piece in zip(ids, pieces):
        shape = next(other for other in settings.images if other.item_id == shape_id)
        shape.shape_kind = 'POLYGON'

        def unit(point, shape=shape):
            return shape_geometry.canvas_to_unit(shape, point)

        set_vertex_records(shape, [(unit(co), kind, unit(left), unit(right), 0)
                                   for co, kind, left, right, _ in piece])
        normalize_shape(shape)
        shapes.append(shape_id)
    original = next(other for other in settings.images if other.item_id == item_id)
    base_name = original.name
    for number, shape_id in enumerate(ids[1:], start=2):
        shape = next(other for other in settings.images if other.item_id == shape_id)
        shape.name = unique_item_name(settings, f'{base_name} {number}')
        shape.text_lines.clear()  # the text stays on the original shape only
    for arrow, side, point in arrows:
        best = None
        for shape_id in ids:
            shape = next(other for other in settings.images if other.item_id == shape_id)
            hit = shape_geometry.nearest_outline_edge(shape, point)
            inside = shape_geometry.contains(shape, point)
            distance = 0.0 if inside else (hit[2] if hit else float('inf'))
            if best is None or distance < best[0]:
                best = (distance, shape)
        setattr(arrow, side + '_item_id', best[1].item_id)
        setattr(arrow, side + '_uv', shape_geometry.uv_at(best[1], point))
    wanted = set(ids)
    for other in settings.images:
        other.is_selected = other.item_id in wanted
    settings.active_image_index = next(i for i, other in enumerate(settings.images)
                                       if other.item_id == item_id)
    return [next(other for other in settings.images if other.item_id == shape_id)
            for shape_id in ids]


def _editable_shapes(settings):
    return [item for item in settings.images
            if item.item_type == 'SHAPE' and item.is_selected and item.show_in_editor
            and not item.is_locked]


class KANVAS_OT_CombineShapes(KanvasTreeOnly, bpy.types.Operator):
    """Join the selected shapes into one shape; where they overlap, a hole opens."""
    bl_idname = 'kanvas.combine_shapes'
    bl_label = 'Combine Shapes'
    bl_description = ('Join the selected shapes into one shape with all their outlines. Where '
                      'outlines overlap a hole opens, so a shape on top of another cuts it. '
                      'The active shape keeps its look and text')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return settings is not None and len(_editable_shapes(settings)) >= 2

    def execute(self, context):
        settings = get_settings(context)
        shapes = _editable_shapes(settings)
        if len({shape_geometry.is_closed(shape) for shape in shapes}) > 1:
            self.report({'WARNING'}, 'Open paths and closed shapes cannot be combined: '
                                     'close or open them first')
            return {'CANCELLED'}
        active = active_shape(settings)
        if active is None or not any(s.item_id == active.item_id for s in shapes):
            active = selection_ordered(settings, shapes)[0]
        result = combine_shapes(context, settings, shapes, active)
        self.report({'INFO'}, f'Combined {len(shapes)} shapes into {result.name}')
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_SeparateContours(KanvasTreeOnly, bpy.types.Operator):
    """Give every contour of the selected shapes a shape of its own."""
    bl_idname = 'kanvas.separate_contours'
    bl_label = 'Separate Contours'
    bl_description = ('Split each selected shape with several contours (holes included) into '
                      'one shape per contour, with the same look')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return settings is not None and any(
            len(shape_geometry.item_contour_ranges(item)) > 1
            for item in _editable_shapes(settings))

    def execute(self, context):
        settings = get_settings(context)
        ids = [item.item_id for item in _editable_shapes(settings)
               if len(shape_geometry.item_contour_ranges(item)) > 1]
        created = []
        for item_id in ids:
            item = next(other for other in settings.images if other.item_id == item_id)
            created.extend(shape.item_id for shape in separate_contours(context, settings, item))
        wanted = set(created)
        for other in settings.images:
            other.is_selected = other.item_id in wanted
        self.report({'INFO'}, f'Separated into {len(created)} shapes')
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


# --- vertex tools: contours, flip, reverse, position -------------------------------------

def contour_indices(item, indices):
    """Every vertex index of the contours that hold any of `indices`."""
    wanted = set(indices)
    return [i for start, stop in shape_geometry.item_contour_ranges(item)
            if any(start <= j < stop for j in wanted) for i in range(start, stop)]


def contour_at(item, point, radius):
    """Vertex indices of the contour whose vertex or edge is near a canvas point, or []."""
    vertex = shape_geometry.hit_vertex(item, point, radius)
    if vertex is None:
        edge = shape_geometry.hit_edge(item, point, radius)
        vertex = edge[0] if edge is not None else None
    return [] if vertex is None else contour_indices(item, [vertex])


def flip_vertices(item, indices, axis):
    """Mirror vertices left to right ('X') or top to bottom ('Y'), in the shape's own
    axes, with their handles. A whole shape is mirrored across the middle of its box,
    and arrow ends attached to it follow; some vertices are mirrored across the middle
    of their own bounds. Returns True when something changed.
    """
    indices = sorted(set(indices))
    if not indices:
        return False
    whole = len(indices) == len(item.shape_vertices)
    k = 0 if axis == 'X' else 1
    values = [item.shape_vertices[i].co[k] for i in indices]
    middle = 0.0 if whole else (max(values) + min(values)) * 0.5
    handles = shape_geometry.item_handles(item)

    def mirrored(point):
        point = list(point)
        point[k] = 2.0 * middle - point[k]
        return tuple(point)

    if item.shape_kind != 'POLYGON':
        item.shape_kind = 'POLYGON'  # keeps the current vertices
    for i in indices:
        vertex = item.shape_vertices[i]
        left, right = handles[i]
        vertex.co = mirrored(vertex.co)
        if vertex.handle_type != 'AUTO':
            vertex.handle_left, vertex.handle_right = mirrored(left), mirrored(right)
    settings = get_settings(bpy.context)
    if whole and settings is not None:
        for arrow in settings.arrows:
            for side in ('start', 'end'):
                if getattr(arrow, side + '_item_id') == item.item_id:
                    u, v = getattr(arrow, side + '_uv')
                    setattr(arrow, side + '_uv', (1.0 - u, v) if k == 0 else (u, 1.0 - v))
    normalize_shape(item)
    return True


def reverse_contours(item, indices):
    """Run the contours that hold `indices` the other way round (which end of an open
    path comes first, and the winding SVG's nonzero rule looks at). The outline does
    not change. Returns True when something changed."""
    from ..properties import set_vertex_records
    records = shape_geometry.item_records(item)
    chosen = set(contour_indices(item, indices))
    if not chosen:
        return False
    selection = {i for i in range(len(records)) if item.shape_vertices[i].select}
    result, selected = [], []
    for start, stop in shape_geometry.contour_ranges(records):
        order = list(range(start, stop))
        if start in chosen:
            order.reverse()
        for i in order:
            co, kind, left, right, contour = records[i]
            if start in chosen:
                left, right = right, left
            result.append((co, kind, left, right, contour))
            selected.append(i in selection)
    set_vertex_records(item, result)
    for vertex, state in zip(item.shape_vertices, selected):
        vertex.select = state
    return True


def selection_center(item, indices):
    """Canvas middle of the bounds of the given vertices."""
    points = [shape_geometry.unit_to_canvas(item, item.shape_vertices[i].co) for i in indices]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return ((max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5)


def move_vertices(item, indices, delta):
    """Move vertices (and their stored handles) by a canvas offset."""
    def moved(unit):
        x, y = shape_geometry.unit_to_canvas(item, unit)
        return shape_geometry.canvas_to_unit(item, (x + delta[0], y + delta[1]))

    for i in indices:
        vertex = item.shape_vertices[i]
        vertex.co = moved(tuple(vertex.co))
        vertex.handle_left = moved(tuple(vertex.handle_left))
        vertex.handle_right = moved(tuple(vertex.handle_right))


def snap_to_shape_vertices(settings, item, point, radius):
    """The vertex of another visible shape nearest to a canvas point, within `radius`."""
    best, best_distance = None, radius
    for other in settings.images:
        if (other.item_type != 'SHAPE' or other.item_id == item.item_id
                or not other.show_in_editor):
            continue
        left, bottom, right, top = shape_geometry.bounds(other)
        if not (left - radius <= point[0] <= right + radius
                and bottom - radius <= point[1] <= top + radius):
            continue
        for candidate in shape_geometry.vertex_points(other):
            distance = math.dist(candidate, point)
            if distance <= best_distance:
                best, best_distance = candidate, distance
    return best


class KANVAS_OT_SelectContour(KanvasTreeOnly, bpy.types.Operator):
    """Select every vertex of a contour."""
    bl_idname = 'kanvas.select_contour'
    bl_label = 'Select Contour'
    bl_description = ('Select every vertex of the contour under the pointer, or of the contours '
                      'that hold the selected vertices (L in Edit Vertices). Shift adds to the '
                      'selection')
    bl_options = {'REGISTER', 'UNDO'}

    extend: bpy.props.BoolProperty(name='Extend', default=False, options={'SKIP_SAVE'})  # type: ignore
    location: bpy.props.FloatVectorProperty(size=2, options={'SKIP_SAVE', 'HIDDEN'})  # type: ignore
    use_location: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE', 'HIDDEN'})  # type: ignore

    @classmethod
    def poll(cls, context):
        return KANVAS_OT_DeleteShapeVertices.poll(context)

    def invoke(self, context, event):
        region = context.region
        if region is not None and region.type == 'WINDOW':
            self.location = region.view2d.region_to_view(event.mouse_region_x,
                                                         event.mouse_region_y)
            self.use_location = True
        self.extend = self.extend or event.shift
        return self.execute(context)

    def execute(self, context):
        from ..utils.gpu.gpu_shape import VERTEX_HIT_PIXELS, vertex_edit_shape
        from .ops_arrow import _pixel_size
        item = vertex_edit_shape(get_settings(context))
        indices = []
        if self.use_location:
            radius = VERTEX_HIT_PIXELS * (_pixel_size(context) if context.region else 1.0)
            indices = contour_at(item, tuple(self.location), radius)
        if not indices:
            indices = contour_indices(item, selected_vertex_indices(item))
        if not indices:
            self.report({'INFO'}, 'Point at a contour or select one of its vertices')
            return {'CANCELLED'}
        select_shape_vertices(item, indices, extend=self.extend)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_ReverseContour(KanvasTreeOnly, bpy.types.Operator):
    """Run the selected contours the other way round."""
    bl_idname = 'kanvas.reverse_contour'
    bl_label = 'Reverse Direction'
    bl_description = ('Run the contours of the selected vertices the other way round: the other '
                      'end of an open path comes first. The outline does not change')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return KANVAS_OT_DeleteShapeVertices.poll(context)

    def execute(self, context):
        from ..utils.gpu.gpu_shape import vertex_edit_shape
        item = vertex_edit_shape(get_settings(context))
        if not reverse_contours(item, selected_vertex_indices(item)):
            self.report({'INFO'}, 'Select vertices of the contour first')
            return {'CANCELLED'}
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_FlipShape(KanvasTreeOnly, bpy.types.Operator):
    """Mirror shapes, or the selected vertices in Edit Vertices."""
    bl_idname = 'kanvas.flip_shape'
    bl_label = 'Flip'
    bl_description = ('Mirror the selected shapes left to right or top to bottom. In Edit '
                      'Vertices, mirror only the selected vertices around their middle')
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(  # type: ignore
        name='Axis',
        items=[('X', 'Horizontal', 'Mirror left to right'),
               ('Y', 'Vertical', 'Mirror top to bottom')],
        default='X',
    )

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return settings is not None and bool(_editable_shapes(settings))

    def execute(self, context):
        from ..utils.gpu.gpu_shape import vertex_edit_shape
        settings = get_settings(context)
        editing = vertex_edit_shape(settings)
        if editing is not None:
            indices = selected_vertex_indices(editing)
            if not indices:
                self.report({'INFO'}, 'Select vertices to flip')
                return {'CANCELLED'}
            flip_vertices(editing, indices, self.axis)
        else:
            ids = [item.item_id for item in _editable_shapes(settings)]
            for item_id in ids:
                item = next(other for other in settings.images if other.item_id == item_id)
                flip_vertices(item, range(len(item.shape_vertices)), self.axis)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


# --- shape tools: simplify, offset, line to shape ---------------------------------------

def _simplify_ring(points, tolerance, closed):
    """Douglas-Peucker on a ring of canvas points; a closed ring keeps at least three."""
    if len(points) <= (3 if closed else 2):
        return list(points)

    def reduce(chain):
        keep = [False] * len(chain)
        keep[0] = keep[-1] = True
        stack = [(0, len(chain) - 1)]
        while stack:
            first, last = stack.pop()
            worst, index = -1.0, None
            for i in range(first + 1, last):
                distance, _ = shape_geometry.segment_distance(chain[i], chain[first], chain[last])
                if distance > worst:
                    worst, index = distance, i
            if index is not None and worst > tolerance:
                keep[index] = True
                stack.extend(((first, index), (index, last)))
        return [p for p, k in zip(chain, keep) if k]

    if not closed:
        return reduce(points)
    # Split a closed ring at the point farthest from its first point.
    far = max(range(len(points)), key=lambda i: math.dist(points[0], points[i]))
    result = reduce(points[:far + 1])[:-1] + reduce(points[far:] + points[:1])[:-1]
    if len(result) < 3:
        result = [points[0], points[len(points) // 3], points[2 * len(points) // 3]]
    return result


def _set_canvas_rings(item, rings):
    """Give a shape Sharp vertices at canvas points, one contour per ring."""
    from ..properties import set_vertex_records
    if item.shape_kind != 'POLYGON':
        item.shape_kind = 'POLYGON'

    def unit(point):
        return shape_geometry.canvas_to_unit(item, point)

    set_vertex_records(item, [(unit(p), 'SHARP', unit(p), unit(p), number)
                              for number, ring in enumerate(rings) for p in ring])
    normalize_shape(item)


def simplify_shape(item, tolerance, smooth=False):
    """Fewer vertices: the outline (curves flattened) keeps only the vertices needed to
    stay within `tolerance` canvas units of it. `smooth` then makes them Auto, so the
    result is a smooth curve through them. Returns (vertices before, after)."""
    before = len(item.shape_vertices)
    closed = shape_geometry.is_closed(item)
    rings = [_simplify_ring(list(ring), tolerance, closed) for ring in shape_geometry.outlines(item)
             if len(ring) >= shape_geometry.min_vertices(item)]
    if not rings:
        return before, before
    _set_canvas_rings(item, rings)
    if smooth:
        for vertex in item.shape_vertices:
            vertex.handle_type = 'AUTO'
        if not closed:
            # The two ends of an open path stay corners.
            for start, stop in shape_geometry.item_contour_ranges(item):
                item.shape_vertices[start].handle_type = 'SHARP'
                item.shape_vertices[stop - 1].handle_type = 'SHARP'
        normalize_shape(item)
    return before, len(item.shape_vertices)


def offset_rings(item, distance):
    """Every contour moved `distance` canvas units outwards (negative: inwards), holes
    included (their outside is inside the shape). Corners are mitered."""
    from ..utils.stroke_geometry import offset_contour
    rings = [list(ring) for ring in shape_geometry.outlines(item)
             if len(ring) >= shape_geometry.MIN_VERTICES]
    depths = shape_geometry.contour_depths(rings) if len(rings) > 1 else [0] * len(rings)
    result = []
    for ring, depth in zip(rings, depths):
        filled_on_left = (shape_geometry.signed_area(ring) > 0) == (depth % 2 == 0)
        result.append(offset_contour(ring, -distance if filled_on_left else distance))
    return result


def stroke_rings(item):
    """Canvas contours of the area the shape's line covers, as a filled shape would draw
    it: a band (two contours) along each closed contour, or one outline around an
    open path with its ends. Joins are mitered; dashes are not kept."""
    from ..utils import stroke_geometry
    half = item.shape_line_width * 0.5
    closed = shape_geometry.is_closed(item)
    rings = []
    for points, _edges in shape_geometry.stroke_paths(item):
        if closed and len(points) >= 3:
            rings.append(stroke_geometry.offset_contour(points, half))
            rings.append(stroke_geometry.offset_contour(points, -half))
        elif len(points) >= 2:
            if item.shape_line_cap == 'ROUND':
                rings.append(_round_ends(points, half))
                continue
            left = stroke_geometry.offset_contour(points, half, closed=False)
            right = stroke_geometry.offset_contour(points, -half, closed=False)
            if item.shape_line_cap == 'SQUARE':
                left, right = _pushed_ends(left, half), _pushed_ends(right, half)
            rings.append(list(left) + list(reversed(right)))
    return rings


def _pushed_ends(chain, distance):
    """A polyline with both end points moved `distance` further out along it."""
    def push(point, toward):
        dx, dy = point[0] - toward[0], point[1] - toward[1]
        length = math.hypot(dx, dy) or 1.0
        return point[0] + dx / length * distance, point[1] + dy / length * distance

    return [push(chain[0], chain[1])] + list(chain[1:-1]) + [push(chain[-1], chain[-2])]


def _round_ends(points, half, steps=8):
    """An open path's outline with half circles at both ends."""
    from ..utils.stroke_geometry import offset_contour
    left = offset_contour(points, half, closed=False)
    right = offset_contour(points, -half, closed=False)

    def arc(center, start_angle):
        return [(center[0] + half * math.cos(start_angle - math.pi * k / steps),
                 center[1] + half * math.sin(start_angle - math.pi * k / steps))
                for k in range(1, steps)]

    def heading(a, b):
        return math.atan2(b[1] - a[1], b[0] - a[0])

    end_angle = heading(points[-2], points[-1]) + math.pi * 0.5
    start_angle = heading(points[1], points[0]) + math.pi * 0.5
    return (list(left) + arc(points[-1], end_angle) + list(reversed(right))
            + arc(points[0], start_angle))


def _new_shape_like(context, settings, source_id, name):
    """A copy of a shape (look, frame, z order) to receive new contours."""
    from .ops_image import KANVAS_OT_DuplicateImage
    new_id = KANVAS_OT_DuplicateImage._duplicate(None, context, settings, source_id)
    item = next(other for other in settings.images if other.item_id == new_id)
    item.name = unique_item_name(settings, name)
    item.text_lines.clear()
    item.shape_corner_radius = 0.0
    item.shape_closed = True
    return item


class KANVAS_OT_SimplifyShape(KanvasTreeOnly, bpy.types.Operator):
    """Remove the vertices the outline does not need."""
    bl_idname = 'kanvas.simplify_shape'
    bl_label = 'Simplify Shape'
    bl_description = ('Keep only the vertices needed to stay close to the outline, for shapes '
                      'with too many vertices (traced or imported). Smooth turns the result '
                      'into a smooth curve')
    bl_options = {'REGISTER', 'UNDO'}

    tolerance: bpy.props.FloatProperty(  # type: ignore
        name='Tolerance', default=2.0, min=0.01, soft_max=50.0,
        description='How far, in canvas units, the new outline may stray from the old one')
    smooth: bpy.props.BoolProperty(  # type: ignore
        name='Smooth', default=False,
        description='Make the remaining vertices Auto, for a smooth curve through them')

    @classmethod
    def poll(cls, context):
        return KANVAS_OT_FlipShape.poll(context)

    def execute(self, context):
        settings = get_settings(context)
        ids = [item.item_id for item in _editable_shapes(settings)]
        before = after = 0
        for item_id in ids:
            item = next(other for other in settings.images if other.item_id == item_id)
            old, new = simplify_shape(item, self.tolerance, self.smooth)
            before, after = before + old, after + new
        self.report({'INFO'}, f'Vertices: {before} -> {after}')
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_OffsetShape(KanvasTreeOnly, bpy.types.Operator):
    """Add a shape whose outline runs at a distance from the selected one."""
    bl_idname = 'kanvas.offset_shape'
    bl_label = 'Offset Outline'
    bl_description = ('Add a copy of each selected shape with its outline moved outwards (or '
                      'inwards, with a negative distance), holes included. Corners stay sharp; '
                      'curves become many short edges')
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(  # type: ignore
        name='Distance', default=10.0, soft_min=-100.0, soft_max=100.0,
        description='Canvas units outwards; negative moves the outline inwards')
    replace: bpy.props.BoolProperty(  # type: ignore
        name='Replace', default=False,
        description='Change the selected shapes instead of adding copies')

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return settings is not None and any(shape_geometry.is_closed(item)
                                            for item in _editable_shapes(settings))

    def execute(self, context):
        settings = get_settings(context)
        ids = [item.item_id for item in _editable_shapes(settings) if shape_geometry.is_closed(item)]
        created = []
        for item_id in ids:
            source = next(other for other in settings.images if other.item_id == item_id)
            rings = offset_rings(source, self.distance)
            target = source if self.replace else _new_shape_like(
                context, settings, item_id, f'{source.name} Offset')
            created.append(target.item_id)
            target.shape_corner_radius = 0.0
            _set_canvas_rings(target, rings)
        wanted = set(created)
        for other in settings.images:
            other.is_selected = other.item_id in wanted
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_LineToShape(KanvasTreeOnly, bpy.types.Operator):
    """Turn the line of the selected shapes into filled shapes."""
    bl_idname = 'kanvas.line_to_shape'
    bl_label = 'Line to Shape'
    bl_description = ('Turn the line of each selected shape into a filled shape of the same '
                      'size and color, which can then be edited or combined like any shape. '
                      'A shape with a fill keeps it without a line; a line alone is replaced')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return settings is not None and any(item.shape_show_outline
                                            for item in _editable_shapes(settings))

    def execute(self, context):
        settings = get_settings(context)
        ids = [item.item_id for item in _editable_shapes(settings) if item.shape_show_outline]
        created, removed = [], []
        for item_id in ids:
            source = next(other for other in settings.images if other.item_id == item_id)
            rings = stroke_rings(source)
            if not rings:
                continue
            keeps_fill = source.shape_show_fill and shape_geometry.is_closed(source)
            target = _new_shape_like(context, settings, item_id, f'{source.name} Line')
            target.shape_fill_color = tuple(target.shape_line_color)
            target.shape_fill_opacity = 1.0
            target.shape_show_fill = True
            target.shape_show_outline = False
            target.shape_line_align = 'CENTER'
            _set_canvas_rings(target, rings)
            created.append(target.item_id)
            source = next(other for other in settings.images if other.item_id == item_id)
            if keeps_fill:
                source.shape_show_outline = False
            else:
                removed.append(item_id)
        if removed:
            from ..utils.arrow_geometry import detach_item_anchors
            for item_id in removed:
                detach_item_anchors(settings, item_id)
            _remove_items(context, settings, removed)
        wanted = set(created)
        for other in settings.images:
            other.is_selected = other.item_id in wanted
        settings.active_image_index = next(
            (i for i, other in enumerate(settings.images) if other.item_id in wanted), -1)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_MT_shape_tools(bpy.types.Menu):
    bl_label = 'Shape Tools'
    bl_idname = 'KANVAS_MT_shape_tools'

    def draw(self, context):
        layout = self.layout
        layout.operator('kanvas.boolean_shapes', text='Union', icon='SELECT_EXTEND').operation = 'UNION'
        layout.operator('kanvas.boolean_shapes', text='Difference (first selected minus the rest)',
                        icon='SELECT_SUBTRACT').operation = 'DIFFERENCE'
        layout.operator('kanvas.boolean_shapes', text='Intersection',
                        icon='SELECT_INTERSECT').operation = 'INTERSECT'
        layout.operator('kanvas.boolean_shapes', text='Exclusion',
                        icon='SELECT_DIFFERENCE').operation = 'EXCLUDE'
        layout.separator()
        layout.operator('kanvas.combine_shapes', text='Combine (holes where they overlap)',
                        icon='SELECT_DIFFERENCE')
        layout.operator('kanvas.separate_contours', text='Separate Contours', icon='MOD_EXPLODE')
        layout.separator()
        layout.operator('kanvas.offset_shape', text='Offset Outline...', icon='MOD_SKIN')
        layout.operator('kanvas.line_to_shape', text='Line to Shape', icon='MOD_OUTLINE')
        layout.operator('kanvas.simplify_shape', text='Simplify...', icon='MOD_DECIM')
        layout.separator()
        layout.operator('kanvas.flip_shape', text='Flip Horizontal', icon='MOD_MIRROR').axis = 'X'
        layout.operator('kanvas.flip_shape', text='Flip Vertical', icon='MOD_MIRROR').axis = 'Y'


def selection_ordered(settings, items):
    """Items in the order they were selected (first selected first); items selected
    together (a box selection) keep the order of the item list."""
    position = {item.item_id: index for index, item in enumerate(settings.images)}
    return sorted(items, key=lambda item: (item.selection_order or float('inf'),
                                           position.get(item.item_id, 0)))


def boolean_shapes(context, settings, shapes, operation, base=None):
    """Replace shapes by the result of a boolean operation on their filled areas.

    `shapes` are in selection order. A difference is the first shape minus all the
    others, with the first shape's look; union, intersection and exclusion keep the
    look of `base` (default: the first shape). The stacking on the canvas plays no
    part: it changes with every click. Curves become short straight edges and corner
    radii are baked in. Arrows attached to any of the shapes stay where they are, on
    the result. Returns the resulting shape, or None (nothing changed) when nothing
    would be left.
    """
    from ..utils.shape_boolean import combine
    ordered = list(shapes)
    if operation == 'DIFFERENCE' or base is None:
        base = ordered[0]
    base_id = base.item_id
    operands = [base] + [shape for shape in ordered if shape.item_id != base_id]
    rings = combine([[list(ring) for ring in shape_geometry.outlines(shape)
                      if len(ring) >= shape_geometry.MIN_VERTICES] for shape in operands],
                    operation)
    if not rings:
        return None
    ids = [shape.item_id for shape in operands]
    arrows = _shape_arrow_ends(settings, set(ids))
    base.shape_corner_radius = 0.0
    _set_canvas_rings(base, rings)
    _remove_items(context, settings, [item_id for item_id in ids if item_id != base_id])
    base = next(item for item in settings.images if item.item_id == base_id)
    for arrow, side, point in arrows:
        setattr(arrow, side + '_item_id', base_id)
        setattr(arrow, side + '_uv', shape_geometry.uv_at(base, point))
    for item in settings.images:
        item.is_selected = item.item_id == base_id
    settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                       if item.item_id == base_id)
    return base


class KANVAS_OT_BooleanShapes(KanvasTreeOnly, bpy.types.Operator):
    """Union, difference, intersection or exclusion of the selected shapes."""
    bl_idname = 'kanvas.boolean_shapes'
    bl_label = 'Boolean'
    bl_description = 'Join, cut, intersect or exclude the selected shapes into one shape'
    bl_options = {'REGISTER', 'UNDO'}

    operation: bpy.props.EnumProperty(  # type: ignore
        name='Operation',
        items=[('UNION', 'Union', 'One shape covering all of them'),
               ('DIFFERENCE', 'Difference', 'The first selected shape with the others cut '
                'out of it'),
               ('INTERSECT', 'Intersection', 'Only where all of them overlap'),
               ('EXCLUDE', 'Exclusion', 'Where an odd number of them overlap: the overlaps '
                'are cut out')],
        default='UNION',
    )

    @classmethod
    def description(cls, context, properties):
        return {
            'UNION': 'Join the selected shapes into one shape covering all of them',
            'DIFFERENCE': ('Cut the other selected shapes out of the first one you selected '
                           '(select the shape to cut first, then the cutters)'),
            'INTERSECT': 'Keep only the area where all the selected shapes overlap',
            'EXCLUDE': 'Join the selected shapes and cut out the areas where they overlap',
        }[properties.operation] + ('. Curves become short straight edges; Simplify with '
                                   'Smooth can round them again')

    @classmethod
    def poll(cls, context):
        return KANVAS_OT_CombineShapes.poll(context)

    def execute(self, context):
        settings = get_settings(context)
        shapes = selection_ordered(settings, _editable_shapes(settings))
        if not all(shape_geometry.is_closed(shape) for shape in shapes):
            self.report({'WARNING'}, 'Boolean operations need closed shapes: close the open '
                                     'paths, or turn their lines into shapes first')
            return {'CANCELLED'}
        active = active_shape(settings)
        base = active if active is not None and any(
            s.item_id == active.item_id for s in shapes) else None
        count = len(shapes)
        first = shapes[0].name
        result = boolean_shapes(context, settings, shapes, self.operation, base)
        if result is None:
            self.report({'WARNING'}, 'Nothing would be left: the shapes were not changed')
            return {'CANCELLED'}
        if self.operation == 'DIFFERENCE':
            self.report({'INFO'}, f'Cut {count - 1} shape(s) out of {first}')
        else:
            self.report({'INFO'}, f'{self.operation.title()} of {count} shapes: {result.name}')
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


def active_shape(settings):
    index = settings.active_image_index
    if 0 <= index < len(settings.images):
        item = settings.images[index]
        if item.item_type == 'SHAPE':
            return item
    return None


class KANVAS_OT_CreateShape(KanvasTreeOnly, bpy.types.Operator):
    """Draw a shape by dragging on the canvas."""
    bl_idname = 'kanvas.create_shape'
    bl_label = 'Add Shape'
    bl_description = ('Draw a shape: drag on the canvas, or click for a default size. '
                      'Shift makes it square and Ctrl draws it from the center')
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.EnumProperty(  # type: ignore
        name='Kind',
        items=[(identifier, label, description) for identifier, label, description, _
               in shape_geometry.KINDS],
        default='RECTANGLE',
    )
    location: bpy.props.FloatVectorProperty(size=2, options={'SKIP_SAVE'})  # type: ignore
    size: bpy.props.FloatVectorProperty(  # type: ignore
        size=2, default=shape_geometry.DEFAULT_SIZE, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        """Arm the next canvas drag; nothing stays running while the user is idle."""
        from .ops_modal import _shape_armed_areas
        _shape_armed_areas[(context.window.as_pointer(), context.area.as_pointer())] = self.kind
        from .. import keymap
        keymap.sync_hand_cursor()
        context.workspace.status_text_set(ARM_HINT)
        context.area.tag_redraw()
        return {'CANCELLED'}

    def execute(self, context):
        settings = get_settings(context)
        new_shape(context, settings, self.kind, self.location, *self.size)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


def draw_shape_menu_entries(layout):
    layout.operator_context = 'INVOKE_DEFAULT'
    for identifier, label, _, icon in _PRESET_KINDS:
        layout.operator('kanvas.create_shape', text=label, icon=icon).kind = identifier
    layout.separator()
    layout.operator('kanvas.draw_polygon', text='Pen (free path, Shift+P)',
                    icon='GREASEPENCIL').mode = 'PEN'
    layout.operator('kanvas.draw_polygon', text='Polygon (click by click, Ctrl+P)',
                    icon='EDITMODE_HLT').mode = 'POLYGON'
    layout.separator()
    layout.operator('kanvas.import_shapes_svg', text='Import SVG...', icon='IMPORT')


# ---------------------------------------------------------------------------
# Polygon and pen, drawn click by click
# ---------------------------------------------------------------------------

POLYGON_HINT = ('Polygon: click to add vertices  |  click the first vertex, double-click or Enter: finish  |  '
                'Backspace: remove last  |  Ctrl: snap to grid  |  Shift: 45 degree steps  |  '
                'Esc: cancel')
PEN_HINT = ('Pen: click a corner, drag a curve  |  click the first vertex: close  |  '
            'Enter or double-click: finish open  |  Backspace: remove last  |  Ctrl: snap to grid  |  '
            'Shift: 45 degree steps  |  Esc: cancel')
CONTOUR_HINT = ('Pen, new contour of {name}: click a corner, drag a curve  |  click the first vertex '
                'or Enter: finish  |  Backspace: remove last  |  Esc: cancel')


def polygon_from_points(item, points, handles=None):
    """Fit the shape's box and unit vertices to canvas points (the shape is unrotated).

    `handles` gives, per point, None for a corner or the (left, right) canvas handles of
    a smooth (Mirrored) vertex.
    """
    from ..properties import set_vertex_records, suspend_frame_geometry_updates
    handles = handles or [None] * len(points)
    extent = list(points) + [h for pair in handles if pair for h in pair]
    xs = [p[0] for p in extent]
    ys = [p[1] for p in extent]
    size_x = max(shape_geometry.MIN_SIZE, max(xs) - min(xs))
    size_y = max(shape_geometry.MIN_SIZE, max(ys) - min(ys))
    center = ((max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5)
    with suspend_frame_geometry_updates():
        item.shape_width, item.shape_height = size_x, size_y
        item.location = center

    def unit(point):
        return (point[0] - center[0]) / size_x, (point[1] - center[1]) / size_y

    set_vertex_records(item, [
        (unit(point), 'MIRRORED' if pair else 'SHARP',
         unit(pair[0] if pair else point), unit(pair[1] if pair else point))
        for point, pair in zip(points, handles)])


def constrain_to_45(origin, point):
    """Snap the direction from origin to point to a multiple of 45 degrees."""
    import math
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return point
    angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
    return origin[0] + math.cos(angle) * length, origin[1] + math.sin(angle) * length


class PolygonSession:
    """State of one path drawn click by click: the placed points and the live shape.

    `mode` 'POLYGON' always closes the outline. 'PEN' also curves: dragging after a
    click pulls the handles of that vertex (`drag_handle`), and the path may end open.
    With `target_id`, the path becomes a new contour of that shape when it is finished.
    """

    def __init__(self, mode='POLYGON', target_id=''):
        self.points = []
        self.handles = []
        self.item_id = ''
        self.mode = mode
        self.target_id = target_id

    def item(self, settings):
        from ..utils.gpu import get_item_by_id
        return get_item_by_id(settings, self.item_id) if self.item_id else None

    def target(self, settings):
        from ..utils.gpu import get_item_by_id
        return get_item_by_id(settings, self.target_id) if self.target_id else None

    def _show(self, settings, floating=None):
        item = self.item(settings)
        points = self.points + ([floating] if floating is not None else [])
        handles = self.handles + ([None] if floating is not None else [])
        if item is not None and points:
            polygon_from_points(item, points, handles)

    def add_point(self, context, settings, point):
        if self.points and tuple(self.points[-1]) == tuple(point):
            return
        if not self.points:
            target = self.target(settings)
            item = new_shape(context, settings, 'POLYGON', point, 1.0, 1.0, attach=False)
            item.shape_edit_vertices = True  # vertex handles give live feedback
            if self.mode == 'PEN':
                # Drawn as an open line until it is closed.
                item.shape_closed = False
            if target is not None:
                # Same look as the shape it will join.
                for name in ('shape_fill_color', 'shape_line_color'):
                    setattr(item, name, tuple(getattr(target, name)))
                item.shape_line_width = target.shape_line_width
            self.item_id = item.item_id
        self.points.append((point[0], point[1]))
        self.handles.append(None)
        self._show(settings)

    def drag_handle(self, settings, point):
        """Pull the handles of the last vertex: the outgoing one follows the pointer and
        the incoming one mirrors it, so the vertex becomes a smooth point."""
        if not self.points or self.mode != 'PEN':
            return
        co = self.points[-1]
        if math.dist(co, point) < 1e-9:
            self.handles[-1] = None
        else:
            self.handles[-1] = ((2.0 * co[0] - point[0], 2.0 * co[1] - point[1]),
                                (point[0], point[1]))
        self._show(settings)

    def move(self, settings, point):
        if self.points:
            self._show(settings, point)

    def remove_last(self, settings):
        if self.points:
            self.points.pop()
            self.handles.pop()
        if self.points:
            self._show(settings)
        return bool(self.points)

    def can_close(self):
        return len(self.points) >= shape_geometry.MIN_VERTICES

    def can_finish_open(self):
        return len(self.points) >= 2

    def closes_on_finish(self, settings):
        """Whether Enter or a double-click closes the path (a polygon, or a contour
        added to a closed shape) or leaves it open."""
        target = self.target(settings)
        if target is not None:
            return shape_geometry.is_closed(target)
        return self.mode != 'PEN'

    def finish(self, context, settings, close=None):
        """Keep the shape. Returns False (and drops it) when it is too short.

        `close` None follows `closes_on_finish`; True closes the outline (the first
        vertex was clicked again), False leaves the path open.
        """
        item = self.item(settings)
        target = self.target(settings)
        if close is None or target is not None:
            close = self.closes_on_finish(settings)  # a new contour matches its shape
        if item is None or not (self.can_close() if close else self.can_finish_open()):
            self.cancel(settings)
            return False
        self._show(settings)
        item.shape_edit_vertices = False
        item.shape_kind = 'POLYGON'
        if close:
            item.shape_closed = True
            if self.mode == 'PEN' and target is None:
                item.shape_show_fill = True
        else:
            item.shape_closed = False
            item.shape_show_outline = True
            item.shape_show_fill = False
        normalize_shape(item)
        if target is not None:
            joined = combine_shapes(context, settings, [target, item], target)
            joined.shape_edit_vertices = True
            return True
        attach_new_shape(context, settings, item)
        return True

    def cancel(self, settings):
        item = self.item(settings)
        if item is not None:
            index = next(i for i, other in enumerate(settings.images)
                         if other.item_id == item.item_id)
            settings.images.remove(index)
            settings.active_image_index = -1
            target = self.target(settings)
            if target is not None:
                # Back to editing the shape the contour was meant for.
                for other in settings.images:
                    other.is_selected = other.item_id == target.item_id
                settings.active_image_index = next(
                    i for i, other in enumerate(settings.images) if other.item_id == target.item_id)
        self.points = []
        self.handles = []
        self.item_id = ''


class KANVAS_OT_DrawPolygon(KanvasTreeOnly, bpy.types.Operator):
    """Draw a polygon or a free path by clicking its vertices."""
    bl_idname = 'kanvas.draw_polygon'
    bl_label = 'Draw Path'
    bl_description = ('Click each vertex, with a live preview. Pen: drag after a click to curve, '
                      'click the first vertex to close, Enter or double-click to finish an open path; '
                      'while a shape is in Edit Vertices, the path becomes a new contour of it. '
                      'Polygon: always closed. Backspace removes the last vertex, Esc cancels')
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(  # type: ignore
        name='Mode',
        items=[('POLYGON', 'Polygon', 'A closed outline with straight edges'),
               ('PEN', 'Pen', 'A free path with corners and curves, open or closed')],
        default='POLYGON',
    )

    @classmethod
    def description(cls, context, properties):
        if properties.mode == 'PEN':
            return ('Draw a free path: click for a corner, drag for a curve. Click the first '
                    'vertex to close it, or press Enter or double-click to leave it open. While a '
                    'shape is in Edit Vertices, the path becomes a new contour of that shape')
        return 'Click each vertex of a closed polygon. Enter, a double-click or the first vertex finishes'

    def invoke(self, context, event):
        from ..utils.gpu import gpu_shape_cursor
        from ..utils.gpu.gpu_shape import vertex_edit_shape
        settings = get_settings(context)
        target = vertex_edit_shape(settings) if (self.mode == 'PEN' and settings) else None
        self.session = PolygonSession(self.mode, target.item_id if target else '')
        self.dragging = False
        self.area = context.area
        self._cursor_key = gpu_shape_cursor.area_key(context.window, context.area)
        gpu_shape_cursor.polygon_areas[self._cursor_key] = True
        gpu_shape_cursor.positions[self._cursor_key] = (event.mouse_region_x,
                                                        event.mouse_region_y)
        if target is not None:
            hint = CONTOUR_HINT.format(name=target.name)
        else:
            hint = PEN_HINT if self.mode == 'PEN' else POLYGON_HINT
        context.workspace.status_text_set(hint)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _end(self, context):
        from ..utils.gpu import gpu_shape_cursor
        gpu_shape_cursor.polygon_areas.pop(self._cursor_key, None)
        gpu_shape_cursor.positions.pop(self._cursor_key, None)
        try:
            context.workspace.status_text_set(None)
        except (ReferenceError, RuntimeError):
            pass
        self.area.tag_redraw()

    def _point(self, context, event, settings):
        from .ops_arrow import _canvas_point
        point = _canvas_point(context, event)
        if point is None:
            return None
        if event.shift and self.session.points:
            point = constrain_to_45(self.session.points[-1], point)
        if event.ctrl:
            grid = max(1.0, float(settings.grid_size))
            point = (round(point[0] / grid) * grid, round(point[1] / grid) * grid)
        return point

    def _finish(self, context, settings, close=None):
        session = self.session
        closing = session.closes_on_finish(settings) if close is None else close
        ok = session.finish(context, settings, close)
        self._end(context)
        if not ok:
            least = shape_geometry.MIN_VERTICES if closing else 2
            self.report({'WARNING'}, f'A {"closed outline" if closing else "path"} needs at least '
                                     f'{least} vertices')
        return {'FINISHED'} if ok else {'CANCELLED'}

    def modal(self, context, event):
        settings = get_settings(context)
        session = self.session
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            session.cancel(settings)
            self._end(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            return self._finish(context, settings)
        if event.type == 'BACK_SPACE' and event.value == 'PRESS':
            self.dragging = False
            if not session.remove_last(settings):
                session.cancel(settings)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        from ..utils.gpu import gpu_shape_cursor
        from .ops_arrow import _pixel_size
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.dragging = False
            return {'RUNNING_MODAL'}
        point = self._point(context, event, settings)
        if point is None:
            gpu_shape_cursor.positions.pop(self._cursor_key, None)
            self.area.tag_redraw()
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        gpu_shape_cursor.positions[self._cursor_key] = (event.mouse_region_x,
                                                        event.mouse_region_y)
        if event.type == 'LEFTMOUSE' and event.value == 'DOUBLE_CLICK':
            # The first click of the double click already placed the last vertex.
            return self._finish(context, settings)
        if event.type == 'MOUSEMOVE':
            if self.dragging:
                # A drag right after a click curves that vertex (Pen only).
                if math.dist(point, session.points[-1]) >= 4.0 * _pixel_size(context):
                    session.drag_handle(settings, point)
            else:
                session.move(settings, point)
        elif event.value == 'PRESS':
            if (session.can_close() and math.dist(point, session.points[0])
                    < 10.0 * _pixel_size(context)):
                return self._finish(context, settings, True)
            session.add_point(context, settings, point)
            self.dragging = self.mode == 'PEN'
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self.session.cancel(get_settings(context))
        self._end(context)


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def shape_from_outline(context, settings, records, outline, name='SVG Shape'):
    """Add a polygon shape whose vertices and handles are canvas `records`.

    Records are (co, type, left, right) or, for several contours, (co, type, left,
    right, contour), with the vertices of each contour together.
    """
    from ..properties import set_vertex_records
    points = [p for record in records for p in (record[0], record[2], record[3])]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    center = ((max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5)
    width = max(shape_geometry.MIN_SIZE, max(xs) - min(xs))
    height = max(shape_geometry.MIN_SIZE, max(ys) - min(ys))
    item = new_shape(context, settings, 'POLYGON', center, width, height, attach=False)

    def unit(point):
        return (point[0] - center[0]) / width, (point[1] - center[1]) / height

    set_vertex_records(item, [(unit(r[0]), r[1], unit(r[2]), unit(r[3]),
                               r[4] if len(r) > 4 else 0) for r in records])
    item.name = unique_item_name(settings, name)
    fill, stroke = outline['fill'], outline['stroke']
    item.shape_show_fill = True
    item.shape_show_outline = True
    if fill is not None:
        item.shape_fill_color = fill
        item.shape_fill_opacity = max(0.0, min(1.0, outline['fill_opacity']))
    if stroke is not None:
        item.shape_line_color = stroke
        item.shape_line_width = max(1.0, min(40.0, outline['stroke_width']))
        item.shape_line_style = 'DASHED' if outline['dashed'] else 'SOLID'
        item.shape_line_join = outline.get('join', 'ROUND')
        item.shape_line_cap = outline.get('cap', 'ROUND')
    elif fill is not None:
        item.shape_line_color = fill
    item.shape_show_fill = fill is not None
    item.shape_show_outline = stroke is not None or fill is None
    normalize_shape(item)
    return item


def import_svg_shapes(context, settings, text, center, target_size=0.0):
    """Add the shapes of an SVG document, centered on `center`.

    Each element becomes a shape, with one contour per subpath (holes included; see
    `contour_groups` for the elements that need more than one shape). With
    `target_size`, the drawing is scaled so its larger side has that size. Returns
    (shapes, skipped elements without area).
    """
    from ..utils.svg_shapes import contour_groups, outline_records, parse_svg
    outlines = parse_svg(text)
    points = [p for outline in outlines for contour in outline['contours']
              for segment in contour for p in segment]
    if not points:
        return [], len(outlines)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    middle = ((max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5)
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    scale = target_size / span if target_size > 0 and span > 1e-9 else 1.0

    def place(point):
        return (center[0] + (point[0] - middle[0]) * scale,
                center[1] + (point[1] - middle[1]) * scale)

    # Keep ids, not items: adding to the collection can move earlier items in memory.
    created, skipped = [], 0
    eps = 1e-6 * max(1.0, span * scale)
    for outline in outlines:
        # A line without fill whose subpaths are all open stays an open path.
        open_path = outline['fill'] is None and not any(outline['closed'])
        contours = [outline_records([tuple(place(p) for p in segment) for segment in contour],
                                    eps=eps, closed=not open_path)
                    for contour in outline['contours']]
        contours = [records for records in contours if records]
        if not contours:
            skipped += 1
            continue
        outline = dict(outline, stroke_width=outline['stroke_width'] * scale)
        groups = contour_groups(contours, outline['fill_rule'])
        for number, group in enumerate(groups):
            records = [(*record, contour) for contour, index in enumerate(group)
                       for record in contours[index]]
            name = outline['name'] or 'SVG Shape'
            if len(groups) > 1:
                name = f'{name} {number + 1}'
            shape = shape_from_outline(context, settings, records, outline, name)
            if open_path:
                shape.shape_closed = False
            created.append(shape.item_id)
    wanted = set(created)
    for item in settings.images:
        item.is_selected = item.item_id in wanted
    by_id = {item.item_id: (i, item) for i, item in enumerate(settings.images)}
    if created:
        settings.active_image_index = by_id[created[-1]][0]
    return [by_id[item_id][1] for item_id in created], skipped


def _selected_shapes(settings):
    return [item for item in settings.images
            if item.item_type == 'SHAPE' and item.is_selected and item.show_in_editor]


def _view_center(context):
    region = getattr(context, 'region', None)
    if region is not None and region.type == 'WINDOW' and getattr(region, 'view2d', None):
        return tuple(region.view2d.region_to_view(region.width / 2, region.height / 2))
    return (0.0, 0.0)


class KANVAS_FH_SVG(bpy.types.FileHandler):
    """Drop SVG files on a Kanvas board to add their shapes where they land."""
    bl_idname = 'KANVAS_FH_SVG'
    bl_label = 'Kanvas SVG Drop Handler'
    bl_file_extensions = '.svg'
    bl_import_operator = 'kanvas.import_shapes_svg'

    @classmethod
    def poll_drop(cls, context):
        from .ops_image import KANVAS_FH_ImageHandler
        return KANVAS_FH_ImageHandler.poll_drop(context)


class KANVAS_OT_ImportShapesSVG(KanvasTreeOnly, bpy.types.Operator):
    """Add shapes from an SVG file."""
    bl_idname = 'kanvas.import_shapes_svg'
    bl_label = 'Import SVG Shapes'
    bl_description = ('Add the outlines of an SVG file as shapes, with their curves, fill and '
                      'stroke. Each element becomes one shape. Dropping SVG files on the board '
                      'adds them where they land')
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})  # type: ignore
    directory: bpy.props.StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})  # type: ignore
    files: bpy.props.CollectionProperty(  # type: ignore
        type=bpy.types.OperatorFileListElement, options={'SKIP_SAVE'})
    filter_glob: bpy.props.StringProperty(default='*.svg', options={'HIDDEN'})  # type: ignore
    fit_size: bpy.props.BoolProperty(  # type: ignore
        name='Fit Size', default=True,
        description='Scale the drawing so its larger side has the Size below; off keeps the SVG units')
    size: bpy.props.FloatProperty(  # type: ignore
        name='Size', default=400.0, min=10.0, max=100000.0,
        description='Larger side of the imported drawing on the canvas')
    group: bpy.props.BoolProperty(  # type: ignore
        name='Group', default=True,
        description='Group the shapes when the file has more than one outline')

    def invoke(self, context, event):
        from .ops_image import drop_location
        if self.filepath or self.files:
            # Dropped on the board: the drawing lands where the pointer is.
            self._center = drop_location(context, event) or _view_center(context)
            return self.execute(context)
        self._center = _view_center(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def _paths(self):
        import os
        names = [entry.name for entry in self.files if entry.name]
        if names and self.directory:
            return [os.path.join(self.directory, name) for name in names]
        return [self.filepath] if self.filepath else []

    def execute(self, context):
        settings = get_settings(context)
        paths = self._paths()
        if not paths:
            return {'CANCELLED'}
        center = getattr(self, '_center', None) or _view_center(context)
        imported, skipped, created = 0, 0, []
        next_left = None   # several files: each one starts right of the previous one
        for path in paths:
            try:
                with open(bpy.path.abspath(path), encoding='utf-8-sig') as handle:
                    text = handle.read()
            except (OSError, UnicodeDecodeError) as exc:
                self.report({'ERROR'}, f'Could not read the SVG file: {exc}')
                continue
            try:
                shapes, missed = import_svg_shapes(context, settings, text, center,
                                                   self.size if self.fit_size else 0.0)
            except Exception as exc:   # malformed XML and the like
                self.report({'ERROR'}, f'Could not read the SVG file: {exc}')
                continue
            if not shapes:
                continue
            ids = [shape.item_id for shape in shapes]
            if next_left is not None:
                # The first file is centered on the drop point, the next ones follow
                # it to the right.
                shift = next_left - min(shape_geometry.bounds(shape)[0] for shape in shapes)
                for item_id in ids:
                    item = next(other for other in settings.images if other.item_id == item_id)
                    item.location = (item.location[0] + shift, item.location[1])
            placed = [next(other for other in settings.images if other.item_id == item_id)
                      for item_id in ids]
            next_left = max(shape_geometry.bounds(shape)[2] for shape in placed) + 40.0
            # Everything is named after the file: one shape takes the name, several get
            # it with a number (name.001, name.002...), and their group takes it plain.
            import os
            stem = os.path.splitext(os.path.basename(path))[0] or 'SVG'
            for item_id in ids:
                item = next(other for other in settings.images if other.item_id == item_id)
                item.name = f'kanvas_svg_{item_id}'   # free the old names first
            group = None
            if self.group and len(ids) > 1:
                from .ops_group import group_selection
                group_id = group_selection(context, settings)
                group = next((item for item in settings.images if item.item_id == group_id), None)
                if group is not None:
                    group.name = unique_item_name(settings, stem)
            for number, item_id in enumerate(ids, start=1):
                item = next(other for other in settings.images if other.item_id == item_id)
                item.name = (unique_item_name(settings, stem) if len(ids) == 1
                             else unique_item_name(settings, f'{stem}.{number:03d}'))
            imported += len(ids)
            skipped += missed
            created.extend(ids)
        if not imported:
            self.report({'WARNING'}, 'No shape found in the SVG file')
            return {'CANCELLED'}
        wanted = set(created)
        for item in settings.images:
            if item.item_type == 'SHAPE':
                item.is_selected = item.item_id in wanted
        plural = 's' if imported != 1 else ''
        message = f'Imported {imported} shape{plural}'
        if len(paths) > 1:
            message += f' from {len(paths)} files'
        if skipped:
            message += f'; skipped {skipped} outline(s) without area'
        self.report({'INFO'}, message)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_ExportShapesSVG(KanvasTreeOnly, bpy.types.Operator):
    """Save the selected shapes as an SVG file."""
    bl_idname = 'kanvas.export_shapes_svg'
    bl_label = 'Export Shapes as SVG'
    bl_description = ('Save the selected shapes as an SVG file, with their curves, fill, '
                      'stroke and text')
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})  # type: ignore
    filter_glob: bpy.props.StringProperty(default='*.svg', options={'HIDDEN'})  # type: ignore
    check_existing: bpy.props.BoolProperty(default=True, options={'HIDDEN'})  # type: ignore

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return settings is not None and bool(_selected_shapes(settings))

    def invoke(self, context, event):
        if not self.filepath:
            shapes = _selected_shapes(get_settings(context))
            base = shapes[0].name if len(shapes) == 1 else 'Shapes'
            self.filepath = bpy.path.clean_name(base) + '.svg'
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from ..utils.svg_shapes import export_svg
        shapes = _selected_shapes(get_settings(context))
        document = export_svg(shapes)
        if not document:
            self.report({'WARNING'}, 'No shape to export')
            return {'CANCELLED'}
        path = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), '.svg')
        try:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(document)
        except OSError as exc:
            self.report({'ERROR'}, f'Could not save the SVG file: {exc}')
            return {'CANCELLED'}
        plural = 's' if len(shapes) != 1 else ''
        self.report({'INFO'}, f'Saved {len(shapes)} shape{plural} to {path}')
        return {'FINISHED'}
