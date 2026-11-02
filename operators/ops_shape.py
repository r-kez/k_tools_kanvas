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
    result = shape_geometry.normalized([tuple(v.co) for v in item.shape_vertices])
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
    for arrow, side, position in anchored:
        setattr(arrow, side + '_uv', shape_geometry.uv_at(item, position))
    if item.parent_frame:
        from ..utils.gpu import update_frame_bounds
        update_frame_bounds(None, get_settings(bpy.context), item.parent_frame)


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


# ---------------------------------------------------------------------------
# Polygon drawn click by click
# ---------------------------------------------------------------------------

POLYGON_HINT = ('Polygon: click to add vertices  |  click the first vertex or Enter: finish  |  '
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
                      'vertex or press Enter to finish, Backspace removes the last vertex, '
                      'Esc cancels')
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        self.session = PolygonSession()
        self.area = context.area
        context.workspace.status_text_set(POLYGON_HINT)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _end(self, context):
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
        point = self._point(context, event, settings)
        if point is None:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
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
