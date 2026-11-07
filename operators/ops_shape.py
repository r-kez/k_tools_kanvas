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
    from ..properties import set_shape_vertices
    for item in settings.images:
        item.is_selected = False
    name = unique_item_name(settings, kind_label(kind))
    item = settings.images.add()
    item.item_id = uuid.uuid4().hex
    item.item_type = 'SHAPE'
    item.name = name
    item.shape_kind = kind
    set_shape_vertices(item, shape_geometry.preset_vertices(kind)
                       or shape_geometry.preset_vertices('RECTANGLE'))
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
    extent = [unit for unit, _, _ in shape_geometry.curve_units(item)]
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
    prev, nxt = records[index - 1][0], records[(index + 1) % len(records)][0]
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
    handles = shape_geometry.effective_handles(records)
    changes = []
    for index in indices:
        old = records[index][1]
        if old == kind:
            continue
        left = right = None
        co = records[index][0]
        if kind in {'ALIGNED', 'MIRRORED', 'FREE'}:
            if old == 'SHARP' and kind == 'FREE':
                left = _third(co, records[index - 1][0])
                right = _third(co, records[(index + 1) % len(records)][0])
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
        records, shape_geometry.effective_handles(records), edge)
    if shape_geometry.is_straight(controls):
        p0, _, _, p3 = controls
        controls = (p0, _third(p0, p3), _third(p3, p0), p3)
    return controls


def bend_edge(item, edge, t, base, delta):
    """Pull the curve point at t of an edge by `delta` (unit box), from `base` controls."""
    first, second = shape_geometry.bend_offsets(t, delta)
    end = (edge + 1) % len(item.shape_vertices)
    set_handle(item, edge, 'right', (base[1][0] + first[0], base[1][1] + first[1]))
    set_handle(item, end, 'left', (base[2][0] + second[0], base[2][1] + second[1]))


def insert_shape_vertex(item, edge, t):
    """Add a vertex on an edge at curve parameter t; a curved edge keeps its shape.

    Returns the index of the new vertex.
    """
    records = shape_geometry.item_records(item)
    handles = shape_geometry.effective_handles(records)
    controls = shape_geometry.segment_controls(records, handles, edge)
    end = (edge + 1) % len(records)
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
    index = edge + 1
    item.shape_vertices.move(len(item.shape_vertices) - 1, index)
    return index


def _outline_arrow_ends(settings, item):
    """(arrow, side) of every arrow end that sits on the shape's outline, not inside it."""
    from ..utils.arrow_geometry import endpoint
    points = shape_geometry.outline(item)
    if len(points) < shape_geometry.MIN_VERTICES:
        return []
    tolerance = max(1e-4, 1e-3 * max(shape_geometry.shape_extent(item)))
    ends = []
    for arrow in settings.arrows:
        for side in ('start', 'end'):
            if getattr(arrow, side + '_item_id') != item.item_id:
                continue
            _, distance, _ = shape_geometry.nearest_edge(points, endpoint(settings, arrow, side))
            if distance <= tolerance:
                ends.append((arrow, side))
    return ends


def delete_shape_vertices(item, indices):
    """Remove vertices from a shape. Returns '' when done, or why nothing was removed.

    In an outline, removing a vertex joins its two neighbours, so this is also the
    "dissolve" of a mesh editor. Arrow ends that sat on the outline stay on it: an end
    on a removed vertex drops to the nearest point of the new outline. Ends placed
    inside the shape keep their position.
    """
    from ..utils.arrow_geometry import endpoint
    indices = sorted({i for i in indices if 0 <= i < len(item.shape_vertices)}, reverse=True)
    if not indices:
        return 'Select vertices to delete'
    if len(item.shape_vertices) - len(indices) < shape_geometry.MIN_VERTICES:
        return f'A shape needs at least {shape_geometry.MIN_VERTICES} vertices'
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
    layout.operator('kanvas.draw_polygon', text='Polygon (click by click)', icon='EDITMODE_HLT')
    layout.separator()
    layout.operator('kanvas.import_shapes_svg', text='Import SVG...', icon='IMPORT')


# ---------------------------------------------------------------------------
# Polygon drawn click by click
# ---------------------------------------------------------------------------

POLYGON_HINT = ('Polygon: click to add vertices  |  click the first vertex, double-click or Enter: finish  |  '
                'Backspace: remove last  |  Ctrl: snap to grid  |  Shift: 45 degree steps  |  '
                'Esc: cancel')


def polygon_from_points(item, points):
    """Fit the shape's box and unit vertices to canvas points (the shape is unrotated)."""
    from ..properties import set_shape_vertices, suspend_frame_geometry_updates
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    size_x = max(shape_geometry.MIN_SIZE, max(xs) - min(xs))
    size_y = max(shape_geometry.MIN_SIZE, max(ys) - min(ys))
    center = ((max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5)
    with suspend_frame_geometry_updates():
        item.shape_width, item.shape_height = size_x, size_y
        item.location = center
    set_shape_vertices(item, [((x - center[0]) / size_x, (y - center[1]) / size_y)
                              for x, y in points])


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
    """State of one click-by-click polygon: the placed points and the live shape."""

    def __init__(self):
        self.points = []
        self.item_id = ''

    def item(self, settings):
        from ..utils.gpu import get_item_by_id
        return get_item_by_id(settings, self.item_id) if self.item_id else None

    def _show(self, settings, floating=None):
        item = self.item(settings)
        points = self.points + ([floating] if floating is not None else [])
        if item is not None and points:
            polygon_from_points(item, points)

    def add_point(self, context, settings, point):
        if self.points and tuple(self.points[-1]) == tuple(point):
            return
        if not self.points:
            item = new_shape(context, settings, 'POLYGON', point, 1.0, 1.0, attach=False)
            item.shape_edit_vertices = True  # vertex handles give live feedback
            self.item_id = item.item_id
        self.points.append((point[0], point[1]))
        self._show(settings)

    def move(self, settings, point):
        if self.points:
            self._show(settings, point)

    def remove_last(self, settings):
        if self.points:
            self.points.pop()
        if self.points:
            self._show(settings)
        return bool(self.points)

    def can_close(self):
        return len(self.points) >= shape_geometry.MIN_VERTICES

    def finish(self, context, settings):
        """Keep the shape. Returns False (and drops it) when it is not a real polygon."""
        item = self.item(settings)
        if item is None or not self.can_close():
            self.cancel(settings)
            return False
        self._show(settings)
        item.shape_edit_vertices = False
        item.shape_kind = 'POLYGON'
        normalize_shape(item)
        attach_new_shape(context, settings, item)
        return True

    def cancel(self, settings):
        item = self.item(settings)
        if item is not None:
            index = next(i for i, other in enumerate(settings.images)
                         if other.item_id == item.item_id)
            settings.images.remove(index)
            settings.active_image_index = -1
        self.points = []
        self.item_id = ''


class KANVAS_OT_DrawPolygon(KanvasTreeOnly, bpy.types.Operator):
    """Draw a polygon by clicking its vertices."""
    bl_idname = 'kanvas.draw_polygon'
    bl_label = 'Draw Polygon'
    bl_description = ('Click each vertex of a polygon, with a live preview. Click the first '
                      'vertex, double-click or press Enter to finish, Backspace removes the last vertex, '
                      'Esc cancels')
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        from ..utils.gpu import gpu_shape_cursor
        self.session = PolygonSession()
        self.area = context.area
        self._cursor_key = gpu_shape_cursor.area_key(context.window, context.area)
        gpu_shape_cursor.polygon_areas[self._cursor_key] = True
        gpu_shape_cursor.positions[self._cursor_key] = (event.mouse_region_x,
                                                        event.mouse_region_y)
        context.workspace.status_text_set(POLYGON_HINT)
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

    def modal(self, context, event):
        settings = get_settings(context)
        session = self.session
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            session.cancel(settings)
            self._end(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            ok = session.finish(context, settings)
            self._end(context)
            if not ok:
                self.report({'WARNING'}, f'A polygon needs at least {shape_geometry.MIN_VERTICES} vertices')
            return {'FINISHED'} if ok else {'CANCELLED'}
        if event.type == 'BACK_SPACE' and event.value == 'PRESS':
            if not session.remove_last(settings):
                session.cancel(settings)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        from ..utils.gpu import gpu_shape_cursor
        point = self._point(context, event, settings)
        if point is None:
            gpu_shape_cursor.positions.pop(self._cursor_key, None)
            self.area.tag_redraw()
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        gpu_shape_cursor.positions[self._cursor_key] = (event.mouse_region_x,
                                                        event.mouse_region_y)
        if event.type == 'LEFTMOUSE' and event.value == 'DOUBLE_CLICK':
            # The first click of the double click already placed the last vertex.
            ok = session.finish(context, settings)
            self._end(context)
            if not ok:
                self.report({'WARNING'}, f'A polygon needs at least {shape_geometry.MIN_VERTICES} vertices')
            return {'FINISHED'} if ok else {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            session.move(settings, point)
        elif event.value == 'PRESS':
            from .ops_arrow import _pixel_size
            if (session.can_close() and math.dist(point, session.points[0])
                    < 10.0 * _pixel_size(context)):
                ok = session.finish(context, settings)
                self._end(context)
                return {'FINISHED'} if ok else {'CANCELLED'}
            session.add_point(context, settings, point)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self.session.cancel(get_settings(context))
        self._end(context)


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def shape_from_outline(context, settings, records, outline, name='SVG Shape'):
    """Add a polygon shape whose vertices and handles are canvas `records`."""
    from ..properties import set_vertex_records
    points = [p for co, _, left, right in records for p in (co, left, right)]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    center = ((max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5)
    width = max(shape_geometry.MIN_SIZE, max(xs) - min(xs))
    height = max(shape_geometry.MIN_SIZE, max(ys) - min(ys))
    item = new_shape(context, settings, 'POLYGON', center, width, height, attach=False)

    def unit(point):
        return (point[0] - center[0]) / width, (point[1] - center[1]) / height

    set_vertex_records(item, [(unit(co), kind, unit(left), unit(right))
                              for co, kind, left, right in records])
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
    elif fill is not None:
        item.shape_line_color = fill
    item.shape_show_fill = fill is not None
    item.shape_show_outline = stroke is not None or fill is None
    normalize_shape(item)
    return item


def import_svg_shapes(context, settings, text, center, target_size=0.0):
    """Add one shape per closed outline of an SVG document, centered on `center`.

    With `target_size`, the drawing is scaled so its larger side has that size.
    Returns (shapes, skipped outlines).
    """
    from ..utils.svg_shapes import outline_records, parse_svg
    outlines = parse_svg(text)
    points = [p for outline in outlines for segment in outline['segments'] for p in segment]
    if not points:
        return [], len(outlines)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    middle = ((max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5)
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    scale = target_size / span if target_size > 0 and span > 1e-9 else 1.0

    def place(point):
        return (center[0] + (point[0] - middle[0]) * scale,
                center[1] + (point[1] - middle[1]) * scale)

    shapes, skipped = [], 0
    for outline in outlines:
        segments = [tuple(place(p) for p in segment) for segment in outline['segments']]
        records = outline_records(segments, eps=1e-6 * max(1.0, span * scale))
        if not records:
            skipped += 1
            continue
        outline = dict(outline, stroke_width=outline['stroke_width'] * scale)
        shapes.append(shape_from_outline(context, settings, records, outline,
                                         outline['name'] or 'SVG Shape'))
    for item in settings.images:
        item.is_selected = any(item.item_id == shape.item_id for shape in shapes)
    if shapes:
        settings.active_image_index = next(
            i for i, item in enumerate(settings.images) if item.item_id == shapes[-1].item_id)
    return shapes, skipped


def _selected_shapes(settings):
    return [item for item in settings.images
            if item.item_type == 'SHAPE' and item.is_selected and item.show_in_editor]


def _view_center(context):
    region = getattr(context, 'region', None)
    if region is not None and region.type == 'WINDOW' and getattr(region, 'view2d', None):
        return tuple(region.view2d.region_to_view(region.width / 2, region.height / 2))
    return (0.0, 0.0)


class KANVAS_OT_ImportShapesSVG(KanvasTreeOnly, bpy.types.Operator):
    """Add shapes from an SVG file."""
    bl_idname = 'kanvas.import_shapes_svg'
    bl_label = 'Import SVG Shapes'
    bl_description = ('Add the outlines of an SVG file as shapes, with their curves, fill and '
                      'stroke. Each closed outline becomes one shape')
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})  # type: ignore
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
        self._center = _view_center(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        settings = get_settings(context)
        try:
            with open(bpy.path.abspath(self.filepath), encoding='utf-8-sig') as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            self.report({'ERROR'}, f'Could not read the SVG file: {exc}')
            return {'CANCELLED'}
        center = getattr(self, '_center', None) or _view_center(context)
        try:
            shapes, skipped = import_svg_shapes(context, settings, text, center,
                                                self.size if self.fit_size else 0.0)
        except Exception as exc:   # malformed XML and the like
            self.report({'ERROR'}, f'Could not read the SVG file: {exc}')
            return {'CANCELLED'}
        if not shapes:
            self.report({'WARNING'}, 'No closed outline found in the SVG file')
            return {'CANCELLED'}
        if self.group and len(shapes) > 1:
            from .ops_group import group_selection
            group_selection(context, settings)
        plural = 's' if len(shapes) != 1 else ''
        message = f'Imported {len(shapes)} shape{plural}'
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
