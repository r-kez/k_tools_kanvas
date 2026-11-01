"""Draw Kanvas arrows and temporary attachment targets."""

import math

import blf
import gpu
from gpu_extras.batch import batch_for_shader
from .gpu_theme import (draw_glass_surface, draw_rounded_border,
                        draw_rounded_fill, glass_enabled, selection_color,
                        studio_enabled, enable_soft_text_shadow,
                        disable_soft_text_shadow, draw_canvas_text)

def _triangles(shader, vertices, color):
    if not vertices:
        return
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, 'TRIS', {'pos': vertices}).draw(shader)


def _square(center, radius):
    x, y = center
    return [(x - radius, y - radius), (x + radius, y - radius),
            (x + radius, y + radius), (x - radius, y - radius),
            (x + radius, y + radius), (x - radius, y + radius)]


def _antialias_fringe(polygon, feather, color):
    """One transparent pixel around an arrow silhouette, in canvas units."""
    vertices = []
    colors = []
    normals = []
    opaque = tuple(color)
    transparent = (*color[:3], 0.0)
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        dx = next_point[0] - point[0]
        dy = next_point[1] - point[1]
        length = math.hypot(dx, dy)
        if length < 1e-8:
            return [], []
        # The arrow perimeter is clockwise, so the left normal points out.
        nx, ny = -dy * feather / length, dx * feather / length
        normals.append((nx, ny))
        outer_a = (point[0] + nx, point[1] + ny)
        outer_b = (next_point[0] + nx, next_point[1] + ny)
        vertices.extend((point, next_point, outer_b,
                         point, outer_b, outer_a))
        colors.extend((opaque, opaque, transparent,
                       opaque, transparent, transparent))
    for index, point in enumerate(polygon):
        previous = polygon[index - 1]
        following = polygon[(index + 1) % len(polygon)]
        incoming = (point[0] - previous[0], point[1] - previous[1])
        outgoing = (following[0] - point[0], following[1] - point[1])
        # Fill only convex outside corners; the two adjacent edge strips
        # otherwise leave a one-pixel wedge at the tip and tail.
        if incoming[0] * outgoing[1] - incoming[1] * outgoing[0] >= 0:
            continue
        prev_normal = normals[index - 1]
        next_normal = normals[index]
        vertices.extend((point,
                         (point[0] + prev_normal[0], point[1] + prev_normal[1]),
                         (point[0] + next_normal[0], point[1] + next_normal[1])))
        colors.extend((opaque, transparent, transparent))
    return vertices, colors


def _rounded_stroke(points, radius, cap_steps=8):
    """Triangle mesh and clockwise contour for a round-capped polyline."""
    points = [point for i, point in enumerate(points)
              if i == 0 or math.dist(point, points[i - 1]) > 1e-6]
    if len(points) < 2 or radius <= 0:
        return [], []
    directions = []
    normals = []
    for i, point in enumerate(points):
        before = points[max(0, i - 1)]
        after = points[min(len(points) - 1, i + 1)]
        dx, dy = after[0] - before[0], after[1] - before[1]
        span = max(math.hypot(dx, dy), 1e-8)
        direction = (dx / span, dy / span)
        directions.append(direction)
        normals.append((-direction[1], direction[0]))
    left = [(p[0] + n[0] * radius, p[1] + n[1] * radius)
            for p, n in zip(points, normals)]
    right = [(p[0] - n[0] * radius, p[1] - n[1] * radius)
             for p, n in zip(points, normals)]
    geometry = []
    for i in range(len(points) - 1):
        geometry.extend((left[i], right[i], right[i + 1],
                         left[i], right[i + 1], left[i + 1]))

    def cap_point(center, direction, angle):
        dx, dy = direction
        return (center[0] + radius * (dx * math.cos(angle) - dy * math.sin(angle)),
                center[1] + radius * (dy * math.cos(angle) + dx * math.sin(angle)))

    end_arc = [cap_point(points[-1], directions[-1],
                         math.pi * 0.5 - math.pi * i / cap_steps)
               for i in range(1, cap_steps)]
    start_arc = [cap_point(points[0], directions[0],
                           -math.pi * 0.5 - math.pi * i / cap_steps)
                 for i in range(1, cap_steps)]
    for center, arc in ((points[-1], [left[-1], *end_arc, right[-1]]),
                        (points[0], [right[0], *start_arc, left[0]])):
        for a, b in zip(arc, arc[1:]):
            geometry.extend((center, a, b))
    return geometry, left + end_arc + list(reversed(right)) + start_arc


def _draw_rounded_arrow(shader, smooth_shader, points, arrow, pixel_size, color):
    from ..arrow_geometry import rounded_head_arms

    radius = arrow.thickness * 0.5
    arms = rounded_head_arms(points, arrow.thickness)
    geometry, fringe, fringe_colors = [], [], []
    for stroke in (points, (arms[0], points[-1]), (arms[1], points[-1])):
        triangles, contour = _rounded_stroke(stroke, radius)
        geometry.extend(triangles)
        if contour:
            vertices, colors = _antialias_fringe(
                contour, min(pixel_size, radius * 0.5), color)
            fringe.extend(vertices)
            fringe_colors.extend(colors)
    if fringe:
        smooth_shader.bind()
        batch_for_shader(smooth_shader, 'TRIS', {
            'pos': fringe, 'color': fringe_colors,
        }).draw(smooth_shader)
    _triangles(shader, geometry, color)


def _filled_head_dimensions(thickness, length):
    """Arrow dimensions in canvas units, independent of editor zoom."""
    half_width = thickness * 0.5
    return (half_width,
            min(12.0 + half_width, length * 0.45),
            max(5.0, half_width * 2.8))


def draw_arrows(settings, pixel_size):
    from ..arrow_geometry import (curve_midpoint, curve_points,
                                  image_anchor_points)
    from .gpu_common import get_prefs

    prefs = get_prefs()
    modern = studio_enabled()
    endpoint_handle_color = (tuple(prefs.color_arrow_endpoint_handles)
                             if prefs else (1.0, 1.0, 1.0, 1.0))
    curve_handle_color = (tuple(prefs.color_arrow_curve_handle)
                          if prefs else (1.0, 1.0, 1.0, 1.0))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    smooth_shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        for index, arrow in enumerate(settings.arrows):
            points = curve_points(settings, arrow)
            start, end = points[0], points[-1]
            length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
            if length < 1e-6:
                continue
            color = tuple(arrow.color)
            if prefs and prefs.arrow_style == 'ROUNDED':
                _draw_rounded_arrow(shader, smooth_shader, points,
                                    arrow, pixel_size, color)
            else:
                half_width, head_length, head_width = _filled_head_dimensions(
                    arrow.thickness, length)
                shaft = [start]
                remaining = length - head_length
                for a, b in zip(points, points[1:]):
                    segment = math.dist(a, b)
                    if remaining > segment:
                        shaft.append(b)
                        remaining -= segment
                    else:
                        factor = remaining / segment if segment else 0.0
                        shaft.append((a[0] + (b[0] - a[0]) * factor,
                                      a[1] + (b[1] - a[1]) * factor))
                        break
                left, right = [], []
                for i, p in enumerate(shaft):
                    before, after = shaft[max(0, i - 1)], shaft[min(len(shaft) - 1, i + 1)]
                    dx, dy = after[0] - before[0], after[1] - before[1]
                    span = max(1e-8, math.hypot(dx, dy))
                    nx, ny = -dy / span, dx / span
                    left.append((p[0] + nx * half_width, p[1] + ny * half_width))
                    right.append((p[0] - nx * half_width, p[1] - ny * half_width))
                dx, dy = end[0] - shaft[-1][0], end[1] - shaft[-1][1]
                span = max(1e-8, math.hypot(dx, dy))
                nx, ny = -dy / span, dx / span
                head_left = (shaft[-1][0] + nx * head_width,
                             shaft[-1][1] + ny * head_width)
                head_right = (shaft[-1][0] - nx * head_width,
                              shaft[-1][1] - ny * head_width)
                perimeter = left + [head_left, end, head_right] + list(reversed(right))
                geometry = []
                for i in range(len(shaft) - 1):
                    geometry.extend((left[i], right[i], right[i + 1],
                                     left[i], right[i + 1], left[i + 1]))
                geometry.extend((end, head_left, head_right))
                _triangles(shader, geometry, color)
                fringe, colors = _antialias_fringe(
                    perimeter, min(pixel_size, half_width * 0.5), color)
                if fringe:
                    smooth_shader.bind()
                    batch_for_shader(smooth_shader, 'TRIS', {
                        'pos': fringe, 'color': colors,
                    }).draw(smooth_shader)
            if not arrow.is_locked and (index == settings.active_arrow_index or arrow.is_selected):
                for point in (start, end):
                    _triangles(shader, _square(point, 4.5 * pixel_size),
                               (0.035, 0.055, 0.075, 0.95) if modern
                               else (0.08, 0.08, 0.08, 0.95))
                    _triangles(shader, _square(point, 3.0 * pixel_size),
                               endpoint_handle_color)
                point = curve_midpoint(settings, arrow)
                _triangles(shader, _square(point, 5.0 * pixel_size),
                           (0.035, 0.055, 0.075, 0.95) if modern
                           else (0.08, 0.08, 0.08, 0.95))
                _triangles(shader, _square(point, 3.5 * pixel_size),
                           curve_handle_color)

        if settings.arrow_dragging:
            if settings.arrow_quick_active:
                for item in settings.images:
                    if item.item_type != 'IMAGE' or not item.show_in_editor or not item.image_data:
                        continue
                    for _, point in image_anchor_points(item):
                        _triangles(shader, _square(point, 2.5 * pixel_size),
                                   (0.1, 0.55, 1.0, 0.9))
            elif settings.arrow_hover_valid and settings.arrow_hover_item_id:
                hovered = next((item for item in settings.images
                                if item.item_id == settings.arrow_hover_item_id
                                and item.item_type == 'IMAGE'
                                and item.show_in_editor), None)
                if hovered:
                    for _, point in image_anchor_points(hovered):
                        _triangles(shader, _square(point, 2.5 * pixel_size),
                                   (0.1, 0.55, 1.0, 0.9))
            if settings.arrow_hover_valid:
                _triangles(shader,
                           _square(settings.arrow_hover, 6.0 * pixel_size),
                           (1.0, 0.85, 0.15, 0.95))
    finally:
        gpu.state.blend_set(old_blend)


def draw_text_anchor_handles(settings, region):
    """Keep text-card attachment handles visible above card backgrounds."""
    if not settings.arrow_dragging:
        return
    from ..arrow_geometry import checklist_anchor_points, text_anchor_points

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        for card in settings.images:
            if card.item_type != 'TEXT' or not card.show_in_editor:
                continue
            points = (point for _, _, point in checklist_anchor_points(card)) \
                if card.text_checklist else (point for _, point in text_anchor_points(card))
            for point in points:
                x, y = region.view2d.view_to_region(*point, clip=False)
                _triangles(shader, _square((x, y), 4.0), (0.1, 0.55, 1.0, 0.9))
        if settings.arrow_hover_valid and settings.arrow_hover_item_id:
            if any(item.item_id == settings.arrow_hover_item_id
                   and item.item_type == 'TEXT' for item in settings.images):
                x, y = region.view2d.view_to_region(*settings.arrow_hover, clip=False)
                _triangles(shader, _square((x, y), 6.0), (1.0, 0.85, 0.15, 0.95))
    finally:
        gpu.state.blend_set(old_blend)


def _label_center_y(anchor_y, height, pad_y, selected, region_height,
                    zoom_scale=1.0):
    if not selected:
        return anchor_y
    offset = 16 * zoom_scale + height * 0.5 + pad_y
    return anchor_y + offset if anchor_y + offset + height * 0.5 + pad_y <= region_height else anchor_y - offset


def _label_width_limit(start, end, region_width, padding=7, cap=240.0):
    """Keep the whole label box within 80% of the arrow's screen span."""
    return min(cap, region_width - 24.0,
               math.dist(start, end) * 0.8 - 2 * padding)


def draw_arrow_labels(settings, region):
    """Draw readable labels at the current midpoint, including attached arrows."""
    from ..arrow_geometry import curve_midpoint, endpoint

    if not any(arrow.label.strip() for arrow in settings.arrows):
        return
    view = region.view2d
    view_pixel_size = abs(view.region_to_view(1, 0)[0]
                          - view.region_to_view(0, 0)[0])
    zoom_scale = 1.0 / max(view_pixel_size, 1e-8)
    font_size = min(256, round(13 * zoom_scale))
    if font_size < 7:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    modern = studio_enabled()
    try:
        for index, arrow in enumerate(settings.arrows):
            label = arrow.label.strip()
            if not label:
                continue
            x, y = view.view_to_region(*curve_midpoint(settings, arrow), clip=False)
            if x < -150 or x > region.width + 150 or y < -20 or y > region.height + 20:
                continue
            blf.size(0, font_size)
            start = view.view_to_region(*endpoint(settings, arrow, 'start'), clip=False)
            end = view.view_to_region(*endpoint(settings, arrow, 'end'), clip=False)
            max_width = _label_width_limit(start, end, region.width,
                                           padding=7 * zoom_scale,
                                           cap=240 * zoom_scale)
            if max_width < blf.dimensions(0, '…')[0]:
                continue
            if blf.dimensions(0, label)[0] > max_width:
                while label and blf.dimensions(0, label + '…')[0] > max_width:
                    label = label[:-1]
                label = label + '…' if label else '…'
            width, height = blf.dimensions(0, label)
            pad_x, pad_y = 7 * zoom_scale, 5 * zoom_scale
            y = _label_center_y(y, height, pad_y,
                                index == settings.active_arrow_index and not arrow.is_locked,
                                region.height, zoom_scale)
            left, right = x - width * 0.5 - pad_x, x + width * 0.5 + pad_x
            bottom, top = y - height * 0.5 - pad_y, y + height * 0.5 + pad_y
            if modern:
                bounds = (left, bottom, right, top)
                radius = 5 * zoom_scale
                if glass_enabled():
                    draw_glass_surface(shader, bounds, radius,
                                       (0.25, 0.4, 0.5), 0.85)
                else:
                    draw_rounded_fill(shader, bounds, radius,
                                      (0.035, 0.055, 0.075, 0.94))
                draw_rounded_border(shader, bounds, radius, zoom_scale,
                                    (0.75, 0.88, 1.0, 0.4) if glass_enabled()
                                    else (*selection_color()[:3], 0.48))
            else:
                background = [(left, bottom), (right, bottom), (right, top),
                              (left, bottom), (right, top), (left, top)]
                shader.bind()
                shader.uniform_float('color', (0.025, 0.03, 0.04, 0.86))
                batch_for_shader(shader, 'TRIS', {'pos': background}).draw(shader)
            blf.color(0, 1.0, 1.0, 1.0, 1.0)
            shadow_enabled = enable_soft_text_shadow((1.0, 1.0, 1.0))
            try:
                draw_canvas_text(0, label, x - width * 0.5,
                                 y - height * 0.5, (1.0, 1.0, 1.0, 1.0),
                                 font_size)
            finally:
                if shadow_enabled:
                    disable_soft_text_shadow()
    finally:
        gpu.state.blend_set(previous_blend)
