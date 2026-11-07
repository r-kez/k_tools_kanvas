"""Paint an instance-specific image mask on the Kanvas canvas."""

import math
import time

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .kanvas_context import KanvasTreeOnly
from ..utils.arrow_geometry import image_uv_at, image_point_from_uv
from ..utils.gpu.gpu_theme import draw_rounded_fill, draw_rounded_border
from ..utils.gpu.gpu_shortcuts import (
    BADGE_ALERT, BADGE_NORMAL, PANEL_STATE, draw_mode_badge, draw_shortcut_panel)
from ..utils.kanvas_data import get_settings


_active_painters = []


def clear_stale_paint_state(tree):
    """Recover paint flags left behind by script reloads that lost their modal."""
    active = {(state.get('item_id'), state.get('editing_attr', 'mask_editing'))
              for state in _active_painters if state.get('tree') == tree}
    for item in tree.kanvas_settings.images:
        if item.mask_editing and (item.item_id, 'mask_editing') not in active:
            item.mask_editing = False
        if item.markup_editing and (item.item_id, 'markup_editing') not in active:
            item.markup_editing = False


def _release_painter(state):
    """Release a draw callback even if Blender already invalidated its operator."""
    handler = state.get('handler')
    state['handler'] = None
    if handler is not None:
        try:
            bpy.types.SpaceNodeEditor.draw_handler_remove(handler, 'WINDOW')
        except (ReferenceError, RuntimeError, ValueError):
            pass
    try:
        item = next((item for item in state['tree'].kanvas_settings.images
                     if item.item_id == state['item_id']), None)
        if item is not None:
            setattr(item, state.get('editing_attr', 'mask_editing'), False)
    except (ReferenceError, RuntimeError, KeyError):
        pass
    if state in _active_painters:
        _active_painters.remove(state)
    state['painter'] = None


def _draw_painter(state):
    painter = state.get('painter')
    if painter is None:
        return
    try:
        painter._draw_cursor()
    except ReferenceError:
        _release_painter(state)


def _active_image(context):
    settings = get_settings(context)
    if settings and 0 <= settings.active_image_index < len(settings.images):
        item = settings.images[settings.active_image_index]
        if item.item_type == 'IMAGE' and item.image_data:
            return item
    return None


def _next_mask_sequence(item):
    sequence = item.mask_next_sequence
    item.mask_next_sequence = sequence + 1
    return sequence


def _dab_snapshot(dab):
    return (tuple(dab.uv), tuple(dab.radius_uv),
            tuple(dab.uv_axis_x), tuple(dab.uv_axis_y),
            bool(dab.erase), int(dab.sequence))


def _restore_dab(dabs, snapshot):
    dab = dabs.add()
    dab.uv, dab.radius_uv, dab.uv_axis_x, dab.uv_axis_y = snapshot[:4]
    dab.erase, dab.sequence = snapshot[4:]


def _polygon_snapshot(polygon):
    return (tuple(tuple(vertex.uv) for vertex in polygon.vertices),
            bool(polygon.erase), int(polygon.sequence))


def _restore_polygon(polygons, snapshot):
    polygon = polygons.add()
    polygon.erase, polygon.sequence = snapshot[1:]
    for uv in snapshot[0]:
        polygon.vertices.add().uv = uv


def _effective_mask_erase(item, alt_held=False):
    return bool(item.mask_erase) != bool(alt_held)


_TOOL_TITLES = {'AUTO': 'Auto Select'}

# Shared by Mask and Color modes; survives between edit sessions.
_shortcut_panel = PANEL_STATE


def _mask_indicator_text(item, alt_held=False, mode_name='MASK MODE', sample_held=False):
    if sample_held:
        color = (f'  |  {item._markup_name}' if getattr(item, '_is_markup', False)
                 else '')
        return f'{mode_name}{color}  |  Pick Mask (S)'
    mode = ('Erase' if _effective_mask_erase(item, alt_held)
            else 'Paint' if getattr(item, '_is_markup', False) else 'Reveal')
    if alt_held:
        mode += ' (Alt)'
    color = (f'  |  {item._markup_name}' if getattr(item, '_is_markup', False)
             else '')
    tool = _TOOL_TITLES.get(item.mask_tool, item.mask_tool.title())
    return f'{mode_name}{color}  |  {tool}  |  {mode}'


def _mask_shortcut_rows(item, compact=False, color_mode=False):
    if item.mask_tool == 'POLYGON':
        tool_rows = (
            ('Click', 'Add vertex'),
            ('Shift', 'Snap edge to 45°'),
            ('Double-click / Enter', 'Close polygon'),
            ('Esc', 'Cancel polygon'),
        )
    elif item.mask_tool == 'RECTANGLE':
        tool_rows = (
            ('Drag', 'Draw rectangle'),
            ('Hold Shift', 'Constrain to square'),
            ('Hold Ctrl', 'Draw from center'),
            ('Shift+Ctrl', 'Centered square'),
            ('Esc', 'Cancel rectangle'),
        )
    elif item.mask_tool == 'AUTO':
        tool_rows = (
            ('Click', 'Include area'),
            ('Ctrl+Click', 'Exclude area'),
            ('Enter', 'Apply selection'),
            ('Backspace', 'Remove last point'),
            ('Esc', 'Clear points'),
        )
    else:
        tool_rows = (
            ('Drag', 'Paint color' if color_mode else 'Paint mask'),
            ('Shift+Click', 'Straight line'),
            ('Shift+Drag', 'Snap line to 45°'),
            ('Ctrl+Wheel', f'Brush size: {item.mask_brush_size:.0f}px'),
        )
    common_rows = (
        ('Tab', 'Next tool'),
        ('E', 'Toggle Paint / Erase' if color_mode else 'Toggle Reveal / Erase'),
        ('Hold Alt', 'Temporarily invert'),
        ('MMB / Wheel', 'Pan / zoom'),
        ('Ctrl+Z', 'Undo stroke'),
        ('Ctrl+Shift+Z', 'Redo stroke'),
        ('C' if color_mode else 'M',
         'Finish Color Mode' if color_mode else 'Finish Mask Mode'),
    )
    if color_mode:
        common_rows = (*common_rows[:-1],
                       ('Hold S + Click', 'Pick mask color'),
                       ('< / >', 'Previous / next color'),
                       ('Shift+C', 'Add color'), ('Shift+E', 'Edit color'),
                       common_rows[-1])
    if compact:
        if item.mask_tool == 'POLYGON':
            tool_rows = (tool_rows[0], ('Double-click', 'Close polygon'))
        elif item.mask_tool == 'RECTANGLE':
            tool_rows = tool_rows[:3]
        else:
            tool_rows = (tool_rows[0], tool_rows[1])
        common_rows = ((common_rows[0], ('E', 'Toggle erase'),
                        ('S+Click', 'Pick color'),
                        ('< / >', 'Change color'), ('Shift+C', 'Add color'),
                        ('Shift+E', 'Edit color'), common_rows[-1]) if color_mode else
                       (common_rows[0], ('E', 'Toggle erase'),
                        ('Ctrl+Z', 'Undo stroke'), common_rows[-1]))
    return (*tool_rows, *common_rows)


def round_brush_geometry(item):
    """Canvas radius and UV axes for a circle on a transformed image."""
    width, height = item.image_data.size
    if width <= 0 or height <= 0:
        return None
    center = image_point_from_uv(item, (0.5, 0.5))
    u_point = image_point_from_uv(item, (1.5, 0.5))
    v_point = image_point_from_uv(item, (0.5, 1.5))
    if center is None or u_point is None or v_point is None:
        return None
    ux, uy = u_point[0] - center[0], u_point[1] - center[1]
    vx, vy = v_point[0] - center[0], v_point[1] - center[1]
    determinant = ux * vy - uy * vx
    if abs(determinant) < 1e-8:
        return None
    # Keep approximately the same brush area as a source-pixel circle.
    radius = item.mask_brush_size * math.sqrt(abs(determinant) / (width * height))
    axis_x = (radius * vy / determinant, -radius * uy / determinant)
    axis_y = (-radius * vx / determinant, radius * ux / determinant)
    return radius, axis_x, axis_y


def snapped_line_endpoint(item, start_uv, target_uv):
    """Snap a drag to a canvas-space multiple of 45 degrees."""
    geometry = round_brush_geometry(item)
    start = image_point_from_uv(item, start_uv)
    target = image_point_from_uv(item, target_uv)
    if geometry is None or start is None or target is None:
        return start_uv
    dx, dy = target[0] - start[0], target[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return start_uv
    angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
    radius, axis_x, axis_y = geometry
    dx, dy = length * math.cos(angle), length * math.sin(angle)
    du = (dx * axis_x[0] + dy * axis_y[0]) / radius
    dv = (dx * axis_x[1] + dy * axis_y[1]) / radius
    # A snapped screen direction can point outside the transformed image.
    # Stop at its edge rather than losing the entire stroke.
    limit = 1.0
    for origin, delta in ((start_uv[0], du), (start_uv[1], dv)):
        if delta > 0:
            limit = min(limit, (1.0 - origin) / delta)
        elif delta < 0:
            limit = min(limit, -origin / delta)
    return (max(0.0, min(1.0, start_uv[0] + du * limit)),
            max(0.0, min(1.0, start_uv[1] + dv * limit)))


class MaskPainterMixin:
    bl_idname = 'kanvas.paint_image_mask'
    bl_label = 'Edit Image Mask'
    bl_description = 'Edit with Brush, Polygon, or Rectangle; Tab switches tools, E toggles erase, and Alt temporarily inverts it'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return (item is not None and not item.mask_editing
                and not item.markup_editing)

    def invoke(self, context, event):
        item = _active_image(context)
        if item is None:
            return {'CANCELLED'}
        return self._start_edit(context, event, item)

    def _start_edit(self, context, event, item):
        self._sam_points = []
        self._sam_loops = []
        self._area = context.area
        if item.mask_tool == 'AUTO' and not self._sam_ready(item):
            item.mask_tool = 'BRUSH'
        from ..utils.gpu import ensure_item_ids
        ensure_item_ids(get_settings(context))
        self._area = context.area
        self._tree = context.space_data.edit_tree
        self._item_id = item.item_id
        self._initial_mask_state = (item.mask_revision, item.mask_enabled,
                                    item.mask_brush_size, item.mask_erase,
                                    item.mask_tool)
        self._initial_counts = (len(item.mask_dabs), len(item.mask_polygons))
        self._initial_next_sequence = item.mask_next_sequence
        self._painting = False
        self._nav_mode = None
        self._nav_mouse = None
        self._zoom_drag_pixels = 0.0
        self._last_uv = None
        self._cursor_uv = None
        self._stroke_anchor_uv = None
        self._line_press_uv = None
        self._line_start_uv = None
        self._line_preview_uv = None
        self._line_dragging = False
        self._line_press_mouse = None
        self._polygon_vertices = []
        self._polygon_cursor_uv = None
        self._polygon_last_click = None
        self._rectangle_start_uv = None
        self._rectangle_end_uv = None
        self._rectangle_press_mouse = None
        self._rectangle_square = False
        self._rectangle_centered = False
        self._alt_held = bool(event.alt)
        self._held_alt_keys = set()
        self._shortcut_toggle = None
        self._shortcut_toggle_pressed = False
        self._last_tool = item.mask_tool
        if self._in_canvas(event):
            self._mouse_uv(event, item)
            if item.mask_tool == 'POLYGON':
                self._polygon_cursor_uv = self._cursor_uv
        self._stroke_start_count = None
        self._stroke_region_id = None
        self._history = []
        self._history_index = 0
        item.mask_enabled = True
        item.mask_editing = True
        self._draw_state = {'painter': self, 'tree': self._tree,
                            'item_id': self._item_id, 'handler': None,
                            'editing_attr': ('markup_editing' if getattr(item, '_is_markup', False)
                                             else 'mask_editing')}
        self._draw_state['handler'] = bpy.types.SpaceNodeEditor.draw_handler_add(
            _draw_painter, (self._draw_state,), 'WINDOW', 'POST_PIXEL')
        _active_painters.append(self._draw_state)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        self.report({'INFO'}, f'{getattr(self, "_mode_label", "Mask Mode")}: '
                    'Tab switches tools; E toggles erase; hold Alt to invert temporarily')
        return {'RUNNING_MODAL'}

    def _item(self):
        if self._tree is None:
            return None
        try:
            return next((item for item in self._tree.kanvas_settings.images
                         if item.item_id == self._item_id), None)
        except ReferenceError:
            return None

    def _window_region(self):
        return next((r for r in self._area.regions if r.type == 'WINDOW'), None)

    def _in_canvas(self, event):
        region = self._window_region()
        if region is None:
            return False
        x, y = event.mouse_x, event.mouse_y
        if not (region.x <= x < region.x + region.width
                and region.y <= y < region.y + region.height):
            return False
        return not any(
            part.type != 'WINDOW' and part.width > 1 and part.height > 1
            and part.x <= x < part.x + part.width
            and part.y <= y < part.y + part.height
            for part in self._area.regions
        )

    def _pan_by(self, context, dx, dy):
        region = self._window_region()
        if region is None or not (dx or dy):
            return
        with context.temp_override(window=context.window, area=self._area, region=region):
            if bpy.ops.view2d.pan.poll():
                bpy.ops.view2d.pan(deltax=-round(dx), deltay=-round(dy))
        self._area.tag_redraw()

    def _zoom_view(self, context, direction):
        region = self._window_region()
        if region is None or direction == 0:
            return
        with context.temp_override(window=context.window, area=self._area, region=region):
            operator = bpy.ops.view2d.zoom_in if direction > 0 else bpy.ops.view2d.zoom_out
            if operator.poll():
                operator()
        self._area.tag_redraw()

    def _zoom_from_drag(self, context, delta_y):
        self._zoom_drag_pixels += delta_y
        steps = min(10, int(abs(self._zoom_drag_pixels) // 8))
        if steps:
            direction = 1 if self._zoom_drag_pixels > 0 else -1
            for _ in range(steps):
                self._zoom_view(context, direction)
            self._zoom_drag_pixels -= direction * steps * 8

    def _mouse_uv(self, event, item):
        region = self._window_region()
        if region is None or not self._in_canvas(event):
            self._cursor_uv = None
            return None
        x = event.mouse_x - region.x
        y = event.mouse_y - region.y
        if not (0 <= x < region.width and 0 <= y < region.height):
            self._cursor_uv = None
            return None
        point = region.view2d.region_to_view(x, y)
        self._cursor_uv = image_uv_at(item, point)
        return self._cursor_uv

    def _stamp(self, item, uv, geometry):
        _, axis_x, axis_y = geometry
        dab = item.mask_dabs.add()
        dab.uv = uv
        dab.uv_axis_x = axis_x
        dab.uv_axis_y = axis_y
        dab.radius_uv = (math.hypot(axis_x[0], axis_y[0]),
                         math.hypot(axis_x[1], axis_y[1]))
        dab.erase = _effective_mask_erase(item, getattr(self, '_alt_held', False))
        dab.sequence = _next_mask_sequence(item)
        item.mask_revision += 1

    def _history_region_id(self, item):
        if getattr(item, '_is_markup', False):
            image = item._item
            return image.markup_regions[image.markup_active_index].region_id
        return None

    def _history_target(self, item, region_id):
        if getattr(item, '_is_markup', False):
            image = item._item
            region = next((part for part in image.markup_regions
                           if part.region_id == region_id), None)
            if region is None:
                return None
            return region.dabs, region.polygons, image, region
        return item.mask_dabs, item.mask_polygons, item, None

    def _history_push(self, entry):
        del self._history[self._history_index:]
        self._history.append(entry)
        self._history_index += 1

    def _begin_stroke(self, item):
        self._stroke_region_id = self._history_region_id(item)
        target = self._history_target(item, self._stroke_region_id)
        self._stroke_start_count = len(target[0]) if target else None

    def _commit_stroke(self, item):
        start = getattr(self, '_stroke_start_count', None)
        if start is None or item is None:
            return
        region_id = self._stroke_region_id
        self._stroke_start_count = None
        self._stroke_region_id = None
        target = self._history_target(item, region_id)
        if target is None:
            return
        dabs = tuple(_dab_snapshot(dab) for dab in target[0][start:])
        if dabs:
            self._history_push({'kind': 'DABS', 'region_id': region_id,
                                'data': dabs})

    def _record_polygon(self, item, polygon):
        self._history_push({'kind': 'POLYGON',
                            'region_id': self._history_region_id(item),
                            'data': _polygon_snapshot(polygon)})

    def _history_step(self, item, redo):
        self._commit_stroke(item)
        if redo:
            if self._history_index >= len(self._history):
                return False
            entry = self._history[self._history_index]
        else:
            if self._history_index == 0:
                return False
            entry = self._history[self._history_index - 1]
        target = self._history_target(item, entry['region_id'])
        if target is None:
            return False
        dabs, polygons, image, region = target
        if entry['kind'] == 'DABS':
            if redo:
                for snapshot in entry['data']:
                    _restore_dab(dabs, snapshot)
            else:
                for _ in entry['data']:
                    dabs.remove(len(dabs) - 1)
        elif entry['kind'] == 'POLYGONS':
            if redo:
                for snapshot in entry['data']:
                    _restore_polygon(polygons, snapshot)
            else:
                for _ in entry['data']:
                    polygons.remove(len(polygons) - 1)
        elif redo:
            _restore_polygon(polygons, entry['data'])
        else:
            polygons.remove(len(polygons) - 1)
        if region is not None:
            image.markup_revision += 1
            region.revision += 1
        else:
            image.mask_revision += 1
        self._history_index += 1 if redo else -1
        self._painting = False
        self._last_uv = None
        self._stroke_anchor_uv = None
        self._clear_line()
        self._area.tag_redraw()
        return True

    def _paint_to(self, item, uv):
        geometry = round_brush_geometry(item)
        if geometry is None:
            self._last_uv = None
            return
        if self._last_uv is None:
            self._stamp(item, uv, geometry)
        else:
            start_point = image_point_from_uv(item, self._last_uv)
            end_point = image_point_from_uv(item, uv)
            distance = math.dist(start_point, end_point)
            count = max(1, math.ceil(distance / max(1e-4, geometry[0] * 0.45)))
            start = self._last_uv
            for step in range(1, count + 1):
                t = step / count
                self._stamp(item, (start[0] + (uv[0] - start[0]) * t,
                                   start[1] + (uv[1] - start[1]) * t), geometry)
        self._last_uv = uv

    def _paint_line(self, item, start_uv, end_uv):
        self._last_uv = None
        self._paint_to(item, start_uv)
        if end_uv != start_uv:
            self._paint_to(item, end_uv)
        self._stroke_anchor_uv = end_uv
        self._last_uv = None

    def _clear_line(self):
        self._line_press_uv = None
        self._line_start_uv = None
        self._line_preview_uv = None
        self._line_press_mouse = None
        self._line_dragging = False

    def _switch_tool(self, item, tool):
        if tool == getattr(self, '_last_tool', 'BRUSH'):
            return
        self._painting = False
        self._last_uv = None
        self._stroke_anchor_uv = None
        self._clear_line()
        self._sam_points = []
        self._sam_loops = []
        self._polygon_vertices = []
        self._polygon_cursor_uv = self._cursor_uv if tool == 'POLYGON' else None
        self._polygon_last_click = None
        self._rectangle_start_uv = None
        self._rectangle_end_uv = None
        self._rectangle_press_mouse = None
        self._rectangle_square = False
        self._rectangle_centered = False
        self._last_tool = tool
        self._area.tag_redraw()

    def _polygon_cancel(self):
        self._polygon_vertices = []
        self._polygon_cursor_uv = None
        self._polygon_last_click = None
        self._area.tag_redraw()

    def _polygon_commit(self, item):
        vertices = self._polygon_vertices
        if len(vertices) < 3:
            return False
        polygon = item.mask_polygons.add()
        polygon.erase = _effective_mask_erase(item, getattr(self, '_alt_held', False))
        polygon.sequence = _next_mask_sequence(item)
        for uv in vertices:
            polygon.vertices.add().uv = uv
        item.mask_revision += 1
        self._record_polygon(item, polygon)
        self._polygon_cancel()
        return True

    def _rectangle_vertices(self, item, end_uv, square=False, centered=False):
        start = self._rectangle_start_uv
        if start is None or end_uv is None:
            return []
        dx, dy = end_uv[0] - start[0], end_uv[1] - start[1]
        if centered:
            half_x = min(abs(dx), start[0], 1.0 - start[0])
            half_y = min(abs(dy), start[1], 1.0 - start[1])
            if square:
                width, height = item.image_data.size
                half_side = min(half_x * width, half_y * height)
                half_x = half_side / width if width else 0.0
                half_y = half_side / height if height else 0.0
            if half_x < 1e-6 or half_y < 1e-6:
                return []
            return [(start[0] - half_x, start[1] - half_y),
                    (start[0] + half_x, start[1] - half_y),
                    (start[0] + half_x, start[1] + half_y),
                    (start[0] - half_x, start[1] + half_y)]
        if square:
            width, height = item.image_data.size
            side = min(abs(dx) * width, abs(dy) * height)
            dx = math.copysign(side / width, dx) if width else 0.0
            dy = math.copysign(side / height, dy) if height else 0.0
        x1 = max(0.0, min(1.0, start[0] + dx))
        y1 = max(0.0, min(1.0, start[1] + dy))
        x0, y0 = start
        if abs(x1 - x0) < 1e-6 or abs(y1 - y0) < 1e-6:
            return []
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def _rectangle_commit(self, item, end_uv, square=False, centered=False):
        vertices = self._rectangle_vertices(item, end_uv, square, centered)
        if not vertices:
            return False
        polygon = item.mask_polygons.add()
        polygon.erase = _effective_mask_erase(item, getattr(self, '_alt_held', False))
        polygon.sequence = _next_mask_sequence(item)
        for uv in vertices:
            polygon.vertices.add().uv = uv
        item.mask_revision += 1
        self._record_polygon(item, polygon)
        return True

    def _rectangle_cancel(self):
        self._rectangle_start_uv = None
        self._rectangle_end_uv = None
        self._rectangle_press_mouse = None
        self._rectangle_square = False
        self._rectangle_centered = False
        self._area.tag_redraw()

    def _polygon_target_uv(self, item, uv, shift):
        if uv is not None and shift and self._polygon_vertices:
            return snapped_line_endpoint(item, self._polygon_vertices[-1], uv)
        return uv

    def _polygon_click(self, item, event, uv):
        if uv is None:
            return False
        region = self._window_region()
        position = (event.mouse_x - region.x, event.mouse_y - region.y)

        def distance_to(vertex):
            point = image_point_from_uv(item, vertex)
            if point is None:
                return float('inf')
            x, y = region.view2d.view_to_region(*point, clip=False)
            return math.hypot(position[0] - x, position[1] - y)

        vertices = self._polygon_vertices
        if len(vertices) >= 3 and distance_to(vertices[0]) <= 10:
            return self._polygon_commit(item)
        last_click = self._polygon_last_click
        if (len(vertices) >= 3 and last_click is not None
                and time.monotonic() - last_click[0] <= 0.5
                and math.dist(position, last_click[1]) <= 8):
            return self._polygon_commit(item)
        target_uv = self._polygon_target_uv(item, uv, event.shift)
        target_point = image_point_from_uv(item, target_uv)
        target_screen = region.view2d.view_to_region(*target_point, clip=False)
        previous_point = image_point_from_uv(item, vertices[-1]) if vertices else None
        previous_screen = (region.view2d.view_to_region(*previous_point, clip=False)
                           if previous_point is not None else None)
        if previous_screen is None or math.dist(target_screen, previous_screen) > 4:
            vertices.append(target_uv)
        self._polygon_last_click = (time.monotonic(), position)
        if event.value == 'DOUBLE_CLICK':
            return self._polygon_commit(item)
        return False

    # --- Auto Select (Segment Anything) -------------------------------------

    def _sam_ready(self, item):
        from ..utils import sam_engine
        return sam_engine.ready() and sam_engine.is_analyzed(item.image_data)

    def _sam_reset(self):
        self._sam_points = []
        self._sam_loops = []
        self._area.tag_redraw()

    def _sam_update(self, item):
        """Re-run the decoder for the current clicks and outline the result."""
        from ..utils import sam_engine
        from ..utils.gpu.gpu_mask import mask_dimensions
        from ..utils.mask_vectorize import mask_to_polygons, polygons_to_uv, resize_mask
        if not self._sam_points:
            self._sam_loops = []
            return
        embedding = sam_engine.get_embedding(item.image_data)
        if embedding is None:
            self._sam_reset()
            self.report({'WARNING'}, 'The analysis expired; analyze the image again')
            return
        width, height = item.image_data.size
        prompts = [(uv[0] * width, (1.0 - uv[1]) * height, label)
                   for uv, label in self._sam_points]
        try:
            mask = sam_engine.decode(embedding, prompts)
        except Exception as exc:
            self._sam_reset()
            self.report({'ERROR'}, f'Auto Select failed: {exc}')
            return
        mask_w, mask_h = mask_dimensions(item.image_data)
        polygons = mask_to_polygons(resize_mask(mask[::-1], mask_h, mask_w))
        self._sam_loops = polygons_to_uv(polygons, mask_w, mask_h)

    def _sam_commit(self, item):
        if not self._sam_loops:
            self._sam_reset()
            return False
        erase = _effective_mask_erase(item, getattr(self, '_alt_held', False))
        snapshots = []
        skipped_holes = 0
        for entry in sorted(self._sam_loops, key=lambda part: part['hole']):
            if entry['hole'] and erase:
                skipped_holes += 1   # cannot restore what was there before
                continue
            polygon = item.mask_polygons.add()
            polygon.erase = True if entry['hole'] else erase
            polygon.sequence = _next_mask_sequence(item)
            for uv in entry['uv']:
                polygon.vertices.add().uv = uv
            snapshots.append(_polygon_snapshot(polygon))
        if snapshots:
            item.mask_revision += 1
            self._history_push({'kind': 'POLYGONS',
                                'region_id': self._history_region_id(item),
                                'data': tuple(snapshots)})
        if skipped_holes:
            self.report({'INFO'}, 'Holes inside the selection are not applied when erasing')
        self._sam_reset()
        return bool(snapshots)

    def _draw_sam_preview(self, item, region):
        view = region.view2d
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        previous_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            color = self._preview_color(item)
            gpu.state.line_width_set(2.0)
            for entry in self._sam_loops:
                points = [view.view_to_region(*image_point_from_uv(item, uv), clip=False)
                          for uv in entry['uv']]
                shader.uniform_float('color', (*color[:3], 0.55 if entry['hole'] else 1.0))
                batch_for_shader(shader, 'LINE_LOOP', {'pos': points}).draw(shader)
            gpu.state.line_width_set(1.0)
            gpu.state.point_size_set(9.0)
            for include, tint in ((1, (0.25, 0.95, 0.4, 1.0)), (0, (1.0, 0.3, 0.3, 1.0))):
                spots = [view.view_to_region(*image_point_from_uv(item, uv), clip=False)
                         for uv, label in self._sam_points if label == include]
                if spots:
                    shader.uniform_float('color', tint)
                    batch_for_shader(shader, 'POINTS', {'pos': spots}).draw(shader)
            cursor = self._cursor_uv
            if cursor is not None:
                point = image_point_from_uv(item, cursor)
                if point is not None:
                    x, y = view.view_to_region(*point, clip=False)
                    shader.uniform_float('color', color)
                    batch_for_shader(shader, 'LINES', {'pos': (
                        (x - 8, y), (x + 8, y), (x, y - 8), (x, y + 8))}).draw(shader)
        finally:
            gpu.state.point_size_set(1.0)
            gpu.state.line_width_set(1.0)
            gpu.state.blend_set(previous_blend)

    def _draw_mode_badge(self, item, region):
        alt_held = getattr(self, '_alt_held', False)
        sample_held = getattr(self, '_sample_held', False)
        title = _mask_indicator_text(
            item, alt_held, getattr(self, '_mode_label', 'Mask Mode').upper(),
            sample_held=sample_held)
        draw_mode_badge(region, title, BADGE_ALERT if _effective_mask_erase(item, alt_held)
                        else BADGE_NORMAL, self._area)

    def _draw_shortcut_list(self, item, region):
        compact = region.height < 320 or region.width < 500
        rows = _mask_shortcut_rows(
            item, compact, getattr(item, '_is_markup', False))
        self._shortcut_toggle = draw_shortcut_panel(self._area, region, rows)

    def _shortcut_toggle_hit(self, event):
        bounds = getattr(self, '_shortcut_toggle', None)
        if bounds is None:
            return False
        region = self._window_region()
        if region is None:
            return False
        x = event.mouse_x - region.x
        y = event.mouse_y - region.y
        return bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]

    def _draw_polygon_cursor_icon(self, item, region):
        uv = self._polygon_cursor_uv
        if uv is None:
            return
        point = image_point_from_uv(item, uv)
        if point is None:
            return
        x, y = region.view2d.view_to_region(*point, clip=False)
        offset_x = 16 if x + 43 < region.width else -37
        offset_y = -29 if y > 39 else 17
        a = (x + offset_x, y + offset_y)
        b = (a[0] + 20, a[1])
        c = (a[0] + 12, a[1] + 17)
        color = self._preview_color(item)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        previous_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            shader.uniform_float('color', color)
            batch_for_shader(shader, 'LINES', {'pos': (
                a, b, b, c, c, a,
                (x - 4, y), (x + 4, y), (x, y - 4), (x, y + 4),
            )}).draw(shader)
            gpu.state.point_size_set(5.0)
            batch_for_shader(shader, 'POINTS', {'pos': (a, b, c)}).draw(shader)
        finally:
            gpu.state.point_size_set(1.0)
            gpu.state.blend_set(previous_blend)

    def _draw_polygon_preview(self, item, region):
        if not self._polygon_vertices:
            return
        view = region.view2d
        vertices = list(self._polygon_vertices)
        if self._polygon_cursor_uv is not None:
            vertices.append(self._polygon_cursor_uv)
        points = [image_point_from_uv(item, uv) for uv in vertices]
        points = [view.view_to_region(*point, clip=False)
                  for point in points if point is not None]
        if not points:
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        previous_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            color = self._preview_color(item)
            shader.uniform_float('color', color)
            if len(points) > 1:
                batch_for_shader(shader, 'LINE_STRIP', {'pos': points}).draw(shader)
            if len(self._polygon_vertices) >= 2 and self._polygon_cursor_uv is not None:
                shader.uniform_float('color', (*color[:3], 0.4))
                batch_for_shader(shader, 'LINES', {'pos': (points[-1], points[0])}).draw(shader)
            gpu.state.point_size_set(6.0)
            shader.uniform_float('color', (1.0, 1.0, 1.0, 1.0))
            batch_for_shader(shader, 'POINTS',
                             {'pos': points[:len(self._polygon_vertices)]}).draw(shader)
        finally:
            gpu.state.point_size_set(1.0)
            gpu.state.blend_set(previous_blend)

    def _draw_rectangle_preview(self, item, region):
        vertices = self._rectangle_vertices(item, self._rectangle_end_uv,
                                            getattr(self, '_rectangle_square', False),
                                            getattr(self, '_rectangle_centered', False))
        if not vertices:
            return
        view = region.view2d
        points = [view.view_to_region(*image_point_from_uv(item, uv), clip=False)
                  for uv in vertices]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        previous_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            shader.uniform_float('color', self._preview_color(item))
            batch_for_shader(shader, 'LINE_STRIP',
                             {'pos': (*points, points[0])}).draw(shader)
        finally:
            gpu.state.blend_set(previous_blend)

    def _draw_rectangle_cursor_icon(self, item, region):
        uv = self._cursor_uv
        if uv is None:
            return
        point = image_point_from_uv(item, uv)
        if point is None:
            return
        x, y = region.view2d.view_to_region(*point, clip=False)
        offset_x = 16 if x + 43 < region.width else -37
        offset_y = -29 if y > 39 else 17
        left, bottom = x + offset_x, y + offset_y
        corners = ((left, bottom), (left + 22, bottom),
                   (left + 22, bottom + 16), (left, bottom + 16))
        color = self._preview_color(item)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        previous_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            shader.uniform_float('color', color)
            batch_for_shader(shader, 'LINES', {'pos': (
                corners[0], corners[1], corners[1], corners[2],
                corners[2], corners[3], corners[3], corners[0],
                (x - 4, y), (x + 4, y), (x, y - 4), (x, y + 4),
            )}).draw(shader)
        finally:
            gpu.state.blend_set(previous_blend)

    def _preview_color(self, item):
        if _effective_mask_erase(item, getattr(self, '_alt_held', False)):
            return (1.0, 0.36, 0.25, 1.0)
        if getattr(item, '_is_markup', False):
            return (*item._markup_color, 1.0)
        return (0.3, 0.85, 1.0, 1.0)

    def _draw_cursor(self):
        if bpy.context.area != self._area:
            return
        item = self._item()
        region = self._window_region()
        if item is None or region is None:
            return
        self._draw_mode_badge(item, region)
        self._draw_shortcut_list(item, region)
        if getattr(self, '_sample_held', False):
            return
        if item.mask_tool == 'AUTO':
            self._draw_sam_preview(item, region)
            return
        if item.mask_tool == 'POLYGON':
            self._draw_polygon_preview(item, region)
            self._draw_polygon_cursor_icon(item, region)
            return
        if item.mask_tool == 'RECTANGLE':
            self._draw_rectangle_preview(item, region)
            self._draw_rectangle_cursor_icon(item, region)
            return
        view = region.view2d
        geometry = round_brush_geometry(item)
        if geometry is None:
            return
        radius = geometry[0]
        cursor_uv = self._line_preview_uv if self._line_press_uv is not None else self._cursor_uv
        if cursor_uv is None:
            return
        center = image_point_from_uv(item, cursor_uv)
        points = []
        for i in range(49):
            angle = i * math.tau / 48
            point = (center[0] + math.cos(angle) * radius,
                     center[1] + math.sin(angle) * radius)
            points.append(view.view_to_region(*point, clip=False))
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float('color', self._preview_color(item))
        batch_for_shader(shader, 'LINE_STRIP', {'pos': points}).draw(shader)
        if self._line_start_uv is not None and self._line_preview_uv is not None:
            start = image_point_from_uv(item, self._line_start_uv)
            end = image_point_from_uv(item, self._line_preview_uv)
            if start is not None and end is not None:
                dx, dy = end[0] - start[0], end[1] - start[1]
                if math.hypot(dx, dy) > 1e-6:
                    angle = math.atan2(dy, dx)
                    normal = (-math.sin(angle) * radius, math.cos(angle) * radius)
                    outline = [(start[0] + normal[0], start[1] + normal[1]),
                               (end[0] + normal[0], end[1] + normal[1])]
                    for step in range(1, 17):
                        a = angle + math.pi / 2 - step * math.pi / 16
                        outline.append((end[0] + math.cos(a) * radius,
                                        end[1] + math.sin(a) * radius))
                    outline.append((start[0] - normal[0], start[1] - normal[1]))
                    for step in range(1, 17):
                        a = angle - math.pi / 2 - step * math.pi / 16
                        outline.append((start[0] + math.cos(a) * radius,
                                        start[1] + math.sin(a) * radius))
                    points = [view.view_to_region(*point, clip=False)
                              for point in outline]
                    batch_for_shader(shader, 'LINE_STRIP', {'pos': points}).draw(shader)

    def _finish(self, item):
        self._commit_stroke(item)
        self._sam_points = []
        self._sam_loops = []
        from ..utils import sam_engine
        sam_engine.release_decoder()
        self._polygon_vertices = []
        self._polygon_cursor_uv = None
        self._polygon_last_click = None
        self._alt_held = False
        self._sample_held = False
        if item:
            item.mask_editing = False
            if not getattr(item, '_is_markup', False) \
                    and not item.mask_dabs and not item.mask_polygons:
                item.mask_enabled = False
        _release_painter(self._draw_state)
        self._area.tag_redraw()
        if item is None:
            return {'CANCELLED'}
        current_state = (item.mask_revision, item.mask_enabled,
                         item.mask_brush_size, item.mask_erase,
                         item.mask_tool)
        if current_state == self._initial_mask_state:
            return {'CANCELLED'}
        if (not getattr(item, '_is_markup', False)
                and self._history_index == 0
                and (len(item.mask_dabs), len(item.mask_polygons)) == self._initial_counts
                and current_state[1:] == self._initial_mask_state[1:]):
            item.mask_next_sequence = self._initial_next_sequence
            return {'CANCELLED'}
        return {'FINISHED'}

    def modal(self, context, event):
        item = self._item()
        if item is None or context.area != self._area:
            return self._finish(item)
        if event.type in {'LEFT_ALT', 'RIGHT_ALT'}:
            if event.value == 'PRESS':
                self._held_alt_keys.add(event.type)
            elif event.value == 'RELEASE':
                self._held_alt_keys.discard(event.type)
            self._alt_held = bool(self._held_alt_keys)
        else:
            self._alt_held = bool(event.alt)
        if event.type == 'LEFTMOUSE' and self._shortcut_toggle_hit(event):
            if event.value in {'PRESS', 'DOUBLE_CLICK'}:
                _shortcut_panel['collapsed'] = not _shortcut_panel['collapsed']
                self._shortcut_toggle_pressed = True
                self._area.tag_redraw()
            if event.value in {'PRESS', 'DOUBLE_CLICK'} or self._shortcut_toggle_pressed:
                if event.value == 'RELEASE':
                    self._shortcut_toggle_pressed = False
                return {'RUNNING_MODAL'}
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE' \
                and getattr(self, '_shortcut_toggle_pressed', False):
            self._shortcut_toggle_pressed = False
            return {'RUNNING_MODAL'}
        tool = item.mask_tool
        if tool != getattr(self, '_last_tool', 'BRUSH'):
            self._commit_stroke(item)
            if self._in_canvas(event):
                self._mouse_uv(event, item)
            self._switch_tool(item, tool)
        if event.ctrl and event.value == 'PRESS' and event.type in {'Z', 'Y'}:
            self._history_step(item, event.type == 'Y' or event.shift)
            return {'RUNNING_MODAL'}
        if event.type in {'TAB', 'B', 'P'} and event.value == 'PRESS':
            self._commit_stroke(item)
            if self._in_canvas(event):
                self._mouse_uv(event, item)
            tools = ('BRUSH', 'POLYGON', 'RECTANGLE')
            if self._sam_ready(item):
                tools += ('AUTO',)
            if event.type == 'TAB':
                current = tools.index(tool) if tool in tools else -1
                tool = tools[(current + 1) % len(tools)]
            else:
                tool = 'BRUSH' if event.type == 'B' else 'POLYGON'
            item.mask_tool = tool
            self._switch_tool(item, tool)
            return {'RUNNING_MODAL'}
        if (event.type == 'A' and event.value == 'PRESS' and not event.ctrl
                and not event.shift and not event.alt):
            if self._sam_ready(item):
                self._commit_stroke(item)
                item.mask_tool = 'AUTO'
                self._switch_tool(item, 'AUTO')
            else:
                self.report({'INFO'}, 'Auto Select: analyze the image first '
                            '(Analyze Image in this panel)')
            return {'RUNNING_MODAL'}
        finish_key = 'C' if getattr(item, '_is_markup', False) else 'M'
        if (event.type == finish_key and event.value == 'PRESS'
                and not event.ctrl and not event.shift and not event.alt):
            return self._finish(item)
        if event.type == 'RIGHTMOUSE' and event.alt:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        if tool == 'POLYGON' and event.type in {'ESC', 'RIGHTMOUSE'} \
                and event.value == 'PRESS' and self._polygon_vertices:
            self._polygon_cancel()
            return {'RUNNING_MODAL'}
        if tool == 'POLYGON' and event.type in {'RET', 'NUMPAD_ENTER'} \
                and event.value == 'PRESS' and self._polygon_vertices:
            self._polygon_commit(item)
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if tool == 'RECTANGLE' and event.type == 'ESC' \
                and event.value == 'PRESS' and self._rectangle_start_uv is not None:
            self._rectangle_cancel()
            return {'RUNNING_MODAL'}
        if event.type == 'ESC' and event.value == 'PRESS' and self._line_press_uv is not None:
            self._commit_stroke(item)
            self._clear_line()
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if tool == 'AUTO' and event.value == 'PRESS' and self._sam_points:
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                self._sam_reset()
                return {'RUNNING_MODAL'}
            if event.type in {'RET', 'NUMPAD_ENTER'}:
                self._sam_commit(item)
                return {'RUNNING_MODAL'}
            if event.type == 'BACK_SPACE':
                self._sam_points.pop()
                self._sam_update(item)
                self._area.tag_redraw()
                return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._finish(item)
        if event.type in {'LEFT_ALT', 'RIGHT_ALT'}:
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'E' and event.value == 'PRESS':
            item.mask_erase = not item.mask_erase
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if tool == 'POLYGON' and event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'}:
            self._polygon_cursor_uv = self._polygon_target_uv(
                item, self._cursor_uv, event.value == 'PRESS')
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if tool == 'RECTANGLE' and event.type in {
                'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_CTRL', 'RIGHT_CTRL'}:
            if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'}:
                self._rectangle_square = event.value == 'PRESS'
            else:
                self._rectangle_centered = event.value == 'PRESS'
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'MIDDLEMOUSE':
            if event.value == 'PRESS' and self._in_canvas(event):
                self._commit_stroke(item)
                self._nav_mode = 'ZOOM' if event.ctrl else 'PAN'
                self._nav_mouse = (event.mouse_x, event.mouse_y)
                self._zoom_drag_pixels = 0.0
                self._painting = False
                self._last_uv = None
                self._cursor_uv = None
                self._polygon_cursor_uv = None
                if tool == 'BRUSH':
                    self._clear_line()
                return {'RUNNING_MODAL'}
            if event.value == 'RELEASE' and self._nav_mode:
                self._nav_mode = None
                self._nav_mouse = None
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and self._nav_mode:
            self._nav_mode = None
            self._nav_mouse = None
        if self._nav_mode and event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            dx = event.mouse_x - self._nav_mouse[0]
            dy = event.mouse_y - self._nav_mouse[1]
            if self._nav_mode == 'PAN':
                self._pan_by(context, dx, dy)
            else:
                self._zoom_from_drag(context, dy)
            self._nav_mouse = (event.mouse_x, event.mouse_y)
            return {'RUNNING_MODAL'}
        if event.type in {'TRACKPADPAN', 'TRACKPADZOOM'} and self._in_canvas(event):
            self._commit_stroke(item)
            self._painting = False
            self._last_uv = None
            self._polygon_cursor_uv = None
            if tool == 'BRUSH':
                self._clear_line()
            dx = event.mouse_x - event.mouse_prev_x
            dy = event.mouse_y - event.mouse_prev_y
            if event.type == 'TRACKPADZOOM' or event.ctrl:
                self._zoom_from_drag(context, dy)
            else:
                self._pan_by(context, dx, dy)
            return {'RUNNING_MODAL'}
        if event.type in {'MOUSEROTATE', 'MOUSESMARTZOOM', 'NDOF_MOTION'}:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE',
                          'WHEELOUTMOUSE', 'WHEELLEFTMOUSE', 'WHEELRIGHTMOUSE'}:
            if not self._in_canvas(event):
                return {'RUNNING_MODAL', 'PASS_THROUGH'}
            if not event.ctrl or tool in {'POLYGON', 'RECTANGLE'}:
                self._commit_stroke(item)
                self._last_uv = None
                self._polygon_cursor_uv = None
                if tool == 'BRUSH':
                    self._clear_line()
                if event.type in {'WHEELLEFTMOUSE', 'WHEELRIGHTMOUSE'}:
                    self._pan_by(context, 40 if event.type == 'WHEELRIGHTMOUSE' else -40, 0)
                else:
                    self._zoom_view(context, 1 if event.type in {'WHEELUPMOUSE', 'WHEELINMOUSE'} else -1)
                return {'RUNNING_MODAL'}
            if event.type in {'WHEELLEFTMOUSE', 'WHEELRIGHTMOUSE'}:
                return {'RUNNING_MODAL', 'PASS_THROUGH'}
            factor = 1.15 if event.type in {'WHEELUPMOUSE', 'WHEELINMOUSE'} else 1 / 1.15
            item.mask_brush_size = max(1, min(512, item.mask_brush_size * factor))
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'NUMPAD_PLUS', 'NUMPAD_MINUS', 'HOME'}:
            if event.value == 'PRESS' and event.type != 'HOME':
                self._zoom_view(context, 1 if event.type == 'NUMPAD_PLUS' else -1)
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        if event.type not in {'LEFTMOUSE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            return {'RUNNING_MODAL'}
        if (event.type == 'LEFTMOUSE' and not self._in_canvas(event)
                and not (tool == 'RECTANGLE' and self._rectangle_start_uv is not None
                         and event.value == 'RELEASE')):
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        uv = self._mouse_uv(event, item)
        if tool == 'AUTO':
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and uv is not None:
                # The first point always includes; Ctrl+Click excludes afterwards.
                label = 0 if (event.ctrl and self._sam_points) else 1
                self._sam_points.append((uv, label))
                self._sam_update(item)
            self._area.tag_redraw()
            return ({'RUNNING_MODAL'} if self._in_canvas(event)
                    else {'RUNNING_MODAL', 'PASS_THROUGH'})
        if tool == 'POLYGON':
            self._polygon_cursor_uv = self._polygon_target_uv(item, uv, event.shift)
            if event.type == 'LEFTMOUSE' and event.value in {'PRESS', 'DOUBLE_CLICK'}:
                self._polygon_click(item, event, uv)
            self._area.tag_redraw()
            return ({'RUNNING_MODAL'} if self._in_canvas(event)
                    else {'RUNNING_MODAL', 'PASS_THROUGH'})
        if tool == 'RECTANGLE':
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and uv is not None:
                self._rectangle_start_uv = uv
                self._rectangle_end_uv = uv
                self._rectangle_press_mouse = (event.mouse_x, event.mouse_y)
                self._rectangle_square = event.shift
                self._rectangle_centered = event.ctrl
            elif self._rectangle_start_uv is not None:
                if uv is not None:
                    self._rectangle_end_uv = uv
                self._rectangle_square = event.shift
                self._rectangle_centered = event.ctrl
                if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                    if (self._rectangle_press_mouse is not None and
                            math.dist(self._rectangle_press_mouse,
                                      (event.mouse_x, event.mouse_y)) >= 3.0):
                        self._rectangle_commit(item, self._rectangle_end_uv,
                                               self._rectangle_square,
                                               self._rectangle_centered)
                    self._rectangle_cancel()
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE':
            if event.value == 'RELEASE':
                if self._line_press_uv is not None:
                    if uv is not None and self._line_press_mouse is not None:
                        moved = math.dist(self._line_press_mouse,
                                          (event.mouse_x, event.mouse_y)) >= 3.0
                        if moved:
                            self._line_dragging = True
                            self._line_start_uv = self._line_press_uv
                            self._line_preview_uv = snapped_line_endpoint(
                                item, self._line_press_uv, uv)
                        elif not self._line_dragging:
                            self._line_preview_uv = uv
                    end_uv = self._line_preview_uv or self._line_press_uv
                    self._paint_line(item, self._line_start_uv, end_uv)
                    self._clear_line()
                elif self._last_uv is not None:
                    self._stroke_anchor_uv = self._last_uv
                self._painting = False
                self._last_uv = None
                self._commit_stroke(item)
            elif event.value == 'PRESS' and uv is not None:
                self._begin_stroke(item)
                if event.shift:
                    self._painting = False
                    self._line_press_uv = uv
                    self._line_start_uv = self._stroke_anchor_uv or uv
                    self._line_preview_uv = uv
                    self._line_press_mouse = (event.mouse_x, event.mouse_y)
                    self._line_dragging = False
                else:
                    self._painting = True
                    self._paint_to(item, uv)
        elif self._line_press_uv is not None:
            if uv is not None:
                if math.dist(self._line_press_mouse,
                             (event.mouse_x, event.mouse_y)) >= 3.0:
                    self._line_dragging = True
                if self._line_dragging:
                    self._line_start_uv = self._line_press_uv
                    self._line_preview_uv = snapped_line_endpoint(
                        item, self._line_press_uv, uv)
                else:
                    self._line_preview_uv = uv
        elif self._painting:
            if uv is None:
                self._last_uv = None
            else:
                self._paint_to(item, uv)
        self._area.tag_redraw()
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'} and not self._painting:
            return {'RUNNING_MODAL'} if self._in_canvas(event) else {'RUNNING_MODAL', 'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class KANVAS_OT_PaintImageMask(MaskPainterMixin, KanvasTreeOnly, bpy.types.Operator):
    """Registered mask editor; color markup shares only its Python behavior."""


class KANVAS_OT_ClearImageMask(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.clear_image_mask'
    bl_label = 'Clear Image Mask'
    bl_description = 'Remove all brush marks and polygons from this image mask'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and _active_image(context) is not None

    def execute(self, context):
        item = _active_image(context)
        if not item.mask_dabs and not item.mask_polygons and not item.mask_enabled:
            return {'CANCELLED'}
        item.mask_dabs.clear()
        item.mask_polygons.clear()
        item.mask_revision += 1
        item.mask_enabled = False
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_DrawMaskPolygon(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.draw_mask_polygon'
    bl_label = 'Draw Mask Polygon'
    bl_description = 'Switch to Polygon and start editing the active image mask'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return KANVAS_OT_PaintImageMask.poll(context)

    def invoke(self, context, event):
        item = _active_image(context)
        item.mask_tool = 'POLYGON'
        bpy.ops.kanvas.paint_image_mask('INVOKE_DEFAULT')
        return {'FINISHED'}


def unregister():
    for state in tuple(_active_painters):
        _release_painter(state)
