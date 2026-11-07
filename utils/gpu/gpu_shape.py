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


def _outline_strokes(points, style, width, edges=None):
    """Polylines that draw the closed outline.

    Solid: one stroke per edge, so the round caps give the corners a round join. A
    curved edge is many points but still one stroke (`edges` gives the edge index of
    each point), instead of one stroke per flattened segment.
    """
    loop = list(points) + [points[0]]
    if style == 'SOLID':
        if edges is None:
            return [[a, b] for a, b in zip(loop, loop[1:])]
        strokes, current = [], [points[0]]
        for i in range(1, len(loop)):
            current.append(loop[i])
            if i == len(points) or edges[i] != edges[i - 1]:
                strokes.append(current)
                current = [loop[i]]
        return strokes
    from ..arrow_geometry import dash_pattern, dash_polylines
    dash, gap = dash_pattern(style, width)
    return dash_polylines(loop, dash, gap)


def _visible(item, view_bounds):
    left, bottom, right, top = geometry.bounds(item)
    margin = item.shape_line_width
    return not (right + margin < view_bounds[0] or left - margin > view_bounds[2]
                or top + margin < view_bounds[1] or bottom - margin > view_bounds[3])


_geometry_cache = {}


def _stroke_geometry(polylines, thickness, pixel_size, color):
    """Same triangles as `_draw_plain_strokes`, returned instead of drawn."""
    from .gpu_arrow import _rounded_stroke
    radius = thickness * 0.5
    triangles, fringe, fringe_colors = [], [], []
    for stroke in polylines:
        mesh, contour = _rounded_stroke(stroke, radius)
        triangles.extend(mesh)
        if contour:
            vertices, colors = _antialias_fringe(contour, min(pixel_size, radius * 0.5), color)
            fringe.extend(vertices)
            fringe_colors.extend(colors)
    return triangles, fringe, fringe_colors


def shape_draw_geometry(item, pixel_size):
    """Everything `_draw_body` sends to the GPU, cached until the shape, its look or the
    zoom changes. A redraw of an unchanged shape (hover, other items moving, the
    cursor) then costs no geometry work at all, however curved it is."""
    opacity = item.opacity
    signature = (geometry.item_records(item), item.shape_curve_resolution,
                 tuple(item.location), item.rotation, item.shape_width, item.shape_height,
                 item.scale_master, pixel_size, opacity, item.shape_show_fill,
                 item.shape_fill_opacity, tuple(item.shape_fill_color), item.shape_show_outline,
                 tuple(item.shape_line_color), item.shape_line_width, item.shape_line_style)
    key = item.as_pointer()
    cached = _geometry_cache.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    points = geometry.outline(item)
    result = {'fill': None, 'line': None}
    line_color = (*item.shape_line_color, opacity)
    if len(points) == 2:
        # A polygon being drawn click by click: its first segment.
        result['line'] = (_stroke_geometry([points], item.shape_line_width, pixel_size,
                                           line_color), line_color)
    elif len(points) >= geometry.MIN_VERTICES:
        if item.shape_show_fill and item.shape_fill_opacity * opacity > 0.0:
            color = (*item.shape_fill_color, item.shape_fill_opacity * opacity)
            triangles = [points[i] for triangle in geometry.fill_triangles(item)
                         for i in triangle]
            fringe, fringe_colors = _antialias_fringe(_clockwise(points), pixel_size, color)
            result['fill'] = (triangles, fringe, fringe_colors, color)
        if item.shape_show_outline:
            edges = [edge for _, edge, _ in geometry.curve_units(item)]
            strokes = _outline_strokes(points, item.shape_line_style,
                                       item.shape_line_width, edges)
            result['line'] = (_stroke_geometry(strokes, item.shape_line_width, pixel_size,
                                               line_color), line_color)
    if len(_geometry_cache) > 512:
        _geometry_cache.clear()
    _geometry_cache[key] = (signature, result)
    return result


def _draw_body(shader, smooth, item, pixel_size):
    parts = shape_draw_geometry(item, pixel_size)
    if parts['fill'] is not None:
        triangles, fringe, fringe_colors, color = parts['fill']
        _triangles(shader, triangles, color)
        if fringe:
            smooth.bind()
            batch_for_shader(smooth, 'TRIS', {
                'pos': fringe, 'color': fringe_colors}).draw(smooth)
    if parts['line'] is not None:
        (triangles, fringe, fringe_colors), color = parts['line']
        if fringe:
            smooth.bind()
            batch_for_shader(smooth, 'TRIS', {
                'pos': fringe, 'color': fringe_colors}).draw(smooth)
        _triangles(shader, triangles, color)


def _draw_handle(shader, point, pixel_size, radius=4.5, fill=HANDLE_LIGHT):
    _triangles(shader, _square(point, radius * pixel_size), HANDLE_DARK)
    _triangles(shader, _square(point, (radius - 1.5) * pixel_size), fill)


def _sole_selection(settings, item):
    return (item.is_selected and not item.is_locked
            and sum(1 for other in settings.images if other.is_selected) == 1)


def _draw_selection(shader, smooth, settings, item, pixel_size):
    color = selection_color()
    thickness = max(1.0, 1.5) * pixel_size
    editing = item.shape_edit_vertices and _sole_selection(settings, item)
    if editing:
        outline = geometry.outline(item)
        edges = [edge for _, edge, _ in geometry.curve_units(item)]
        _draw_plain_strokes(shader, smooth, _outline_strokes(outline, 'SOLID', thickness, edges),
                            thickness, pixel_size, color)
        for unit in geometry.edge_midpoints(item):
            _triangles(shader, _circle(geometry.unit_to_canvas(item, unit), 2.6 * pixel_size),
                       (*color[:3], 0.75))
        points = geometry.vertex_points(item)
        # Bezier handles of the selected vertices (Sharp vertices have none).
        for index, (vertex, point) in enumerate(zip(item.shape_vertices, points)):
            if not vertex.select or vertex.handle_type == 'SHARP':
                continue
            for handle in geometry.handle_points(item, index):
                _draw_plain_strokes(shader, smooth, [[point, handle]], max(1.0, pixel_size),
                                    pixel_size, (*color[:3], 0.8))
                _triangles(shader, _circle(handle, 4.0 * pixel_size), HANDLE_DARK)
                _triangles(shader, _circle(handle, 2.8 * pixel_size), HANDLE_LIGHT)
        selected_fill = (*color[:3], 1.0)
        for vertex, point in zip(item.shape_vertices, points):
            if vertex.select:
                # Selected vertices: larger and in the selection color.
                _draw_handle(shader, point, pixel_size, 6.0, selected_fill)
            else:
                _draw_handle(shader, point, pixel_size, 5.0)
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


# --- Edit Vertices: mode badge and shortcut panel --------------------------------------

VERTEX_EDIT_ROWS = (
    ('Click vertex', 'Select vertex'),
    ('Shift+Click vertex', 'Add / remove from selection'),
    ('Drag empty space', 'Box select (Shift adds, Ctrl removes)'),
    ('Ctrl+A / Ctrl+I', 'Select all / invert'),
    ('Drag vertex', 'Move selected vertices'),
    ('Drag edge', 'Bend edge (click selects it)'),
    ('Drag handle', 'Shape the curve'),
    ('V', 'Vertex type: Sharp / Auto / Aligned / Mirrored / Free'),
    ('Ctrl+Click edge', 'Add vertex'),
    ('X / Delete', 'Delete selected vertices'),
    ('Ctrl+Click vertex', 'Delete vertex'),
    ('Ctrl+Drag', 'Snap to grid'),
    ('Shift+Ctrl+Drag', 'Snap to fine grid'),
    ('MMB / Wheel', 'Pan / zoom'),
    ('Ctrl+Z', 'Undo'),
    ('Esc', 'Exit Edit Vertices'),
)

# Header rectangle of the panel from the last redraw, in region pixels, for click tests.
_vertex_panel = {'toggle': None}


def vertex_edit_shape(settings):
    """The shape whose vertices are being edited, or None.

    Same rule as the editing gestures: one selected, unlocked, visible shape.
    """
    index = settings.active_image_index
    item = settings.images[index] if 0 <= index < len(settings.images) else None
    if (item is None or item.item_type != 'SHAPE' or not item.shape_edit_vertices
            or not item.is_selected or item.is_locked or not item.show_in_editor
            or sum(1 for other in settings.images if other.is_selected) != 1):
        return None
    return item


def vertex_edit_title(item):
    title = f'EDIT VERTICES  |  {item.name}  |  {len(item.shape_vertices)} vertices'
    selected = sum(1 for vertex in item.shape_vertices if vertex.select)
    return f'{title}  |  {selected} selected' if selected else title


def draw_vertex_edit_overlay(settings, area, region):
    """POST_PIXEL pass: a badge naming the mode and the Shortcuts panel."""
    from .gpu_shortcuts import draw_mode_badge, draw_shortcut_panel
    item = vertex_edit_shape(settings)
    if item is None:
        _vertex_panel['toggle'] = None
        return
    draw_mode_badge(region, vertex_edit_title(item), area=area)
    _vertex_panel['toggle'] = draw_shortcut_panel(area, region, VERTEX_EDIT_ROWS)


def hit_vertex_panel_toggle(settings, region_x, region_y):
    """True when a click lands on the panel header (the minus / plus button)."""
    bounds = _vertex_panel['toggle']
    if bounds is None or vertex_edit_shape(settings) is None:
        return False
    return bounds[0] <= region_x <= bounds[2] and bounds[1] <= region_y <= bounds[3]


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
