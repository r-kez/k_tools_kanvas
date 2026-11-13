"""Hand cursor for Move mode, without any modal operator.

A modal operator that stays alive blocks Blender's auto save, so the cursor is
set by a one-shot operator bound to MOUSEMOVE. The binding is only active while
some Kanvas tree is in Move mode (see keymap.sync_hand_cursor).
"""

import bpy

# Windows whose pointer is held as a hand by a modal cursor. Blender puts its own cursor back
# after each mouse move, which made a plain `cursor_set` flicker between hand and arrow; a
# modal cursor stays until restored. `kanvas.hand_hover` (bound in the Window keymap, so it
# also sees the pointer leave the canvas) sets and restores it.
_hand_windows = {}


def _over_move_canvas(window, x, y):
    """True when (x, y) in window pixels is on the canvas of a board in Move mode."""
    from .ops_modal import _shape_armed_areas
    for area in window.screen.areas:
        if area.type != 'NODE_EDITOR':
            continue
        tree = getattr(area.spaces.active, 'edit_tree', None)
        if (tree is None or tree.bl_idname != 'KanvasNodeTree'
                or tree.kanvas_settings.canvas_mode != 'MOVE'
                or (window.as_pointer(), area.as_pointer()) in _shape_armed_areas):
            continue
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if region is None or not (region.x <= x < region.x + region.width
                                  and region.y <= y < region.y + region.height):
            continue
        # The toolbar, sidebar and header can overlap the canvas.
        if not any(r.type != 'WINDOW' and r.width > 1 and r.height > 1
                   and r.x <= x < r.x + r.width and r.y <= y < r.y + r.height
                   for r in area.regions):
            return True
    return False


def _set_hand(window, cursor):
    window.cursor_modal_set(cursor)
    _hand_windows[window.as_pointer()] = window


def _drop_hand(window):
    if _hand_windows.pop(window.as_pointer(), None) is not None:
        try:
            window.cursor_modal_restore()
        except (ReferenceError, RuntimeError):
            pass


def refresh_hand(window, x, y):
    """The open hand while the pointer is over a Move mode canvas, the usual cursor elsewhere."""
    if _over_move_canvas(window, x, y):
        _set_hand(window, 'HAND')
    else:
        _drop_hand(window)


def release_all():
    for window in tuple(_hand_windows.values()):
        _drop_hand(window)
    _hand_windows.clear()


class KANVAS_OT_HandHover(bpy.types.Operator):
    """On every mouse move while a board is in Move mode: the open hand over its canvas.
    Never modal; the event always goes on."""
    bl_idname = 'kanvas.hand_hover'
    bl_label = 'Move Mode Hand'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if context.window is not None:
            refresh_hand(context.window, event.mouse_x, event.mouse_y)
        return {'PASS_THROUGH'}


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
        _set_hand(self._window, 'HAND_CLOSED')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, event):
        try:
            refresh_hand(self._window, event.mouse_x, event.mouse_y)
        except (ReferenceError, RuntimeError):
            pass
        return {'CANCELLED'}

    def modal(self, context, event):
        if event.type in {'LEFTMOUSE', 'ESC'} and event.value == 'RELEASE' \
                or event.type == 'ESC' and event.value == 'PRESS':
            return self._end(event)
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
        return {'PASS_THROUGH'}
