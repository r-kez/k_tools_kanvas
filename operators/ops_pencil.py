"""The pencil: strokes drawn with the mouse or a pen, kept together in a Pencil Drawing.

The first stroke with the pencil makes a Pencil Drawing; the strokes after it join the
same one while it is being drawn on (selected and `pencil_editing`). E on a drawing
draws on it again; Esc or E leaves. A drawing is one item of the item list however many
strokes it holds. The stroke is a short modal that lives only while the button is down.
"""

import numpy as np
import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils.kanvas_data import get_settings, unique_item_name

PENCIL_TOOL = 'kanvas.pencil'
EDIT_TOOL = 'kanvas.edit'


def is_pencil(item):
    return item.item_type == 'SHAPE' and item.shape_kind == 'PENCIL'


def drawing_in_progress(settings):
    """The Pencil Drawing taking strokes now: selected, unlocked, visible and on."""
    return next((item for item in settings.images
                 if is_pencil(item) and item.pencil_editing and item.is_selected
                 and not item.is_locked and item.show_in_editor), None)


def set_tool(context, name):
    try:
        bpy.ops.wm.tool_set_by_id(name=name, space_type='NODE_EDITOR')
    except RuntimeError:
        pass


def toggle_pencil_edit(context, settings):
    """E on a single selected Pencil Drawing: draw on it, or stop. The drawing, or None
    when E is not for the pencil."""
    current = drawing_in_progress(settings)
    if current is not None:
        current.pencil_editing = False
        set_tool(context, EDIT_TOOL)
        return current
    selected = [item for item in settings.images if item.is_selected]
    if len(selected) != 1 or not is_pencil(selected[0]):
        return None
    drawing = selected[0]
    if drawing.is_locked or not drawing.show_in_editor:
        return None
    drawing.pencil_editing = True
    set_tool(context, PENCIL_TOOL)
    return drawing


def leave_pencil_edit(context, settings):
    """Stop drawing on whatever is being drawn on. True when something was."""
    changed = False
    for item in settings.images:
        if item.item_type == 'SHAPE' and item.pencil_editing:
            item.pencil_editing = False
            for stroke in item.shape_strokes:
                stroke.selected = False
            changed = True
    return changed


def delete_picked_strokes(context, settings):
    """X or Delete with strokes picked: remove them, not the drawing. True when it did."""
    from ..utils import pencil
    removed = 0
    for item in settings.images:
        if is_pencil(item) and item.is_selected and not item.is_locked:
            removed += pencil.remove_selected_strokes(item)
    if removed and context.area:
        context.area.tag_redraw()
    return removed > 0


class KANVAS_OT_PencilPick(KanvasTreeOnly, bpy.types.Operator):
    """Ctrl+click with the pencil: pick the stroke under the pointer."""
    bl_idname = 'kanvas.pencil_pick'
    bl_label = 'Pick Pencil Stroke'
    bl_description = ('Pick a stroke of a Pencil Drawing: its color and width then follow the '
                      'pencil settings and Delete removes it. Shift adds to the picks')
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    extend: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})  # type: ignore

    DRAG_PIXELS = 4

    def invoke(self, context, event):
        """A short modal that lives only while the button is down: a click picks the
        stroke under the pointer, a drag draws a box and picks the strokes it touches."""
        region = context.region
        if region is None or region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        self._start = (event.mouse_region_x, event.mouse_region_y)
        self._dragging = False
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        region = context.region
        settings = get_settings(context)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end_box(context, settings)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            here = (event.mouse_region_x, event.mouse_region_y)
            if not self._dragging and np.hypot(here[0] - self._start[0],
                                               here[1] - self._start[1]) >= self.DRAG_PIXELS:
                self._dragging = True
                settings.box_sel_start = tuple(region.view2d.region_to_view(*self._start))
                settings.show_box_sel = True
            if self._dragging:
                settings.box_sel_end = tuple(region.view2d.region_to_view(*here))
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self._dragging:
                start, end = settings.box_sel_start, settings.box_sel_end
                self._end_box(context, settings)
                self._box(context, settings, start, end)
            else:
                self._pick(context, event)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._end_box(context, get_settings(context))

    def _end_box(self, context, settings):
        settings.show_box_sel = False
        if context.area:
            context.area.tag_redraw()

    def _activate(self, context, settings, drawing, current, drawings):
        """Make `drawing` the one drawn on, if it is not already."""
        from ..utils import pencil
        if current is None or drawing.item_id != current.item_id:
            leave_pencil_edit(context, settings)
            for item in settings.images:
                item.is_selected = False
            drawing.is_selected = True
            settings.active_image_index = next(
                i for i, item in enumerate(settings.images) if item.item_id == drawing.item_id)
            drawing.pencil_editing = True

    def _box(self, context, settings, start, end):
        from ..properties import show_pencil_style
        from ..utils import pencil
        low = (min(start[0], end[0]), min(start[1], end[1]))
        high = (max(start[0], end[0]), max(start[1], end[1]))
        current = drawing_in_progress(settings)
        drawings = [item for item in settings.images
                    if is_pencil(item) and item.show_in_editor and not item.is_locked]
        hits = {drawing.item_id: pencil.strokes_in_rect(drawing, low, high)
                for drawing in drawings}
        # The drawing being drawn on, else the one with most strokes in the box.
        chosen = None
        if current is not None and hits.get(current.item_id):
            chosen = current
        else:
            ranked = [d for d in drawings if hits[d.item_id]]
            if ranked:
                chosen = max(ranked, key=lambda d: len(hits[d.item_id]))
        if not self.extend:
            for drawing in drawings:
                pencil.clear_stroke_selection(drawing)
        if chosen is not None:
            self._activate(context, settings, chosen, current, drawings)
            last = None
            for index in hits[chosen.item_id]:
                chosen.shape_strokes[index].selected = True
                last = chosen.shape_strokes[index]
            if last is not None:
                show_pencil_style(settings, last)
        context.area.tag_redraw()

    def _pick(self, context, event):
        from ..properties import show_pencil_style
        from ..utils import pencil
        region = context.region
        settings = get_settings(context)
        point = region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        pixel = abs(region.view2d.region_to_view(1, 0)[0] - region.view2d.region_to_view(0, 0)[0])
        current = drawing_in_progress(settings)
        drawings = [item for item in settings.images
                    if is_pencil(item) and item.show_in_editor and not item.is_locked]
        # The drawing being drawn on wins a tie: it is the one in front of the user.
        drawings.sort(key=lambda item: 0 if current and item.item_id == current.item_id else 1)
        best = None
        for drawing in drawings:
            hit = pencil.pick_stroke(drawing, point, 8.0 * pixel)
            if hit is not None and (best is None or hit[1] < best[1] - 1e-6):
                best = (drawing, hit[1], hit[0])
        if best is None:
            if not self.extend:
                for drawing in drawings:
                    pencil.clear_stroke_selection(drawing)
            context.area.tag_redraw()
            return
        drawing, _, index = best
        self._activate(context, settings, drawing, current, drawings)
        if not self.extend:
            for other in drawings:
                pencil.clear_stroke_selection(other)
        stroke = drawing.shape_strokes[index]
        stroke.selected = not stroke.selected if self.extend else True
        if stroke.selected:
            show_pencil_style(settings, stroke)
        context.area.tag_redraw()
        return {'FINISHED'}


def picked_strokes_target(settings):
    """(drawing, indices) of the strokes picked in an unlocked drawing, or None."""
    from ..utils import pencil
    for item in settings.images:
        if is_pencil(item) and item.is_selected and not item.is_locked:
            indices = pencil.selected_strokes(item)
            if indices:
                return item, indices
    return None


class KANVAS_OT_PencilTransform(KanvasTreeOnly, bpy.types.Operator):
    """G, R or S on the picked strokes: move, rotate or scale them inside the drawing."""
    bl_idname = 'kanvas.pencil_transform'
    bl_label = 'Transform Pencil Strokes'
    bl_description = 'Move, rotate or scale the picked strokes of a Pencil Drawing'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    mode: bpy.props.EnumProperty(  # type: ignore
        items=[('MOVE', 'Move', ''), ('ROTATE', 'Rotate', ''), ('SCALE', 'Scale', '')],
        default='MOVE', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return super().poll(context) and picked_strokes_target(get_settings(context)) is not None

    def invoke(self, context, event):
        from ..utils import pencil
        region = context.region
        if region is None or region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        target = picked_strokes_target(get_settings(context))
        if target is None:
            return {'PASS_THROUGH'}
        self._item_id = target[0].item_id
        self._snapshot = pencil.strokes_snapshot(*target)
        self._pivot = pencil.snapshot_center(self._snapshot)
        self._start = tuple(region.view2d.region_to_view(event.mouse_region_x,
                                                         event.mouse_region_y))
        if self.mode != 'MOVE' and np.hypot(self._start[0] - self._pivot[0],
                                            self._start[1] - self._pivot[1]) < 1e-6:
            self._start = (self._start[0] + 1.0, self._start[1])
        context.workspace.status_text_set(
            f'{self.mode.title()} strokes  |  click or Enter: confirm  |  '
            'Esc or right-click: cancel  |  Ctrl: snap')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _item(self, settings):
        return next((i for i in settings.images if i.item_id == self._item_id), None)

    def _apply(self, context, event):
        from ..utils import pencil
        settings = get_settings(context)
        item = self._item(settings)
        if item is None:
            return False
        mouse = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        px, py = self._pivot
        sx, sy = self._start
        factor = 1.0
        if self.mode == 'MOVE':
            dx, dy = mouse[0] - sx, mouse[1] - sy
            if event.ctrl:
                grid = max(1.0, float(settings.grid_size)) * (0.1 if event.shift else 1.0)
                dx, dy = round(dx / grid) * grid, round(dy / grid) * grid
            offset = np.array([dx, dy])

            def place(points):
                return points + offset
        elif self.mode == 'ROTATE':
            angle = (np.arctan2(mouse[1] - py, mouse[0] - px) - np.arctan2(sy - py, sx - px))
            if event.ctrl:
                step = np.radians(1.0 if event.shift else 15.0)
                angle = round(angle / step) * step
            c, s = np.cos(angle), np.sin(angle)

            def place(points):
                x, y = points[:, 0] - px, points[:, 1] - py
                return np.stack([px + x * c - y * s, py + x * s + y * c], axis=1)
        else:
            base = np.hypot(sx - px, sy - py)
            factor = max(np.hypot(mouse[0] - px, mouse[1] - py) / base, 0.01) if base > 1e-9 else 1.0
            if event.ctrl:
                step = 0.01 if event.shift else 0.1
                factor = max(round(factor / step) * step, step)

            def place(points):
                return np.array([px, py]) + (points - np.array([px, py])) * factor
        pencil.transform_strokes(item, self._snapshot, place, factor if self.mode == 'SCALE' else 1.0)
        context.area.tag_redraw()
        return True

    def _restore(self, context):
        from ..utils import pencil
        item = self._item(get_settings(context))
        if item is not None:
            pencil.transform_strokes(item, self._snapshot, lambda points: points, 1.0)

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._restore(context)
            context.workspace.status_text_set(None)
            context.area.tag_redraw()
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._apply(context, event)
            return {'RUNNING_MODAL'}
        if (event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS'):
            self._apply(context, event)
            context.workspace.status_text_set(None)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        context.workspace.status_text_set(None)


class KANVAS_OT_PencilCursor(bpy.types.Operator):
    """On every mouse move (and Alt press or release) while the pencil or the eraser is the
    tool: remember where the pointer is, so its mark is drawn beside it, and set the pointer.
    Never modal; the event always goes on."""
    bl_idname = 'kanvas.pencil_cursor'
    bl_label = 'Pencil Cursor'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        space = getattr(context, 'space_data', None)
        tree = getattr(space, 'edit_tree', None) if space else None
        region = getattr(context, 'region', None)
        return (tree is not None and tree.bl_idname == 'KanvasNodeTree'
                and region is not None and region.type == 'WINDOW')

    def invoke(self, context, event):
        from .ops_modal import _event_in_canvas
        from ..utils import pencil
        if _event_in_canvas(context, event):
            pencil.set_hover(context.window, context.area, event.mouse_region_x,
                             event.mouse_region_y, event.alt)
            tool = context.workspace.tools.from_space_node()
            erasing = event.alt or (tool is not None and tool.idname == 'kanvas.eraser')
            context.window.cursor_set('DOT' if erasing else 'PAINT_CROSS')
        else:
            pencil.hover.pop(pencil.hover_key(context.window, context.area), None)
        context.area.tag_redraw()
        return {'PASS_THROUGH'}


class KANVAS_OT_PencilErase(KanvasTreeOnly, bpy.types.Operator):
    """Drag with the eraser: it rubs out the strokes where it passes."""
    bl_idname = 'kanvas.pencil_erase'
    bl_label = 'Erase Pencil Strokes'
    bl_description = 'Drag over strokes of a Pencil Drawing to rub them out where you pass'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        region = context.region
        if region is None or region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        settings = get_settings(context)
        view = region.view2d
        pixel = abs(view.region_to_view(1, 0)[0] - view.region_to_view(0, 0)[0])
        self._radius = settings.pencil_eraser_size * pixel
        context.window.cursor_set('DOT')
        self._last = None
        self._erased = 0
        self._step(context, event)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _drawings(self, settings):
        return [item for item in settings.images
                if is_pencil(item) and item.show_in_editor and not item.is_locked]

    def _step(self, context, event):
        """Erase along the way from the last position to this one, so a fast drag skips
        nothing."""
        from ..utils import pencil
        settings = get_settings(context)
        here = np.array(context.region.view2d.region_to_view(event.mouse_region_x,
                                                              event.mouse_region_y))
        last = here if self._last is None else self._last
        count = max(2, int(np.hypot(*(here - last)) / max(self._radius * 0.5, 1e-6)) + 2)
        along = last + (here - last) * np.linspace(0.0, 1.0, count)[:, None]
        for drawing in self._drawings(settings):
            self._erased += pencil.erase_parts(drawing, along, self._radius)
        self._last = here
        pencil.set_hover(context.window, context.area, event.mouse_region_x,
                         event.mouse_region_y, True)
        context.area.tag_redraw()

    def _finish(self, context):
        from .ops_shape import _remove_items
        settings = get_settings(context)
        # A drawing with no strokes left is nothing: take it off the board.
        empty = [item.item_id for item in settings.images
                 if is_pencil(item) and not len(item.shape_strokes)]
        if empty:
            _remove_items(context, settings, empty)
        context.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._step(context, event)
            return {'RUNNING_MODAL'}
        if ((event.type == 'LEFTMOUSE' and event.value == 'RELEASE')
                or (event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS')):
            self._finish(context)
            return {'FINISHED'} if self._erased else {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._finish(context)


class KANVAS_OT_PencilAttach(KanvasTreeOnly, bpy.types.Operator):
    """Stick the selected Pencil Drawing to the image under its middle."""
    bl_idname = 'kanvas.pencil_attach'
    bl_label = 'Stick to Image'
    bl_description = ('Stick the drawing to the image under its middle: it then moves, '
                      'rotates and scales with the image')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return super().poll(context) and _selected_drawings(get_settings(context)) != []

    def execute(self, context):
        from ..utils import pencil_anchor, shape_geometry
        settings = get_settings(context)
        done = 0
        for drawing in _selected_drawings(settings):
            corners = shape_geometry.box_corners(drawing)
            middle = (sum(p[0] for p in corners) / 4.0, sum(p[1] for p in corners) / 4.0)
            image = pencil_anchor.image_under_point(settings, middle)
            if image is not None:
                pencil_anchor.attach(drawing, image)
                done += 1
        if not done:
            self.report({'WARNING'}, 'No image under the middle of the drawing')
            return {'CANCELLED'}
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_PencilDetach(KanvasTreeOnly, bpy.types.Operator):
    """Let the selected Pencil Drawing go: it stays where it is."""
    bl_idname = 'kanvas.pencil_detach'
    bl_label = 'Detach from Image'
    bl_description = 'Let the drawing go: it stays where it is and no longer follows the image'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return super().poll(context) and any(
            item.anchor_item_id for item in _selected_drawings(get_settings(context)))

    def execute(self, context):
        from ..utils import pencil_anchor
        for drawing in _selected_drawings(get_settings(context)):
            pencil_anchor.detach(drawing)
        context.area.tag_redraw()
        return {'FINISHED'}


def _selected_drawings(settings):
    return [item for item in settings.images if is_pencil(item) and item.is_selected]


class KANVAS_OT_StartPencil(KanvasTreeOnly, bpy.types.Operator):
    """Pick the pencil: the next stroke starts a new Pencil Drawing."""
    bl_idname = 'kanvas.start_pencil'
    bl_label = 'Pencil Drawing'
    bl_description = ('Pick the pencil: drag on the canvas to draw. The first stroke makes a '
                      'Pencil Drawing and the strokes after it join it')

    def execute(self, context):
        settings = get_settings(context)
        leave_pencil_edit(context, settings)
        for item in settings.images:
            item.is_selected = False
        set_tool(context, PENCIL_TOOL)
        return {'FINISHED'}


class KANVAS_OT_PencilStroke(KanvasTreeOnly, bpy.types.Operator):
    """Draw one pencil stroke: drag, with pressure from a pen."""
    bl_idname = 'kanvas.pencil_stroke'
    bl_label = 'Pencil Stroke'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    loose: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})  # type: ignore

    def invoke(self, context, event):
        region = context.region
        if region is None or region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        self._points = []
        self._pixel = abs(region.view2d.region_to_view(1, 0)[0]
                          - region.view2d.region_to_view(0, 0)[0])
        settings = get_settings(context)
        self._color = tuple(settings.pencil_color)
        self._width = settings.pencil_width
        self._pen = (settings.pencil_use_pressure, settings.pencil_pressure_min,
                     settings.pencil_pressure_curve)
        self._add(region, event, force=True)
        self._show()
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _add(self, region, event, force=False):
        x, y = region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        pressure = event.pressure if event.pressure > 0.0 else 1.0
        from ..utils import pencil
        pencil.set_hover(bpy.context.window, bpy.context.area, event.mouse_region_x,
                         event.mouse_region_y, False)
        if self._points and not force:
            last = self._points[-1]
            if np.hypot(x - last[0], y - last[1]) < self._pixel * 1.5:
                return False
        self._points.append((x, y, pressure))
        return True

    def _show(self):
        from ..utils import pencil
        points = np.array(self._points, dtype=np.float64)
        points[:, 2] = pencil.apply_pressure(points[:, 2], *self._pen)
        pencil.live.update(points=points, color=self._color, width=self._width)

    def _hide(self, context):
        from ..utils import pencil
        pencil.live['points'] = None
        if context.area:
            context.area.tag_redraw()

    def modal(self, context, event):
        region = context.region
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._hide(context)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if self._add(region, event):
                self._show()
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._add(region, event)
            self._hide(context)
            return self._commit(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._hide(context)

    def _commit(self, context):
        from ..utils import pencil
        settings = get_settings(context)
        points = np.array(self._points, dtype=np.float32)
        points = pencil.smoothed(points, settings.pencil_smoothing)
        points[:, 2] = pencil.apply_pressure(points[:, 2], *self._pen)
        drawing = drawing_in_progress(settings)
        if drawing is None:
            drawing = self._new_drawing(context, settings, points)
        pencil.add_stroke(drawing, points[:, :2], points[:, 2], self._color, self._width)
        context.area.tag_redraw()
        return {'FINISHED'}

    def _new_drawing(self, context, settings, points):
        from .ops_shape import new_shape
        from ..utils import pencil
        leave_pencil_edit(context, settings)
        center = points[:, :2].mean(axis=0)
        drawing = new_shape(context, settings, 'PENCIL', (float(center[0]), float(center[1])),
                            pencil.MIN_BOX, pencil.MIN_BOX)
        drawing.name = unique_item_name(settings, 'Pencil Drawing')
        drawing.shape_show_fill = False
        drawing.shape_show_outline = False
        drawing.pencil_editing = True
        if settings.pencil_attach and not self.loose:
            from ..utils import pencil_anchor
            image = pencil_anchor.image_under_point(settings, (float(points[0, 0]),
                                                               float(points[0, 1])))
            if image is not None:
                pencil_anchor.attach(drawing, image)
        return drawing
