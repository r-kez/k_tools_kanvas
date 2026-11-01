"""Lightweight visual links between checklists and their images."""

import math

import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from ..item_geometry import item_bounds
from ..checklist_links import attached_checklist_pairs
from .gpu_markup import isolated_index


def _boundary_point(bounds, toward):
    left, bottom, right, top = bounds
    x, y = (left + right) * 0.5, (bottom + top) * 0.5
    dx, dy = toward[0] - x, toward[1] - y
    if abs(dx) + abs(dy) < 1e-6:
        return x, y
    half_w, half_h = (right - left) * 0.5, (top - bottom) * 0.5
    scale = min(half_w / abs(dx) if dx else math.inf,
                half_h / abs(dy) if dy else math.inf)
    return x + dx * scale, y + dy * scale


def _append_soft_line(vertices, colors, start, end, color, pixel_size):
    """Draw a one-pixel core with transparent fringes on both sides."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return
    nx, ny = -dy / length, dx / length
    half_width = pixel_size * 0.55
    outer_width = half_width + pixel_size
    opaque = tuple(color)
    transparent = (*color[:3], 0.0)

    def side(point, distance):
        return (point[0] + nx * distance, point[1] + ny * distance)

    def quad(a, b, c, d, first_color, second_color):
        vertices.extend((a, b, c, a, c, d))
        colors.extend((first_color, second_color, second_color,
                       first_color, second_color, first_color))

    # Outer left -> inner left, then the solid center, then the right fringe.
    quad(side(start, outer_width), side(start, half_width),
         side(end, half_width), side(end, outer_width), transparent, opaque)
    quad(side(start, half_width), side(start, -half_width),
         side(end, -half_width), side(end, half_width), opaque, opaque)
    quad(side(start, -half_width), side(start, -outer_width),
         side(end, -outer_width), side(end, -half_width), opaque, transparent)


def _visible_task_rows(card, region):
    """Canvas positions of visible checklist rows, including card scrolling."""
    from .gpu_text import _scroll_layout

    layout = _scroll_layout(card, region)
    if layout is None:
        return {}
    left, _, right, _ = layout['bounds']
    cursor = layout['top'] + layout['scroll_screen']
    rows = {}
    for _, height, meta in layout['rows']:
        task_index, first = meta
        center_y = cursor - layout['font_size'] * 0.5
        if (first and layout['bottom'] <= center_y <= layout['top']
                and card.text_lines[task_index].line_id):
            rows[card.text_lines[task_index].line_id] = (
                region.view2d.region_to_view(left, center_y),
                region.view2d.region_to_view(right, center_y),
            )
        cursor -= height
    return rows


_candidate_cache = {}


def _paint_target(region, image, origin):
    """Choose a nearby painted sample that actually has non-erased color."""
    from ..arrow_geometry import image_point_from_uv
    from .gpu_markup import region_active_mask

    pixels = region_active_mask(image, region)
    if pixels is None:
        return None
    # Sampling the mask is independent of where the card is, so do it once per
    # mask version instead of scanning the whole array on every redraw.
    key = (image.item_id, region.region_id)
    memo = _candidate_cache.get(key)
    if memo is None or memo[0] is not pixels:
        candidates = _paint_candidates(region, pixels)
        if len(_candidate_cache) > 512:
            _candidate_cache.clear()
        _candidate_cache[key] = (pixels, candidates)
    else:
        candidates = memo[1]
    points = [point for uv in candidates
              if (point := image_point_from_uv(image, uv)) is not None]
    return min(points, key=lambda point: math.dist(origin, point)) if points else None


def _paint_candidates(region, pixels):
    if not np.any(pixels > 0.05):
        return []
    height, width = pixels.shape
    candidates = []
    count = len(region.dabs)
    if count:
        step = max(1, (count + 63) // 64)
        for index in range(0, count, step):
            dab = region.dabs[index]
            if dab.erase:
                continue
            u, v = dab.uv
            px = int(np.clip(u * width, 0, width - 1))
            py = int(np.clip(v * height, 0, height - 1))
            if pixels[py, px] > 0.05:
                candidates.append((u, v))
    count = len(region.polygons)
    if count:
        step = max(1, (count + 31) // 32)
        for index in range(0, count, step):
            polygon = region.polygons[index]
            if polygon.erase or not polygon.vertices:
                continue
            vertices = [tuple(vertex.uv) for vertex in polygon.vertices]
            centroid = tuple(sum(point[axis] for point in vertices) / len(vertices)
                             for axis in (0, 1))
            cx = int(np.clip(centroid[0] * width, 0, width - 1))
            cy = int(np.clip(centroid[1] * height, 0, height - 1))
            if pixels[cy, cx] > 0.05:
                candidates.append(centroid)
            else:
                for vertex_uv in vertices:
                    vx = int(np.clip(vertex_uv[0] * width, 0, width - 1))
                    vy = int(np.clip(vertex_uv[1] * height, 0, height - 1))
                    if pixels[vy, vx] > 0.05:
                        candidates.append(vertex_uv)
                        break

    if not candidates:
        ys, xs = np.nonzero(pixels > 0.05)
        if len(ys) > 0:
            step = max(1, len(ys) // 48)
            for i in range(0, len(ys), step):
                candidates.append(((xs[i] + 0.5) / width, (ys[i] + 0.5) / height))
    return candidates


def _island_targets(region, image):
    """Canvas point inside every painted island of a region."""
    from ..arrow_geometry import image_point_from_uv
    from .gpu_markup_labels import _islands_for

    points = [point for island in _islands_for(image, region)
              if (point := image_point_from_uv(image, island['uv'])) is not None]
    return points


def _task_arrow_geometry(settings, cards, region, pixel_size):
    vertices, colors, covered_pairs = [], [], set()
    if region is None:
        return vertices, colors, covered_pairs
    origins = {card_id: _visible_task_rows(card, region)
               for card_id, card in cards.items()
               if any(line.show_color_links for line in card.text_lines)}
    for image in settings.images:
        if (image.item_type != 'IMAGE' or not image.show_in_editor
                or not image.markup_visible or not image.image_data):
            continue
        for link in image.checklist_associations:
            card = cards.get(link.card_id)
            rows = origins.get(link.card_id)
            if card is None or not rows:
                continue
            lines = {line.line_id: line for line in card.text_lines
                     if line.show_color_links}
            only = isolated_index(image)
            for index, paint in enumerate(image.markup_regions):
                if (paint.checklist_card_id != card.item_id
                        or not paint.visible or paint.opacity <= 0
                        or (only >= 0 and index != only)):
                    continue
                line = lines.get(paint.checklist_line_id)
                row = rows.get(paint.checklist_line_id)
                if line is None or row is None:
                    continue
                start = row[1] if image.location[0] >= card.location[0] else row[0]
                targets = (_island_targets(paint, image)
                           if image.markup_arrows_all_islands else [])
                if not targets:
                    # Nearest painted point (also the fallback when every island
                    # is too small to be considered).
                    nearest = _paint_target(paint, image, start)
                    targets = [nearest] if nearest is not None else []
                for target in targets:
                    dx, dy = target[0] - start[0], target[1] - start[1]
                    length = math.hypot(dx, dy)
                    if length <= 12 * pixel_size:
                        continue
                    color = (*line.color, 0.88)
                    _append_soft_line(vertices, colors, start, target, color, pixel_size)
                    ux, uy = dx / length, dy / length
                    head_length, head_width = 10 * pixel_size, 5 * pixel_size
                    base = (target[0] - ux * head_length, target[1] - uy * head_length)
                    for side in (-1, 1):
                        arm = (base[0] + side * -uy * head_width,
                               base[1] + side * ux * head_width)
                        _append_soft_line(vertices, colors, arm, target, color, pixel_size)
                    covered_pairs.add((card.item_id, image.item_id))
    return vertices, colors, covered_pairs


def draw_checklist_links(settings, pixel_size=1.0, region=None):
    arrow_pairs = attached_checklist_pairs(settings)
    cards = {item.item_id: item for item in settings.images
             if item.item_type == 'TEXT' and item.text_checklist
             and item.show_in_editor}
    if not cards:
        return
    vertices, colors, _task_pairs = _task_arrow_geometry(
        settings, cards, region, pixel_size)
    suppressed_pairs = arrow_pairs
    for image in settings.images:
        if (image.item_type != 'IMAGE' or not image.show_in_editor
                or not image.checklist_associations):
            continue
        image_bounds = item_bounds(image)
        if image_bounds is None:
            continue
        image_center = tuple(image.location)
        for link in image.checklist_associations:
            card = cards.get(link.card_id)
            if card is None:
                continue
            if (card.item_id, image.item_id) in suppressed_pairs:
                continue
            card_bounds = item_bounds(card)
            start = _boundary_point(card_bounds, image_center)
            end = _boundary_point(image_bounds, tuple(card.location))
            if math.dist(start, end) < 2:
                continue
            alpha = 0.75 if card.is_selected or image.is_selected else 0.30
            color = (0.28, 0.74, 1.0, alpha)
            _append_soft_line(vertices, colors, start, end, color, pixel_size)
    if not vertices:
        return
    shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    previous_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        batch_for_shader(shader, 'TRIS', {'pos': vertices, 'color': colors}).draw(shader)
    finally:
        gpu.state.blend_set(previous_blend)
