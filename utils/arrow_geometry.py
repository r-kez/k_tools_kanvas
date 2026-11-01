"""Canvas-space arrow endpoints and attachment to Kanvas content."""

import math
import blf

from .gpu.gpu_common import get_prefs, rotate_point
from .item_geometry import item_bounds


def _item_by_id(settings, item_id):
    return next((item for item in settings.images if item.item_id == item_id), None)


def image_uv_at(item, point):
    """Return source-image coordinates for a point inside a transformed image."""
    image = item.image_data
    if image is None or image.size[0] <= 0 or image.size[1] <= 0:
        return None
    width = image.size[0] * item.scale_xy[0] * item.scale_master
    height = image.size[1] * item.scale_xy[1] * item.scale_master
    if abs(width) < 1e-6 or abs(height) < 1e-6:
        return None
    unrotated = rotate_point(point, item.location, -item.rotation)
    dx = unrotated[0] - item.location[0]
    dy = unrotated[1] - item.location[1]
    shear_x, shear_y = item.shear_xy
    determinant = 1.0 - shear_x * shear_y
    if abs(determinant) < 1e-6:
        return None
    local_x = (dx - shear_x * dy) / determinant
    local_y = (dy - shear_y * dx) / determinant
    u = local_x / width + 0.5
    v = local_y / height + 0.5
    if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
        return None
    return (1.0 - u if item.flip_h else u,
            1.0 - v if item.flip_v else v)


def image_point_from_uv(item, uv):
    image = item.image_data
    if image is None or image.size[0] <= 0 or image.size[1] <= 0:
        return None
    u = 1.0 - uv[0] if item.flip_h else uv[0]
    v = 1.0 - uv[1] if item.flip_v else uv[1]
    x = (u - 0.5) * image.size[0] * item.scale_xy[0] * item.scale_master
    y = (v - 0.5) * image.size[1] * item.scale_xy[1] * item.scale_master
    shear_x, shear_y = item.shear_xy
    sheared = (item.location[0] + x + shear_x * y,
               item.location[1] + y + shear_y * x)
    return rotate_point(sheared, item.location, item.rotation)


def text_anchor_points(item):
    left, bottom, right, top = item_bounds(item)
    cx, cy = (left + right) * 0.5, (bottom + top) * 0.5
    return [((0.0, 0.5), (left, cy)),
            ((1.0, 0.5), (right, cy)),
            ((0.5, 0.0), (cx, bottom)),
            ((0.5, 1.0), (cx, top))]


def checklist_anchor_points(item):
    """Visible task rows, with one anchor on each side of the card."""
    if not item.text_checklist:
        return []
    from .gpu.gpu_text import _checklist_lines, _top_band_height

    left, bottom, right, top = item_bounds(item)
    scale = item.text_scale
    font_size = max(1, round(item.text_font_size * scale))
    padding = 12 * scale
    header_height = _top_band_height(item, font_size)
    blf.size(0, font_size)
    rows, _ = _checklist_lines(item, right - left - 2 * padding,
                                top - bottom - header_height, font_size, padding)
    anchors = []
    for row_index, (_, task_index, first) in enumerate(rows):
        if not first:
            continue
        line_id = item.text_lines[task_index].line_id
        if not line_id:
            continue
        y = top - padding - header_height - font_size * 0.5 - row_index * font_size * 1.3
        anchors.extend(((line_id, 'LEFT', (left, y)),
                        (line_id, 'RIGHT', (right, y))))
    return anchors


def image_anchor_points(item):
    """Corners and edge centers in source UV, following image transforms."""
    source_uvs = ((0.0, 0.0), (0.5, 0.0), (1.0, 0.0),
                  (1.0, 0.5), (1.0, 1.0), (0.5, 1.0),
                  (0.0, 1.0), (0.0, 0.5))
    return [(uv, position) for uv in source_uvs
            if (position := image_point_from_uv(item, uv)) is not None]


def endpoint(settings, arrow, side):
    stored = tuple(getattr(arrow, side))
    item_id = getattr(arrow, side + '_item_id')
    if not item_id:
        return stored
    item = _item_by_id(settings, item_id)
    if item is None:
        return stored
    uv = getattr(arrow, side + '_uv')
    if item.item_type == 'IMAGE':
        return image_point_from_uv(item, uv) or stored
    if item.item_type == 'TEXT':
        line_id = getattr(arrow, side + '_line_id')
        if line_id and item.text_checklist:
            anchors = checklist_anchor_points(item)
            position = next((point for anchor_id, anchor_side, point in anchors
                             if anchor_id == line_id
                             and anchor_side == ('LEFT' if uv[0] < 0.5 else 'RIGHT')),
                            None)
            return position or stored
        left, bottom, right, top = item_bounds(item)
        return (left + uv[0] * (right - left),
                bottom + uv[1] * (top - bottom))
    return stored


def set_endpoint(arrow, side, point, candidate=None):
    setattr(arrow, side, point)
    setattr(arrow, side + '_item_id', candidate[0] if candidate else '')
    setattr(arrow, side + '_line_id', candidate[3] if candidate and len(candidate) > 3 else '')
    if candidate:
        setattr(arrow, side + '_uv', candidate[1])


def capture_selected_arrow_move(settings, moving_item_ids=()):
    """Capture arrows once so repeated drag updates cannot accumulate offsets."""
    moving_ids = set(moving_item_ids)
    snapshots = []
    for arrow in settings.arrows:
        if not arrow.is_selected or arrow.is_locked:
            continue
        sides = {}
        for side in ('start', 'end'):
            anchor_id = getattr(arrow, side + '_item_id')
            sides[side] = {
                'stored': tuple(getattr(arrow, side)),
                'effective': endpoint(settings, arrow, side),
                'item_id': anchor_id,
                'uv': tuple(getattr(arrow, side + '_uv')),
                'line_id': getattr(arrow, side + '_line_id'),
                'follows': bool(anchor_id and anchor_id in moving_ids),
            }
        snapshots.append((arrow, sides))
    return snapshots


def translate_selected_arrows(snapshots, dx, dy):
    """Keep moving-item anchors; detach other ends and shift them with the group."""
    for arrow, sides in snapshots:
        for side, state in sides.items():
            if state['follows']:
                continue
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                setattr(arrow, side, state['stored'])
                setattr(arrow, side + '_item_id', state['item_id'])
                setattr(arrow, side + '_uv', state['uv'])
                setattr(arrow, side + '_line_id', state['line_id'])
                continue
            point = state['effective']
            set_endpoint(arrow, side, (point[0] + dx, point[1] + dy))


def restore_selected_arrows(snapshots):
    for arrow, sides in snapshots:
        for side, state in sides.items():
            setattr(arrow, side, state['stored'])
            setattr(arrow, side + '_item_id', state['item_id'])
            setattr(arrow, side + '_uv', state['uv'])
            setattr(arrow, side + '_line_id', state['line_id'])


def curve_midpoint(settings, arrow):
    start = endpoint(settings, arrow, 'start')
    end = endpoint(settings, arrow, 'end')
    return ((start[0] + end[0]) * 0.5 + arrow.curve_offset[0],
            (start[1] + end[1]) * 0.5 + arrow.curve_offset[1])


def curve_points(settings, arrow, segments=24):
    """Quadratic curve whose visible midpoint is the draggable control handle."""
    start = endpoint(settings, arrow, 'start')
    end = endpoint(settings, arrow, 'end')
    middle = curve_midpoint(settings, arrow)
    control = (2 * middle[0] - (start[0] + end[0]) * 0.5,
               2 * middle[1] - (start[1] + end[1]) * 0.5)
    return [((1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t * t * end[0],
             (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t * t * end[1])
            for t in (i / segments for i in range(segments + 1))]


def curve_intersects_rect(settings, arrow, rect):
    """Test the visible curve against a canvas-space selection rectangle."""
    left, bottom, right, top = rect
    points = curve_points(settings, arrow)
    if any(left <= x <= right and bottom <= y <= top for x, y in points):
        return True
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t_min, t_max = 0.0, 1.0
        for p, q in ((-dx, a[0] - left), (dx, right - a[0]),
                     (-dy, a[1] - bottom), (dy, top - a[1])):
            if abs(p) < 1e-12:
                if q < 0:
                    break
            elif p < 0:
                t_min = max(t_min, q / p)
            else:
                t_max = min(t_max, q / p)
            if t_min > t_max:
                break
        else:
            return True
    return False


def rounded_head_arms(points, thickness):
    """Endpoints of the open V head, oriented by the curve's final tangent."""
    end = points[-1]
    before = next((p for p in reversed(points[:-1]) if math.dist(p, end) > 1e-6), None)
    if before is None:
        return end, end
    dx, dy = end[0] - before[0], end[1] - before[1]
    span = math.hypot(dx, dy)
    dx, dy = dx / span, dy / span
    length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    head_length = min(max(20.0, thickness * 6.5), length * 0.42)
    spread = min(max(9.0, thickness * 2.5), head_length * 0.75)
    base_x, base_y = end[0] - dx * head_length, end[1] - dy * head_length
    return ((base_x - dy * spread, base_y + dx * spread),
            (base_x + dy * spread, base_y - dx * spread))


def polyline_length(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def slice_polyline(points, start, end):
    """The part of a polyline between two arc lengths (clamped to its ends)."""
    total = polyline_length(points)
    start, end = max(0.0, start), min(total, end)
    if end - start <= 1e-9:
        return []
    result, walked = [], 0.0
    for a, b in zip(points, points[1:]):
        segment = math.dist(a, b)
        if segment <= 1e-12:
            continue
        low, high = walked, walked + segment
        walked = high
        if high <= start or low >= end:
            continue
        t0 = max(0.0, (start - low) / segment)
        t1 = min(1.0, (end - low) / segment)
        first = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
        last = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
        if not result:
            result.append(first)
        result.append(last)
    return result


def dash_pattern(line_style, thickness):
    """(dash, gap) lengths in canvas units; dots are zero-length dashes with round caps."""
    if line_style == 'DASHED':
        return 5.0 * thickness + 6.0, 3.0 * thickness + 4.0
    if line_style == 'DOTTED':
        return 0.05, 2.2 * thickness + 3.0
    return 0.0, 0.0


def dash_polylines(points, dash, gap):
    """Split a polyline into dashes of `dash` length separated by `gap`."""
    if dash <= 0 or gap < 0:
        return [list(points)] if len(points) > 1 else []
    total = polyline_length(points)
    pieces, position = [], 0.0
    while position < total:
        piece = slice_polyline(points, position, min(position + dash, total))
        if len(piece) > 1:
            pieces.append(piece)
        position += dash + gap
    return pieces


def head_reach(thickness):
    """Arc length a head needs at one end of an arrow (covers both head styles)."""
    return max(20.0, thickness * 6.5, 12.0 + thickness * 0.5) / 0.42


def _distance_to_segment(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-8:
        return math.dist(point, a)
    t = max(0.0, min(1.0, ((point[0] - a[0]) * dx
                             + (point[1] - a[1]) * dy) / length_sq))
    return math.dist(point, (a[0] + dx * t, a[1] + dy * t))


def anchor_candidate(settings, point, pixel_size):
    """Snap near visible anchors, or attach at an exact point inside an image."""
    cards = sorted((item for item in settings.images
                    if item.item_type == 'TEXT' and item.show_in_editor),
                   key=lambda item: item.z_index, reverse=True)
    radius = 14.0 * pixel_size
    for card in cards:
        bounds = item_bounds(card)
        if not (bounds[0] - radius <= point[0] <= bounds[2] + radius
                and bounds[1] - radius <= point[1] <= bounds[3] + radius):
            continue
        if card.text_checklist:
            anchors = checklist_anchor_points(card)
            if anchors:
                line_id, anchor_side, anchor = min(
                    anchors, key=lambda entry: math.dist(point, entry[2]))
                if math.dist(point, anchor) <= radius:
                    uv = (0.0 if anchor_side == 'LEFT' else 1.0, 0.5)
                    return card.item_id, uv, anchor, line_id
                continue
        uv, anchor = min(text_anchor_points(card),
                         key=lambda pair: math.dist(point, pair[1]))
        return card.item_id, uv, anchor

    images = sorted((item for item in settings.images
                     if item.item_type == 'IMAGE' and item.show_in_editor
                     and item.image_data),
                    key=lambda item: item.z_index, reverse=True)
    for item in images:
        anchors = image_anchor_points(item)
        if anchors:
            uv, anchor = min(anchors, key=lambda pair: math.dist(point, pair[1]))
            if math.dist(point, anchor) <= radius:
                return item.item_id, uv, anchor
        uv = image_uv_at(item, point)
        if uv is not None:
            return item.item_id, uv, point
    return None


def detach_item_anchors(settings, item_id):
    """Keep an arrow in place if its target is deleted."""
    for arrow in settings.arrows:
        for side in ('start', 'end'):
            if getattr(arrow, side + '_item_id') == item_id:
                set_endpoint(arrow, side, endpoint(settings, arrow, side))


def hit_arrow(settings, point, pixel_size):
    """Return arrow index and handle, with endpoint handles taking priority."""
    radius = 9.0 * pixel_size
    prefs = get_prefs()
    rounded_style = bool(prefs and prefs.arrow_style == 'ROUNDED')
    for index in reversed(range(len(settings.arrows))):
        arrow = settings.arrows[index]
        if arrow.is_locked:
            continue
        start = endpoint(settings, arrow, 'start')
        end = endpoint(settings, arrow, 'end')
        if math.dist(point, end) <= radius:
            return index, 'end'
        if math.dist(point, start) <= radius:
            return index, 'start'
        if index == settings.active_arrow_index and math.dist(
                point, curve_midpoint(settings, arrow)) <= radius:
            return index, 'curve'
        points = curve_points(settings, arrow)
        for a, b in zip(points, points[1:]):
            if _distance_to_segment(point, a, b) <= radius * 0.65:
                return index, 'body'
        if rounded_style:
            arms = rounded_head_arms(points, arrow.thickness)
            hit_radius = max(radius * 0.65, arrow.thickness * 0.5)
            if any(_distance_to_segment(point, base, end) <= hit_radius for base in arms):
                return index, 'body'
    return None, None
