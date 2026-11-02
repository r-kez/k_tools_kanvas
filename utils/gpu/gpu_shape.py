"""Draw Kanvas shapes: fill, outline, selection handles and centered text."""

import math

import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .. import shape_geometry as geometry
from ..item_geometry import shape_draw_indices
from .gpu_arrow import _antialias_fringe, _draw_plain_strokes, _square, _triangles
from .gpu_theme import (disable_soft_text_shadow, draw_canvas_text,
                        enable_soft_text_shadow, selection_color)

HANDLE_DARK = (0.035, 0.055, 0.075, 0.95)
HANDLE_LIGHT = (1.0, 1.0, 1.0, 1.0)
VERTEX_HIT_PIXELS = 9.0
EDGE_HIT_PIXELS = 7.0


def _circle(center, radius, steps=16):
    x, y = center
    ring = [(x + radius * math.cos(math.tau * i / steps),
             y + radius * math.sin(math.tau * i / steps)) for i in range(steps)]
    return [vertex for i in range(steps)
            for vertex in (center, ring[i], ring[(i + 1) % steps])]


def _clockwise(points):
    return list(reversed(points)) if geometry.signed_area(points) > 0 else list(points)


def _outline_strokes(points, style, width):
    loop = list(points) + [points[0]]
    if style == 'SOLID':
        # One stroke per side: the round caps give the corners a round join.
        return [[a, b] for a, b in zip(loop, loop[1:])]
    from ..arrow_geometry import dash_pattern, dash_polylines
    dash, gap = dash_pattern(style, width)
    return dash_polylines(loop, dash, gap)


def _visible(item, view_bounds):
    left, bottom, right, top = geometry.bounds(item)
    margin = item.shape_line_width
    return not (right + margin < view_bounds[0] or left - margin > view_bounds[2]
                or top + margin < view_bounds[1] or bottom - margin > view_bounds[3])


def _draw_body(shader, smooth, item, pixel_size):
    points = geometry.outline(item)
    opacity = item.opacity
    if len(points) == 2:
        # A polygon being drawn click by click: its first segment.
        _draw_plain_strokes(shader, smooth, [points], item.shape_line_width,
                            pixel_size, (*item.shape_line_color, opacity))
        return
    if len(points) < geometry.MIN_VERTICES:
        return
    if item.shape_show_fill and item.shape_fill_opacity * opacity > 0.0:
        color = (*item.shape_fill_color, item.shape_fill_opacity * opacity)
        triangles = [vertex for triangle in geometry.triangulate(points)
                     for vertex in triangle]
        _triangles(shader, triangles, color)
        fringe, fringe_colors = _antialias_fringe(
            _clockwise(points), pixel_size, color)
        if fringe:
            smooth.bind()
            batch_for_shader(smooth, 'TRIS', {
                'pos': fringe, 'color': fringe_colors}).draw(smooth)
    if item.shape_show_outline:
        strokes = _outline_strokes(points, item.shape_line_style, item.shape_line_width)
        _draw_plain_strokes(shader, smooth, strokes, item.shape_line_width,
                            pixel_size, (*item.shape_line_color, opacity))


def _draw_handle(shader, point, pixel_size, radius=4.5):
    _triangles(shader, _square(point, radius * pixel_size), HANDLE_DARK)
    _triangles(shader, _square(point, (radius - 1.5) * pixel_size), HANDLE_LIGHT)


def _sole_selection(settings, item):
    return (item.is_selected and not item.is_locked
            and sum(1 for other in settings.images if other.is_selected) == 1)


def _draw_selection(shader, smooth, settings, item, pixel_size):
    color = selection_color()
    thickness = max(1.0, 1.5) * pixel_size
    editing = item.shape_edit_vertices and _sole_selection(settings, item)
    if editing:
        points = geometry.outline(item)
        _draw_plain_strokes(shader, smooth, _outline_strokes(points, 'SOLID', thickness),
                            thickness, pixel_size, color)
        for point in points:
            _draw_handle(shader, point, pixel_size, 5.0)
        for i, a in enumerate(points):
            b = points[(i + 1) % len(points)]
            _triangles(shader, _circle(((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5),
                                       2.6 * pixel_size), (*color[:3], 0.75))
        return
    corners = geometry.box_corners(item)
    _draw_plain_strokes(shader, smooth, _outline_strokes(corners, 'SOLID', thickness),
                        thickness, pixel_size, color)
    if not (_sole_selection(settings, item) and settings.show_gizmos):
        return
    size = settings.gizmo_size * pixel_size
    corner_points, edge_points, stem, rotate = geometry.gizmo_layout(item, size)
    if settings.show_scale_handles:
        for point in corner_points:
            _draw_handle(shader, point, pixel_size)
        for point in edge_points:
            _draw_handle(shader, point, pixel_size, 4.0)
    if settings.show_rotate_handles:
        _draw_plain_strokes(shader, smooth, [[stem, rotate]], thickness, pixel_size, color)
        _triangles(shader, _circle(rotate, 6.0 * pixel_size), HANDLE_DARK)
        _triangles(shader, _circle(rotate, 4.5 * pixel_size), color)


def draw_shapes(settings, pixel_size, view_bounds):
    """POST_VIEW pass: every visible shape, then the selection overlays on top."""
    indices = shape_draw_indices(settings)
    if not indices:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    smooth = gpu.shader.from_builtin('SMOOTH_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        visible = []
        for index in indices:
            item = settings.images[index]
            if not _visible(item, view_bounds):
                continue
            visible.append(item)
            try:
                _draw_body(shader, smooth, item, pixel_size)
            except Exception as exc:
                print(f'Kanvas shape {item.name}: {exc}')
        for item in visible:
            if item.is_selected and not item.is_locked:
                _draw_selection(shader, smooth, settings, item, pixel_size)
    finally:
        gpu.state.blend_set(old_blend)


# Text is measured at this size and scaled, so wrapping does not depend on the zoom.
TEXT_REFERENCE_SIZE = 100.0


def _fit_rows(text, max_width, max_rows):
    """Wrap text to the box width; what does not fit ends in an ellipsis."""
    from .gpu_text import _wrapped_lines
    rows = _wrapped_lines(text, max_width, 0)
    if len(rows) <= max_rows:
        return rows
    rows = rows[:max(1, max_rows)]
    last = rows[-1].rstrip()
    while last and blf.dimensions(0, last + '…')[0] > max_width:
        last = last[:-1]
    rows[-1] = last + '…'
    return rows


def draw_shape_labels(settings, region):
    """POST_PIXEL pass: the text of each shape, centered and rotated with it."""
    view = region.view2d
    # view_to_region returns whole pixels, so one canvas unit would always measure 1:
    # measure over a long span instead.
    span = 1000.0
    origin = view.view_to_region(0.0, 0.0, clip=False)
    far = view.view_to_region(span, 0.0, clip=False)
    pixels_per_unit = abs(far[0] - origin[0]) / span
    if pixels_per_unit <= 0:
        return
    for index in shape_draw_indices(settings):
        item = settings.images[index]
        if not item.shape_show_text:
            continue
        value = ' '.join(line.value for line in item.text_lines if line.value).strip()
        if not value:
            continue
        # The lettering has a fixed size on the canvas, like the shape: it grows and
        # shrinks with the zoom. The text is wrapped in canvas units, at a fixed
        # reference size, so the line breaks never change while zooming.
        unit_size = item.text_font_size * item.scale_master
        font_size = unit_size * pixels_per_unit
        if font_size < 4 or font_size > 1024:
            continue  # too small to read, or larger than any font can draw
        width, height = geometry.shape_extent(item)
        cx, cy = view.view_to_region(item.location[0], item.location[1], clip=False)
        if cx < -width * pixels_per_unit or cx > region.width + width * pixels_per_unit:
            continue
        if cy < -height * pixels_per_unit or cy > region.height + height * pixels_per_unit:
            continue
        padding = 6.0 * item.scale_master
        box_width = width - 2 * padding
        box_height = height - 2 * padding
        max_rows = int(box_height // (unit_size * 1.3))
        if box_width < unit_size or max_rows < 1:
            continue
        blf.size(0, TEXT_REFERENCE_SIZE)
        rows = _fit_rows(value, box_width * TEXT_REFERENCE_SIZE / unit_size, max_rows)
        blf.size(0, font_size)
        line_height = font_size * 1.3
        total = line_height * len(rows)
        color = (*item.text_color, item.opacity)
        angle = math.radians(item.rotation)
        blf.color(0, *color)
        blf.enable(0, blf.ROTATION)
        blf.rotation(0, angle)
        shadow = enable_soft_text_shadow(item.text_color)
        try:
            for number, row in enumerate(rows):
                if not row:
                    continue
                row_width = blf.dimensions(0, row)[0]
                local = (-row_width * 0.5,
                         total * 0.5 - line_height * (number + 0.5) - font_size * 0.3)
                dx, dy = geometry.rotate(local, item.rotation)
                draw_canvas_text(0, row, cx + dx, cy + dy, color, font_size)
        finally:
            if shadow:
                disable_soft_text_shadow()
            blf.rotation(0, 0.0)
            blf.disable(0, blf.ROTATION)
