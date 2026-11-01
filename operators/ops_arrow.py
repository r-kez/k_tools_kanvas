"""Create and edit free or attached Kanvas arrows."""

import math
import uuid

import bpy
from ..utils.kanvas_data import get_settings, unique_item_name

from .kanvas_context import KanvasTreeOnly
from ..utils.arrow_geometry import (
    anchor_candidate, endpoint, set_endpoint,
)


def _canvas_point(context, event):
    """Read a canvas coordinate even when the operator starts in the sidebar."""
    area = context.area
    if area is None:
        return None
    region = next((part for part in area.regions if part.type == 'WINDOW'), None)
    if region is None:
        return None
    x, y = event.mouse_x, event.mouse_y
    if not (region.x <= x < region.x + region.width
            and region.y <= y < region.y + region.height):
        return None
    for part in area.regions:
        if (part.type != 'WINDOW' and part.width > 1 and part.height > 1
                and part.x <= x < part.x + part.width
                and part.y <= y < part.y + part.height):
            return None
    return region.view2d.region_to_view(x - region.x, y - region.y)


def _pixel_size(context):
    region = next((part for part in context.area.regions
                   if part.type == 'WINDOW'), None)
    if region is None:
        return 1.0
    view = region.view2d
    return abs(view.region_to_view(1, 0)[0] - view.region_to_view(0, 0)[0])


def _set_hover(settings, candidate):
    settings.arrow_hover_valid = candidate is not None
    settings.arrow_hover_item_id = candidate[0] if candidate else ''
    if candidate is not None:
        settings.arrow_hover = candidate[2]


def _header_hint(context, text):
    if context.area and hasattr(context.area, 'header_text_set'):
        context.area.header_text_set(text)


def _create_arrow(settings, center):
    for item in settings.images:
        item.is_selected = False
    settings.active_image_index = -1
    arrow_name = unique_item_name(settings, 'Arrow')
    arrow = settings.arrows.add()
    arrow.arrow_id = uuid.uuid4().hex
    arrow.name = arrow_name
    from ..utils.gpu.gpu_common import get_prefs
    prefs = get_prefs()
    if prefs and prefs.arrow_style == 'ROUNDED':
        arrow.thickness = 8.0
    arrow.start = (center[0] - 70.0, center[1] + 30.0)
    arrow.end = (center[0] + 70.0, center[1] - 30.0)
    settings.active_arrow_index = len(settings.arrows) - 1
    return arrow


class KANVAS_OT_CreateArrow(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.create_arrow'
    bl_label = 'Add Arrow'
    bl_description = 'Place a free arrow; click its endpoints to attach them to cards or images'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _create_arrow(get_settings(context), (0.0, 0.0))
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        settings = get_settings(context)
        from ..utils.gpu import ensure_item_ids
        ensure_item_ids(settings)
        region = next((part for part in context.area.regions
                       if part.type == 'WINDOW'), None)
        if region is None:
            return self.execute(context)
        center = region.view2d.region_to_view(region.width * 0.5,
                                              region.height * 0.5)
        self.arrow = _create_arrow(settings, center)
        self.arrow_id = self.arrow.arrow_id
        self.phase = 'START'
        settings.arrow_dragging = True
        settings.arrow_hover_valid = False
        _header_hint(context, 'Arrow: click the starting point, or Esc to cancel')
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        settings = get_settings(context)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        point = _canvas_point(context, event)
        if point is None:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        candidate = anchor_candidate(settings, point, _pixel_size(context))
        _set_hover(settings, candidate)
        snapped = candidate[2] if candidate else point
        if event.type == 'MOUSEMOVE':
            if self.phase == 'START':
                self.arrow.start = snapped
                self.arrow.end = (snapped[0] + 100.0 * _pixel_size(context),
                                  snapped[1] - 30.0 * _pixel_size(context))
            else:
                set_endpoint(self.arrow, 'end', snapped, candidate)
            context.area.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self.phase == 'START':
                set_endpoint(self.arrow, 'start', snapped, candidate)
                self.arrow.end = (snapped[0] + 100.0 * _pixel_size(context),
                                  snapped[1] - 30.0 * _pixel_size(context))
                self.phase = 'END'
            else:
                if math.dist(endpoint(settings, self.arrow, 'start'), snapped) \
                        < 8.0 * _pixel_size(context):
                    return {'RUNNING_MODAL'}
                set_endpoint(self.arrow, 'end', snapped, candidate)
                from .ops_checklist import associate_arrow_endpoints
                associate_arrow_endpoints(settings, self.arrow)
                settings.arrow_dragging = False
                settings.arrow_hover_valid = False
                _header_hint(context, None)
                context.area.tag_redraw()
                return {'FINISHED'}
            _header_hint(context, 'Arrow: click the end point; hover a card or image to attach')
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        settings = get_settings(context)
        index = next((i for i, arrow in enumerate(settings.arrows)
                      if arrow.arrow_id == getattr(self, 'arrow_id', '')), None)
        if index is not None:
            settings.arrows.remove(index)
            settings.active_arrow_index = min(index, len(settings.arrows) - 1)
        settings.arrow_dragging = False
        settings.arrow_hover_valid = False
        _header_hint(context, None)
        if context.area:
            context.area.tag_redraw()


class KANVAS_OT_QuickArrow(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.quick_arrow'
    bl_label = 'Quick Arrow'
    bl_description = 'Hold the shortcut and drag from a free point or anchor to create an attached arrow'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (KanvasTreeOnly.poll(context)
                and getattr(context, 'region', None) is not None
                and context.region.type == 'WINDOW')

    def invoke(self, context, event):
        settings = get_settings(context)
        if settings.arrow_quick_active:
            return {'CANCELLED'}
        from ..utils.gpu import ensure_item_ids
        ensure_item_ids(settings)
        self._area = context.area
        self._settings = settings
        self._hold_key = event.type
        self._key_held = True
        self._pressed = False
        self._arrow_id = ''
        self._start = None
        self._press_point = None
        self._start_candidate = None
        self._saved_selection = [item.item_id for item in settings.images if item.is_selected]
        self._saved_active_image = settings.active_image_index
        self._saved_active_arrow = settings.active_arrow_index
        settings.arrow_quick_active = True
        settings.arrow_dragging = True
        settings.arrow_hover_valid = False
        _header_hint(context, 'Quick Arrow: hold key and drag from an anchor or free point; release key to finish')
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _current_arrow(self):
        if not self._arrow_id:
            return None
        return next((arrow for arrow in self._settings.arrows
                     if arrow.arrow_id == self._arrow_id), None)

    def _cancel_current(self):
        if not self._arrow_id:
            return
        for index, arrow in enumerate(self._settings.arrows):
            if arrow.arrow_id == self._arrow_id:
                self._settings.arrows.remove(index)
                break
        self._arrow_id = ''
        selected = set(self._saved_selection)
        for item in self._settings.images:
            item.is_selected = item.item_id in selected
        self._settings.active_image_index = self._saved_active_image
        self._settings.active_arrow_index = self._saved_active_arrow

    def _finish(self, context):
        self._cancel_current()
        self._settings.arrow_quick_active = False
        self._settings.arrow_dragging = False
        self._settings.arrow_hover_valid = False
        self._settings.arrow_hover_item_id = ''
        _header_hint(context, None)
        self._area.tag_redraw()
        return {'FINISHED'}

    def modal(self, context, event):
        if context.area != self._area:
            return self._finish(context)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._finish(context)
        if event.type == self._hold_key:
            if event.value == 'RELEASE':
                self._key_held = False
                if not self._pressed:
                    return self._finish(context)
            return {'RUNNING_MODAL'}
        if event.type == 'MIDDLEMOUSE':
            if event.value == 'PRESS':
                self._pressed = False
                self._cancel_current()
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE',
                          'WHEELOUTMOUSE', 'WHEELLEFTMOUSE', 'WHEELRIGHTMOUSE', 'TRACKPADPAN',
                          'TRACKPADZOOM', 'MOUSEROTATE', 'MOUSESMARTZOOM', 'NDOF_MOTION'}:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        if event.type not in {'LEFTMOUSE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            return {'RUNNING_MODAL'}

        point = _canvas_point(context, event)
        if point is None:
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._pressed = False
                self._cancel_current()
                if not self._key_held:
                    return self._finish(context)
            _set_hover(self._settings, None)
            self._area.tag_redraw()
            return ({'RUNNING_MODAL', 'PASS_THROUGH'}
                    if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}
                    else {'RUNNING_MODAL'})
        candidate = anchor_candidate(self._settings, point, _pixel_size(context))
        snapped = candidate[2] if candidate else point
        _set_hover(self._settings, candidate)

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._saved_selection = [item.item_id for item in self._settings.images if item.is_selected]
            self._saved_active_image = self._settings.active_image_index
            self._saved_active_arrow = self._settings.active_arrow_index
            self._pressed = True
            self._start = snapped
            self._press_point = point
            self._start_candidate = candidate
        elif event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} and self._pressed:
            if not self._arrow_id and math.dist(self._press_point, point) >= 3.0 * _pixel_size(context):
                arrow = _create_arrow(self._settings, self._start)
                self._arrow_id = arrow.arrow_id
                set_endpoint(arrow, 'start', self._start, self._start_candidate)
                set_endpoint(arrow, 'end', snapped, candidate)
            elif self._arrow_id:
                arrow = self._current_arrow()
                if arrow:
                    set_endpoint(arrow, 'end', snapped, candidate)
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._pressed = False
            arrow = self._current_arrow()
            if arrow:
                if math.dist(endpoint(self._settings, arrow, 'start'), snapped) < 8.0 * _pixel_size(context):
                    self._cancel_current()
                else:
                    set_endpoint(arrow, 'end', snapped, candidate)
                    from .ops_checklist import associate_arrow_endpoints
                    associate_arrow_endpoints(self._settings, arrow)
                    self._arrow_id = ''
            self._start = None
            self._press_point = None
            self._start_candidate = None
            if not self._key_held:
                return self._finish(context)
        self._area.tag_redraw()
        return ({'RUNNING_MODAL', 'PASS_THROUGH'}
                if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} and not self._pressed
                else {'RUNNING_MODAL'})

    def cancel(self, context):
        self._finish(context)


class KANVAS_OT_DragArrow(KanvasTreeOnly, bpy.types.Operator):
    """Drag an arrow body, endpoint, or curvature handle on the canvas."""
    bl_idname = 'kanvas.drag_arrow'
    bl_label = 'Move Arrow'
    bl_description = 'Drag the arrow body, endpoint, or curvature handle'
    bl_options = {'REGISTER', 'UNDO'}

    arrow_index: bpy.props.IntProperty(default=-1)  # type: ignore
    part: bpy.props.EnumProperty(items=[
        ('start', 'Start', ''), ('end', 'End', ''),
        ('curve', 'Curve', ''), ('body', 'Body', '')
    ])  # type: ignore

    def invoke(self, context, event):
        settings = get_settings(context)
        if not 0 <= self.arrow_index < len(settings.arrows):
            return {'CANCELLED'}
        if settings.arrows[self.arrow_index].is_locked:
            return {'CANCELLED'}
        point = _canvas_point(context, event)
        if point is None:
            return {'CANCELLED'}
        self.arrow = settings.arrows[self.arrow_index]
        if self.part == 'body' and not self.arrow.is_selected:
            self.arrow.is_selected = True
        from ..properties import suspend_selection_updates
        with suspend_selection_updates():
            settings.active_image_index = -1
            settings.active_arrow_index = self.arrow_index
        self.initial_mouse = point
        self.initial_start = endpoint(settings, self.arrow, 'start')
        self.initial_end = endpoint(settings, self.arrow, 'end')
        self.initial_curve_offset = tuple(self.arrow.curve_offset)
        self.saved = {
            side: (tuple(getattr(self.arrow, side)),
                   getattr(self.arrow, side + '_item_id'),
                   tuple(getattr(self.arrow, side + '_uv')),
                   getattr(self.arrow, side + '_line_id'))
            for side in ('start', 'end')
        }
        self.mixed_items = ([(item, tuple(item.location)) for item in settings.images
                             if item.is_selected and not item.is_locked
                             and item.show_in_editor and item.item_type in {'IMAGE', 'TEXT'}]
                            if self.part == 'body' else [])
        from ..utils.arrow_geometry import capture_selected_arrow_move
        self.body_saved = (capture_selected_arrow_move(
            settings, (item.item_id for item, _ in self.mixed_items))
            if self.part == 'body' else [])
        self.moved = False
        settings.arrow_dragging = True
        settings.arrow_hover_valid = False
        hint = ('Moving the arrow detaches its ends; release near a card or image to attach'
                if self.part == 'body' else
                'Drag the middle handle to bend the arrow'
                if self.part == 'curve' else
                'Drag the arrow end to a card or image; release to attach')
        _header_hint(context, hint)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _finish(self, context, cancelled):
        settings = get_settings(context)
        if cancelled:
            self.arrow.curve_offset = self.initial_curve_offset
            if self.part == 'body':
                from ..utils.arrow_geometry import restore_selected_arrows
                for item, location in self.mixed_items:
                    item.location = location
                restore_selected_arrows(self.body_saved)
            else:
                for side, (point, item_id, uv, line_id) in self.saved.items():
                    setattr(self.arrow, side, point)
                    setattr(self.arrow, side + '_item_id', item_id)
                    setattr(self.arrow, side + '_uv', uv)
                    setattr(self.arrow, side + '_line_id', line_id)
        elif self.moved:
            from .ops_checklist import associate_arrow_endpoints
            if self.part == 'body':
                for arrow, sides in self.body_saved:
                    if any(getattr(arrow, side + '_item_id') != state['item_id']
                           for side, state in sides.items()):
                        associate_arrow_endpoints(settings, arrow)
            elif self.part in {'start', 'end'}:
                if any(getattr(self.arrow, side + '_item_id') != state[1]
                       for side, state in self.saved.items()):
                    associate_arrow_endpoints(settings, self.arrow)
        if self.part == 'body' and self.mixed_items:
            from ..utils.gpu import update_frame_bounds
            for frame_name in {item.parent_frame for item, _ in self.mixed_items
                               if item.parent_frame}:
                update_frame_bounds(None, settings, frame_name)
        settings.arrow_dragging = False
        settings.arrow_hover_valid = False
        _header_hint(context, None)
        context.area.tag_redraw()
        return {'CANCELLED'} if cancelled else {'FINISHED'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._finish(context, True)
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        point = _canvas_point(context, event)
        if point is not None and event.type == 'MOUSEMOVE':
            settings = get_settings(context)
            if math.dist(point, self.initial_mouse) > 2.0 * _pixel_size(context):
                self.moved = True
            if self.moved:
                if self.part == 'body':
                    delta = (point[0] - self.initial_mouse[0],
                             point[1] - self.initial_mouse[1])
                    for item, location in self.mixed_items:
                        item.location = (location[0] + delta[0],
                                         location[1] + delta[1])
                    from ..utils.arrow_geometry import translate_selected_arrows
                    translate_selected_arrows(self.body_saved, *delta)
                    if self.mixed_items:
                        from ..utils.gpu import update_frame_bounds
                        for frame_name in {item.parent_frame for item, _ in self.mixed_items
                                           if item.parent_frame}:
                            update_frame_bounds(None, settings, frame_name)
                    settings.arrow_hover_valid = False
                elif self.part == 'curve':
                    self.arrow.curve_offset = (
                        self.initial_curve_offset[0] + point[0] - self.initial_mouse[0],
                        self.initial_curve_offset[1] + point[1] - self.initial_mouse[1])
                    settings.arrow_hover_valid = False
                else:
                    candidate = anchor_candidate(settings, point, _pixel_size(context))
                    _set_hover(settings, candidate)
                    set_endpoint(self.arrow, self.part,
                                 candidate[2] if candidate else point, candidate)
            context.area.tag_redraw()
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.part == 'body' and self.moved:
                settings = get_settings(context)
                for arrow, sides in self.body_saved:
                    for side, state in sides.items():
                        if state['follows']:
                            continue
                        free_point = tuple(getattr(arrow, side))
                        candidate = anchor_candidate(settings, free_point,
                                                     _pixel_size(context))
                        if candidate:
                            set_endpoint(arrow, side, candidate[2], candidate)
            return self._finish(context, False)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._finish(context, True)


class KANVAS_OT_RemoveArrow(KanvasTreeOnly, bpy.types.Operator):
    """Remove the active unlocked arrow from this Kanvas board."""
    bl_idname = 'kanvas.remove_arrow'
    bl_label = 'Remove Arrow'
    bl_description = 'Remove selected unlocked arrows'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = get_settings(context)
        indices = [i for i, arrow in enumerate(settings.arrows)
                   if arrow.is_selected and not arrow.is_locked]
        if not indices and 0 <= settings.active_arrow_index < len(settings.arrows):
            if not settings.arrows[settings.active_arrow_index].is_locked:
                indices = [settings.active_arrow_index]
        if not indices:
            return {'CANCELLED'}
        for index in reversed(indices):
            settings.arrows.remove(index)
        from ..properties import suspend_selection_updates
        with suspend_selection_updates():
            settings.active_arrow_index = next(
                (i for i, arrow in enumerate(settings.arrows) if arrow.is_selected), -1)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_ResetArrowCurvature(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.reset_arrow_curvature'
    bl_label = 'Reset Curvature'
    bl_description = 'Straighten the selected arrow without changing its endpoints'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return (0 <= settings.active_arrow_index < len(settings.arrows)
                and not settings.arrows[settings.active_arrow_index].is_locked)

    def execute(self, context):
        settings = get_settings(context)
        arrow = settings.arrows[settings.active_arrow_index]
        if tuple(arrow.curve_offset) == (0.0, 0.0):
            return {'CANCELLED'}
        arrow.curve_offset = (0.0, 0.0)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_DetachArrowEnd(KanvasTreeOnly, bpy.types.Operator):
    """Free an anchored arrow endpoint while keeping it in place."""
    bl_idname = 'kanvas.detach_arrow_end'
    bl_label = 'Detach Arrow End'
    bl_description = 'Detach one arrow endpoint while keeping its current position'
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(items=[
        ('start', 'Start', ''), ('end', 'End', '')
    ])  # type: ignore

    def execute(self, context):
        settings = get_settings(context)
        index = settings.active_arrow_index
        if not 0 <= index < len(settings.arrows):
            return {'CANCELLED'}
        arrow = settings.arrows[index]
        if arrow.is_locked:
            return {'CANCELLED'}
        set_endpoint(arrow, self.side, endpoint(settings, arrow, self.side))
        context.area.tag_redraw()
        return {'FINISHED'}
