"""Marks on images, drawn on the canvas: lines and rectangles with their sizes.

The lines are drawn in canvas space (`draw_marks`, POST_VIEW) from the image
coordinates the marks are stored in, so they follow the image. The sizes are text at
the middle of each mark, in region pixels (`draw_mark_labels`, POST_PIXEL), always the
same size on screen. The mark that is the scale of its image is amber with a pin;
the others are cyan. Nothing here is drawn into an exported picture.
"""

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .. import measure as measure_math
from .gpu_theme import draw_canvas_text
from .gpu_visibility import image_intersects_view

COLOR = (0.25, 0.85, 1.0, 0.95)
SCALE_COLOR = (1.0, 0.72, 0.15, 1.0)
FILL_ALPHA = 0.10
LINE_WIDTH = 2.0
LABEL_LIFT = 18.0           # how far labels rise while the handles show, in pixels
HANDLE_HALF = 4.0          # half the side of a handle square, in pixels
CAP_PIXELS = 6.0            # half length of the end caps of a line
FONT_SIZE = 13
MIN_IMAGE_SCREEN_SIZE = 40.0


def _marked_items(settings, view_bounds=None):
    """Visible images that show marks, with the marks to draw."""
    for item in settings.images:
        if (item.item_type != 'IMAGE' or not item.show_in_editor or not item.image_data
                or not item.measure_visible or not item.measures):
            continue
        if view_bounds is not None and not image_intersects_view(item, view_bounds):
            continue
        yield item


def _color(item, mark):
    return SCALE_COLOR if mark.measure_id == item.measure_scale_id else COLOR


def draw_marks(settings, view_pixel_size, view_bounds):
    """Lines and rectangles, in canvas space."""
    items = list(_marked_items(settings, view_bounds))
    if not items:
        return
    editing = measure_math.editing_item(settings, bpy.context.window_manager)
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    fill_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()
    previous = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        for item in items:
            for mark in item.measures:
                if not mark.visible:
                    continue
                points = measure_math.mark_canvas_points(item, mark)
                if points is None:
                    continue
                color = _color(item, mark)
                lines = []
                if mark.kind == 'RECT':
                    fill_shader.bind()
                    fill_shader.uniform_float('color', (*color[:3], FILL_ALPHA))
                    batch_for_shader(fill_shader, 'TRI_FAN', {'pos': points}).draw(fill_shader)
                    for index, point in enumerate(points):
                        lines += [point, points[(index + 1) % 4]]
                else:
                    start, end = points
                    lines += [start, end]
                    # A short cap across each end, so the measured length reads clearly.
                    dx, dy = end[0] - start[0], end[1] - start[1]
                    length = (dx * dx + dy * dy) ** 0.5
                    if length > 1e-9:
                        nx, ny = -dy / length * CAP_PIXELS * view_pixel_size, \
                            dx / length * CAP_PIXELS * view_pixel_size
                        for x, y in (start, end):
                            lines += [(x - nx, y - ny), (x + nx, y + ny)]
                shader.bind()
                shader.uniform_float('viewportSize', (viewport[2], viewport[3]))
                shader.uniform_float('lineWidth', LINE_WIDTH)
                shader.uniform_float('color', color)
                batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)
                if editing is not None and item.item_id == editing.item_id:
                    _draw_handles(fill_shader, item, mark, color, view_pixel_size,
                                  mark.measure_id == _active_id(item))
    finally:
        gpu.state.blend_set(previous)


def _active_id(item):
    index = item.measure_active_index
    return item.measures[index].measure_id if 0 <= index < len(item.measures) else ''


def _draw_handles(shader, item, mark, color, view_pixel_size, active):
    """Squares at the ends and corners and a diamond in the middle: what can be dragged."""
    half = (HANDLE_HALF + (1.0 if active else 0.0)) * view_pixel_size
    shader.bind()
    for part, (x, y) in measure_math.mark_handles(item, mark):
        if part == 'CENTER':
            r = half * 1.15
            points = [(x - r, y), (x, y - r), (x + r, y), (x, y + r)]
        else:
            points = [(x - half, y - half), (x + half, y - half),
                      (x + half, y + half), (x - half, y + half)]
        shader.uniform_float('color', (1.0, 1.0, 1.0, 0.95 if active else 0.7))
        batch_for_shader(shader, 'TRI_FAN', {'pos': [
            (px + (px - x) * 0.45, py + (py - y) * 0.45) for px, py in points]}).draw(shader)
        shader.uniform_float('color', (*color[:3], 1.0 if active else 0.85))
        batch_for_shader(shader, 'TRI_FAN', {'pos': points}).draw(shader)


def draw_mark_labels(settings, region):
    """The size of each mark, in region pixels."""
    view = region.view2d
    items = list(_marked_items(settings))
    if not items:
        return
    unit = settings.measure_unit
    editing = measure_math.editing_item(settings, bpy.context.window_manager)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    blf.size(0, FONT_SIZE)
    try:
        for item in items:
            width, height = _screen_size(item, view)
            if max(width, height) < MIN_IMAGE_SCREEN_SIZE:
                continue
            for mark in item.measures:
                if not mark.visible:
                    continue
                point = measure_math.mark_label_point(item, mark)
                if point is None:
                    continue
                x, y = view.view_to_region(point[0], point[1], clip=False)
                if x < -80 or x > region.width + 80 or y < -20 or y > region.height + 20:
                    continue
                if editing is not None and item.item_id == editing.item_id:
                    y += LABEL_LIFT       # clear of the handle in the middle of the mark
                text = measure_math.mark_text(item, mark, unit)
                text_w, text_h = blf.dimensions(0, text)
                pad = 5.0
                left, bottom = x - text_w * 0.5 - pad, y - text_h * 0.5 - pad
                right, top = x + text_w * 0.5 + pad, y + text_h * 0.5 + pad
                color = _color(item, mark)
                shader.bind()
                shader.uniform_float('color', (0.05, 0.05, 0.06, 0.78))
                batch_for_shader(shader, 'TRI_FAN', {'pos': [
                    (left, bottom), (right, bottom), (right, top), (left, top)]}).draw(shader)
                shader.uniform_float('color', (*color[:3], 0.9))
                batch_for_shader(shader, 'LINE_LOOP', {'pos': [
                    (left, bottom), (right, bottom), (right, top), (left, top)]}).draw(shader)
                blf.color(0, 1.0, 1.0, 1.0, 1.0)
                draw_canvas_text(0, text, x - text_w * 0.5, y - text_h * 0.5 + 1.0,
                                 (1.0, 1.0, 1.0), FONT_SIZE)
    finally:
        gpu.state.blend_set(previous)


def _screen_size(item, view):
    """Width and height in region pixels of the image's bounding box."""
    from ..item_geometry import item_bounds
    bounds = item_bounds(item)
    if bounds is None:
        return 0.0, 0.0
    x0, y0 = view.view_to_region(bounds[0], bounds[1], clip=False)
    x1, y1 = view.view_to_region(bounds[2], bounds[3], clip=False)
    return abs(x1 - x0), abs(y1 - y0)
