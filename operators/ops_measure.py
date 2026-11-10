"""Marks and scale on images.

Drawing a mark works like drawing a shape: the tool button only arms the next drag on the
canvas (plain state, so nothing runs while the user is idle); the press then starts
`kanvas.draw_measure`, which is modal only for the length of the drag. A mark made for
the scale then opens a small dialog asking how big it really is.
"""

import math

import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils import measure as mm
from ..utils.kanvas_data import get_settings

HINT = {
    'LINE': 'Measure: drag along what you want to measure  |  Shift: along the image axes or '
            'at 45°  |  Esc: cancel',
    'RECT': 'Measure: drag a rectangle  |  Shift: square  |  Esc: cancel',
}
MIN_DRAG_PIXELS = 4.0


def _item(settings, item_id):
    return next((item for item in settings.images if item.item_id == item_id), None)


def _marked_image(context):
    """The active image, the one the Measure tab shows: a picture item with its image."""
    settings = get_settings(context)
    index = settings.active_image_index
    if 0 <= index < len(settings.images):
        item = settings.images[index]
        if item.item_type == 'IMAGE' and item.image_data and item.image_data.size[0] > 0:
            return item
    return None


def _clamp_uv(uv):
    return min(1.0, max(0.0, uv[0])), min(1.0, max(0.0, uv[1]))


def _constrained(item, start, end, kind):
    """`end` held to the image axes or 45° steps (a line) or to a square (a rectangle),
    measured in image pixels."""
    width, height = mm.pixel_size(item)
    dx, dy = (end[0] - start[0]) * width, (end[1] - start[1]) * height
    if kind == 'RECT':
        side = max(abs(dx), abs(dy))
        dx = math.copysign(side, dx or 1.0)
        dy = math.copysign(side, dy or 1.0)
    else:
        length = math.hypot(dx, dy)
        angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
        dx, dy = length * math.cos(angle), length * math.sin(angle)
    return _clamp_uv((start[0] + dx / width, start[1] + dy / height))


class KANVAS_OT_MeasureTool(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.measure_tool'
    bl_label = 'Draw Mark'
    bl_description = ('Draw a line or a rectangle on the active image: drag on the canvas. '
                      'It reads in pixels, or in real units once the image has a scale')
    bl_options = {'REGISTER'}

    kind: bpy.props.EnumProperty(  # type: ignore
        name='Kind', items=(('LINE', 'Line', 'Two points'),
                            ('RECT', 'Rectangle', 'Two opposite corners')),
        default='LINE', options={'SKIP_SAVE'})
    purpose: bpy.props.EnumProperty(  # type: ignore
        name='Purpose', items=(('MARK', 'Mark', 'A mark that is read in the scale of the image'),
                               ('SCALE', 'Scale', 'A mark of known real size: it gives the '
                                                  'image its scale')),
        default='MARK', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and _marked_image(context) is not None

    def invoke(self, context, event):
        """Arm the next canvas drag; nothing stays running while the user is idle."""
        item = _marked_image(context)
        if item is None:
            return {'CANCELLED'}
        from .ops_modal import _shape_armed_areas
        key = (context.window.as_pointer(), context.area.as_pointer())
        _shape_armed_areas[key] = f'MEASURE:{self.purpose}:{self.kind}:{item.item_id}'
        from .. import keymap
        keymap.sync_hand_cursor()
        context.workspace.status_text_set(HINT[self.kind])
        context.area.tag_redraw()
        return {'CANCELLED'}


class KANVAS_OT_DrawMeasure(KanvasTreeOnly, bpy.types.Operator):
    """Drag out a mark on an image. Started by the press that follows the Draw Mark tool."""
    bl_idname = 'kanvas.draw_measure'
    bl_label = 'Draw Mark'
    bl_options = {'REGISTER', 'UNDO'}

    item_id: bpy.props.StringProperty(options={'SKIP_SAVE'})  # type: ignore
    kind: bpy.props.EnumProperty(  # type: ignore
        items=(('LINE', 'Line', ''), ('RECT', 'Rectangle', '')),
        default='LINE', options={'SKIP_SAVE'})
    purpose: bpy.props.EnumProperty(  # type: ignore
        items=(('MARK', 'Mark', ''), ('SCALE', 'Scale', '')),
        default='MARK', options={'SKIP_SAVE'})

    def invoke(self, context, event):
        from .ops_arrow import _canvas_point
        settings = get_settings(context)
        item = _item(settings, self.item_id)
        point = _canvas_point(context, event)
        if item is None or point is None or not item.image_data:
            return {'CANCELLED'}
        uv = mm.canvas_to_uv(item, point)
        if uv is None:
            return {'CANCELLED'}
        self.start = _clamp_uv(uv)
        self.start_mouse = (event.mouse_region_x, event.mouse_region_y)
        mark = mm.add_mark(item, self.kind, self.start, self.start)
        self.mark_id = mark.measure_id
        if self.purpose == 'SCALE':
            mark.name = 'Scale'
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _mark(self, context):
        item = _item(get_settings(context), self.item_id)
        return item, (mm.find_mark(item, self.mark_id) if item is not None else None)

    def _discard(self, context):
        item, mark = self._mark(context)
        if item is not None and mark is not None:
            index = list(item.measures).index(mark)
            item.measures.remove(index)
            item.measure_active_index = max(0, min(item.measure_active_index,
                                                   len(item.measures) - 1))

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._discard(context)
            context.area.tag_redraw()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            from .ops_arrow import _canvas_point
            item, mark = self._mark(context)
            point = _canvas_point(context, event)
            if item is not None and mark is not None and point is not None:
                uv = mm.canvas_to_uv(item, point)
                if uv is not None:
                    end = _clamp_uv(uv)
                    if event.shift:
                        end = _constrained(item, self.start, end, self.kind)
                    mark.p1 = end
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            moved = math.dist(self.start_mouse, (event.mouse_region_x, event.mouse_region_y))
            item, mark = self._mark(context)
            if item is None or mark is None:
                return {'CANCELLED'}
            size = mm.mark_pixels(item, mark)
            tiny = (size < 1.0 if self.kind == 'LINE' else min(size) < 1.0)
            if moved < MIN_DRAG_PIXELS or tiny:
                self._discard(context)
                self.report({'INFO'}, 'Drag to draw a mark')
                context.area.tag_redraw()
                return {'CANCELLED'}
            context.area.tag_redraw()
            if self.purpose == 'SCALE':
                bpy.ops.kanvas.set_measure_scale('INVOKE_DEFAULT', item_id=self.item_id,
                                                 measure_id=self.mark_id)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._discard(context)


class KANVAS_OT_SetMeasureScale(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.set_measure_scale'
    bl_label = 'Set Scale'
    bl_description = ('Say how big the active mark really is: the image gets a scale, and '
                      'every mark of it, and its size in the 3D View, follows')
    bl_options = {'REGISTER', 'UNDO'}

    item_id: bpy.props.StringProperty(options={'SKIP_SAVE'})  # type: ignore
    measure_id: bpy.props.StringProperty(options={'SKIP_SAVE'})  # type: ignore
    value: bpy.props.FloatProperty(  # type: ignore
        name='Real Size', description='How big the mark really is',
        default=1.0, min=0.0001, soft_max=10000.0, precision=3)
    unit: bpy.props.EnumProperty(  # type: ignore
        name='Unit', items=mm.UNIT_ITEMS, default='CM')
    side: bpy.props.EnumProperty(  # type: ignore
        name='Side', items=mm.SIDE_ITEMS, default='LENGTH')

    @classmethod
    def poll(cls, context):
        item = _marked_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and bool(item.measures)

    def _target(self, context):
        settings = get_settings(context)
        item = _item(settings, self.item_id) if self.item_id else _marked_image(context)
        if item is None:
            return None, None
        if self.measure_id:
            return item, mm.find_mark(item, self.measure_id)
        if 0 <= item.measure_active_index < len(item.measures):
            return item, item.measures[item.measure_active_index]
        return item, None

    def invoke(self, context, event):
        item, mark = self._target(context)
        if mark is None:
            return {'CANCELLED'}
        self.item_id, self.measure_id = item.item_id, mark.measure_id
        settings = get_settings(context)
        if item.measure_scale_id == mark.measure_id:
            self.value, self.unit, self.side = mark.known_value, mark.known_unit, mark.known_side
        else:
            self.unit = settings.measure_unit
            self.side = mm.default_side(mark.kind)
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        item, mark = self._target(context)
        layout = self.layout
        if mark is None:
            return
        layout.label(text=f'How big is "{mark.name}" really?', icon='DRIVER_DISTANCE')
        if mark.kind == 'RECT':
            row = layout.row(align=True)
            row.prop_enum(self, 'side', 'HEIGHT')
            row.prop_enum(self, 'side', 'WIDTH')
        row = layout.row(align=True)
        row.prop(self, 'value', text='')
        row.prop(self, 'unit', text='')

    def execute(self, context):
        item, mark = self._target(context)
        if mark is None:
            return {'CANCELLED'}
        settings = get_settings(context)
        first = not any(other.measure_scale_id for other in settings.images
                        if other.item_type == 'IMAGE')
        side = self.side if mark.kind == 'RECT' else 'LENGTH'
        if not mm.set_scale(item, mark.measure_id, self.value, self.unit, side):
            self.report({'WARNING'}, 'The mark has no size to give a scale')
            return {'CANCELLED'}
        if first:
            settings.measure_unit = self.unit    # the board reads in what it was given
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_ClearMeasureScale(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.clear_measure_scale'
    bl_label = 'Clear Scale'
    bl_description = 'Take the scale off the image: its marks read in pixels again'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        item = _marked_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and bool(item.measure_scale_id)

    def execute(self, context):
        item = _marked_image(context)
        mm.clear_scale(item)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_RemoveMeasure(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.remove_measure'
    bl_label = 'Remove Mark'
    bl_description = 'Remove the active mark. If it was the scale, the image loses its scale'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        item = _marked_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and bool(item.measures)

    def execute(self, context):
        item = _marked_image(context)
        index = min(item.measure_active_index, len(item.measures) - 1)
        if item.measures[index].measure_id == item.measure_scale_id:
            mm.clear_scale(item)
        item.measures.remove(index)
        item.measure_active_index = max(0, min(index, len(item.measures) - 1))
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_ClearMeasures(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.clear_measures'
    bl_label = 'Clear All Marks'
    bl_description = 'Remove every mark of the active image, and its scale'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        item = _marked_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and bool(item.measures)

    def execute(self, context):
        item = _marked_image(context)
        item.measures.clear()
        mm.clear_scale(item)
        item.measure_active_index = 0
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}
