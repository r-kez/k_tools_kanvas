"""Frame the selected Kanvas items with Blender's native 2D view operator."""

import bpy
from ..utils.kanvas_data import get_settings

from .kanvas_context import KanvasTreeOnly
from ..utils.arrow_geometry import curve_points
from ..utils.item_geometry import item_bounds


def selected_bounds(settings):
    bounds = [item_bounds(item) for item in settings.images
              if item.is_selected and item.show_in_editor]
    bounds = [bound for bound in bounds if bound is not None]
    for arrow in settings.arrows:
        if not arrow.is_selected:
            continue
        points = curve_points(settings, arrow)
        bounds.append((min(point[0] for point in points),
                       min(point[1] for point in points),
                       max(point[0] for point in points),
                       max(point[1] for point in points)))
    if not bounds:
        return None
    return (min(bound[0] for bound in bounds),
            min(bound[1] for bound in bounds),
            max(bound[2] for bound in bounds),
            max(bound[3] for bound in bounds))


def visible_content_bounds(settings):
    """Bounds for shown board content, including arrows and frame titles."""
    bounds = [item_bounds(item) for item in settings.images if item.show_in_editor]
    bounds = [bound for bound in bounds if bound is not None]
    for arrow in settings.arrows:
        points = curve_points(settings, arrow)
        if points:
            bounds.append((min(point[0] for point in points),
                           min(point[1] for point in points),
                           max(point[0] for point in points),
                           max(point[1] for point in points)))
    return bounds


def offscreen_target(settings, view_bounds, content_bounds=None):
    """Return the nearest content center only when the current view is empty."""
    bounds = content_bounds if content_bounds is not None else visible_content_bounds(settings)
    if not bounds:
        return None
    left, bottom, right, top = view_bounds
    if any(a <= right and c >= left and b <= top and d >= bottom
           for a, b, c, d in bounds):
        return None
    center_x, center_y = (left + right) * 0.5, (bottom + top) * 0.5
    nearest = min(bounds, key=lambda bound:
                  ((bound[0] + bound[2]) * 0.5 - center_x) ** 2
                  + ((bound[1] + bound[3]) * 0.5 - center_y) ** 2)
    return ((nearest[0] + nearest[2]) * 0.5,
            (nearest[1] + nearest[3]) * 0.5)


def usable_canvas_rect(area, region):
    """Window-region coordinates left uncovered by Blender side panels."""
    left, bottom, right, top = 0.0, 0.0, float(region.width), float(region.height)
    window_left, window_right = region.x, region.x + region.width
    window_middle_y = region.y + region.height * 0.5
    for panel in area.regions:
        if panel == region or panel.type not in {'UI', 'TOOLS', 'TOOL_PROPS'}:
            continue
        if panel.width < 24 or not (panel.y <= window_middle_y <= panel.y + panel.height):
            continue
        panel_left, panel_right = panel.x, panel.x + panel.width
        if panel_left <= window_left + 24 < panel_right:
            left = max(left, panel_right - window_left)
        elif panel_left < window_right - 24 <= panel_right:
            right = min(right, panel_left - window_left)
    return (left, bottom, right, top)


def recenter_prompt(settings, area, region):
    """Centered GPU prompt state, or None while content is in view."""
    left, bottom, right, top = usable_canvas_rect(area, region)
    view = region.view2d
    vx0, vy0 = view.region_to_view(left, bottom)
    vx1, vy1 = view.region_to_view(right, top)
    view_bounds = (min(vx0, vx1), min(vy0, vy1),
                   max(vx0, vx1), max(vy0, vy1))
    content = visible_content_bounds(settings)
    target = offscreen_target(settings, view_bounds, content) if content else None
    empty = not content
    if empty and not (view_bounds[0] <= 0 <= view_bounds[2]
                      and view_bounds[1] <= 0 <= view_bounds[3]):
        target = (0.0, 0.0)
    if target is None or right - left < 190 or top - bottom < 100:
        return None
    center_x, center_y = (left + right) * 0.5, (bottom + top) * 0.5
    target_x, target_y = view.view_to_region(*target, clip=False)
    dx, dy = target_x - center_x, target_y - center_y
    direction = ('→' if dx > 0 else '←') if abs(dx) >= abs(dy) else ('↑' if dy > 0 else '↓')
    return {
        'bounds': (center_x - 94, center_y - 28,
                   center_x + 94, center_y + 28),
        'direction': direction,
        'empty': empty,
    }


def hit_recenter_prompt(settings, area, region, position):
    prompt = recenter_prompt(settings, area, region)
    if prompt is None:
        return False
    x0, y0, x1, y1 = prompt['bounds']
    return x0 <= position[0] <= x1 and y0 <= position[1] <= y1


def expand_zoom_box_for_panels(box, usable_rect, region_size):
    """Reserve sidebar space when framing content with view2d.zoom_border."""
    x0, y0, x1, y1 = box
    left, bottom, right, top = usable_rect
    width, height = region_size
    usable_width = max(1.0, right - left)
    usable_height = max(1.0, top - bottom)
    full_width = (x1 - x0) * width / usable_width
    full_height = (y1 - y0) * height / usable_height
    return (x0 - full_width * left / width,
            y0 - full_height * bottom / height,
            x1 + full_width * (width - right) / width,
            y1 + full_height * (height - top) / height)


class KANVAS_OT_Recenter(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.recenter'
    bl_label = 'Recenter Kanvas'
    bl_description = 'Frame visible board content, or return to the origin if the board is empty'

    def execute(self, context):
        region = next((region for region in context.area.regions
                       if region.type == 'WINDOW'), None)
        if region is None:
            return {'CANCELLED'}
        bounds = visible_content_bounds(get_settings(context))
        if bounds:
            left = min(bound[0] for bound in bounds)
            bottom = min(bound[1] for bound in bounds)
            right = max(bound[2] for bound in bounds)
            top = max(bound[3] for bound in bounds)
        else:
            left, bottom, right, top = -500.0, -300.0, 500.0, 300.0
        width, height = max(40.0, right - left), max(40.0, top - bottom)
        margin_x, margin_y = width * 0.12, height * 0.12
        view = region.view2d
        x0, y0 = view.view_to_region(left - margin_x, bottom - margin_y, clip=False)
        x1, y1 = view.view_to_region(right + margin_x, top + margin_y, clip=False)
        x0, y0, x1, y1 = expand_zoom_box_for_panels(
            (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
            usable_canvas_rect(context.area, region),
            (region.width, region.height))
        with context.temp_override(region=region):
            result = bpy.ops.view2d.zoom_border(
                xmin=int(x0), xmax=int(x1),
                ymin=int(y0), ymax=int(y1),
                wait_for_input=False)
        context.area.tag_redraw()
        return result


class KANVAS_OT_FocusSelection(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.focus_selection'
    bl_label = 'Focus Kanvas Selection'
    bl_description = 'Frame the selected Kanvas images, text cards, frames, and arrows'

    @classmethod
    def poll(cls, context):
        return (KanvasTreeOnly.poll(context)
                and getattr(context, 'region', None) is not None
                and context.region.type == 'WINDOW')

    def execute(self, context):
        bounds = selected_bounds(get_settings(context))
        if bounds is None:
            return {'PASS_THROUGH'}

        left, bottom, right, top = bounds
        width = max(40.0, right - left)
        height = max(40.0, top - bottom)
        margin_x = width * 0.12
        margin_y = height * 0.12
        view = context.region.view2d
        x0, y0 = view.view_to_region(left - margin_x, bottom - margin_y, clip=False)
        x1, y1 = view.view_to_region(right + margin_x, top + margin_y, clip=False)
        result = bpy.ops.view2d.zoom_border(
            xmin=min(x0, x1), xmax=max(x0, x1),
            ymin=min(y0, y1), ymax=max(y0, y1),
            wait_for_input=False,
        )
        context.area.tag_redraw()
        return result
