"""Hand cursor for Move mode, without any modal operator.

A modal operator that stays alive blocks Blender's auto save, so the cursor is
set by a one-shot operator bound to MOUSEMOVE. The binding is only active while
some Kanvas tree is in Move mode (see keymap.sync_hand_cursor).
"""

import bpy


class KANVAS_OT_HandPan(bpy.types.Operator):
    """Pan with the left button in Move mode.

    Modal only while the button is held. It consumes every mouse event, so
    Blender's own click-drag selection can never start, and it shows the hand
    from the very first moment of the press.
    """

    bl_idname = 'kanvas.hand_pan'
    bl_label = 'Pan Canvas'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self._area = context.area
        self._window = context.window
        self._region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if self._region is None:
            return {'PASS_THROUGH'}
        self._last = (event.mouse_x, event.mouse_y)
        self._window.cursor_modal_set('HAND')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self):
        try:
            self._window.cursor_modal_restore()
        except (ReferenceError, RuntimeError):
            pass
        return {'CANCELLED'}

    def modal(self, context, event):
        if event.type in {'LEFTMOUSE', 'ESC'} and event.value == 'RELEASE' \
                or event.type == 'ESC' and event.value == 'PRESS':
            return self._end()
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            dx = event.mouse_x - self._last[0]
            dy = event.mouse_y - self._last[1]
            self._last = (event.mouse_x, event.mouse_y)
            if dx or dy:
                with context.temp_override(window=self._window, area=self._area,
                                           region=self._region):
                    if bpy.ops.view2d.pan.poll():
                        bpy.ops.view2d.pan(deltax=-dx, deltay=-dy)
                self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE':
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL', 'PASS_THROUGH'}


class KANVAS_OT_HandCursor(bpy.types.Operator):
    bl_idname = 'kanvas.hand_cursor'
    bl_label = 'Move Mode Cursor'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        space = getattr(context, 'space_data', None)
        tree = getattr(space, 'edit_tree', None) if space else None
        region = getattr(context, 'region', None)
        return (tree is not None and tree.bl_idname == 'KanvasNodeTree'
                and region is not None and region.type == 'WINDOW'
                and (tree.kanvas_settings.canvas_mode == 'MOVE'
                     or cls._shape_armed(context)))

    @staticmethod
    def _shape_armed(context):
        from .ops_modal import _shape_armed_areas
        return (context.window.as_pointer(),
                context.area.as_pointer()) in _shape_armed_areas

    def invoke(self, context, event):
        from .ops_modal import _event_in_canvas
        from ..utils.gpu import gpu_shape_cursor
        inside = _event_in_canvas(context, event)
        key = gpu_shape_cursor.area_key(context.window, context.area)
        if self._shape_armed(context):
            if inside:
                gpu_shape_cursor.positions[key] = (event.mouse_region_x,
                                                   event.mouse_region_y)
            else:
                gpu_shape_cursor.positions.pop(key, None)
            context.area.tag_redraw()
        if inside and context.space_data.edit_tree.kanvas_settings.canvas_mode == 'MOVE':
            context.window.cursor_set('HAND')
        return {'PASS_THROUGH'}
