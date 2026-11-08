"""Canvas cards and zoom-aware multiline labels for Kanvas text items."""

import blf
import gpu
import math
from bisect import bisect_right
from functools import lru_cache
from gpu_extras.batch import batch_for_shader

from ..item_geometry import item_bounds
from ..markdown import layout as markdown_layout, layout_inline as markdown_inline_layout
from .gpu_theme import (draw_glass_surface, draw_rounded_border,
                        draw_rounded_fill, glass_enabled, selection_color,
                        studio_enabled, enable_soft_text_shadow,
                        disable_soft_text_shadow, draw_canvas_text)


HANDLE_PIXELS = 14
EDIT_BUTTON_PIXELS = 22

# The pencil texture in assets/icons/pencil.png is rasterized from the
# MIT-licensed Tabler pencil outline:
# https://github.com/tabler/tabler-icons/blob/main/icons/outline/pencil.svg


def text_edit_button_bounds(item, region):
    """Keep the pencil's size proportional to the card in view space."""
    x0, y0, x1, y1 = _region_bounds(item, region.view2d)
    width, height = x1 - x0, y1 - y0
    pixel_scale = width / item.text_width
    size = item.text_font_size * pixel_scale
    if size < 3:
        return None
    if width < size * 2.4 or height < size * 1.8:
        return None
    margin = 12 * pixel_scale
    return (x1 - size - margin, y1 - size - margin, x1 - margin, y1 - margin)


def hit_test_text_edit_button(item, region, position):
    bounds = text_edit_button_bounds(item, region)
    return bool(bounds and bounds[0] <= position[0] <= bounds[2]
                and bounds[1] <= position[1] <= bounds[3])


def draw_text_edit_button(item, region):
    bounds = text_edit_button_bounds(item, region)
    if bounds is None:
        return
    x0, y0, x1, y1 = bounds
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        if studio_enabled():
            radius = max(1.0, (x1 - x0) * 0.2)
            if glass_enabled():
                draw_glass_surface(shader, bounds, radius,
                                   (0.25, 0.4, 0.5), 0.85)
            else:
                draw_rounded_fill(shader, bounds, radius, (0.035, 0.055, 0.075, 0.92))
            draw_rounded_border(shader, bounds, radius, max(0.8, (x1 - x0) * 0.045),
                                (*selection_color()[:3], 0.7 if item.is_selected else 0.32))
        else:
            batch = batch_for_shader(shader, 'TRIS', {'pos': [
                (x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1),
            ]})
            shader.bind()
            shader.uniform_float('color', (0.08, 0.10, 0.13, 0.85))
            batch.draw(shader)
        from .gpu_image import get_icon_texture
        texture = get_icon_texture('pencil')
        if texture is not None:
            icon_shader = gpu.shader.from_builtin('IMAGE_COLOR')
            icon = batch_for_shader(icon_shader, 'TRI_FAN', {
                'pos': [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                'texCoord': [(0, 0), (1, 0), (1, 1), (0, 1)],
            })
            icon_shader.bind()
            icon_shader.uniform_sampler('image', texture)
            icon_shader.uniform_float('color', (1.0, 1.0, 1.0, 1.0))
            icon.draw(icon_shader)
    finally:
        gpu.state.blend_set(old_blend)


def hit_test_text_resize(item, position, view_pixel_size):
    left, bottom, right, top = item_bounds(item)
    handle = HANDLE_PIXELS * view_pixel_size
    x, y = position
    return (right - handle <= x <= right + handle * 0.3
            and bottom - handle * 0.3 <= y <= bottom + handle)


def draw_text_card(item, view_pixel_size=1.0, region=None, grip=True):
    """The card itself; `grip` draws the resize grip in its corner (left out of an
    exported picture: it is a handle, not part of the board)."""
    if region is None:
        left, bottom, right, top = item_bounds(item)
    else:
        left, bottom, right, top = _region_bounds(item, region.view2d)
        view_pixel_size = 1.0
    if studio_enabled():
        _draw_studio_text_card(item, left, bottom, right, top, view_pixel_size,
                               (right - left) / item.text_width if region else 1.0, grip)
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        background = batch_for_shader(shader, 'TRIS', {'pos': [
            (left, bottom), (right, bottom), (right, top),
            (left, bottom), (right, top), (left, top),
        ]})
        shader.bind()
        shader.uniform_float('color', (*item.text_background, item.text_opacity))
        background.draw(shader)
        # One non-overlapping ring avoids double alpha and seams at the corners.
        thickness = min(1.5 * view_pixel_size, (right - left) * 0.25,
                        (top - bottom) * 0.25)
        border = batch_for_shader(shader, 'TRIS', {'pos': [
            (left, bottom), (right, bottom), (right, top), (left, top),
            (left + thickness, bottom + thickness),
            (right - thickness, bottom + thickness),
            (right - thickness, top - thickness),
            (left + thickness, top - thickness),
        ]}, indices=[
            (0, 1, 5), (0, 5, 4),
            (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6),
            (3, 0, 4), (3, 4, 7),
        ])
        shader.uniform_float('color', (0.0, 0.8, 1.0, 1.0) if item.is_selected
                             else (*item.text_color, 0.45))
        border.draw(shader)
        if grip and right - left >= 48 * view_pixel_size and top - bottom >= 48 * view_pixel_size:
            inset = min(14 * view_pixel_size, (right - left) * 0.18,
                        (top - bottom) * 0.18)
            pad = min(4 * view_pixel_size, inset * 0.3)
            grip = batch_for_shader(shader, 'LINES', {'pos': [
                (right - inset, bottom + pad), (right - pad, bottom + inset),
                (right - inset * 0.65, bottom + pad),
                (right - pad, bottom + inset * 0.65),
            ]})
            shader.uniform_float('color', (0.95, 0.74, 0.25, 1.0) if item.is_selected
                                 else (*item.text_color, 0.45))
            grip.draw(shader)
    finally:
        gpu.state.blend_set(old_blend)


def _draw_studio_text_card(item, left, bottom, right, top, pixel_size, scale, grip=True):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        bounds = (left, bottom, right, top)
        radius = min(10 * scale, (right - left) * 0.12, (top - bottom) * 0.12)
        shadow = min(3 * scale, max(0, radius * 0.3))
        if shadow > 0:
            draw_rounded_fill(shader, (left + shadow, bottom - shadow,
                                       right + shadow, top - shadow), radius,
                              (0.0, 0.0, 0.0, 0.22))
        glass = glass_enabled()
        if glass:
            draw_glass_surface(shader, bounds, radius,
                               item.text_background, item.text_opacity)
        else:
            draw_rounded_fill(shader, bounds, radius,
                              (*item.text_background, item.text_opacity),
                              antialias=True)
        accent = selection_color()
        border_color = ((*accent[:3], 0.95) if item.is_selected else
                        (0.75, 0.88, 1.0, 0.38) if glass else
                        (*item.text_color, 0.32))
        draw_rounded_border(shader, bounds, radius, max(1.0, 1.35 * scale),
                            border_color, antialias=True)
        # A short accent on the upper edge gives cards a clear visual hierarchy.
        if right - left > 42 * scale and top - bottom > 30 * scale:
            strip_left = left + max(radius, 12 * scale)
            strip_right = min(right - max(radius, 12 * scale), strip_left + 36 * scale)
            strip_top = top - max(2 * scale, radius * 0.32)
            draw_rounded_fill(shader, (strip_left, strip_top - 2 * scale,
                                       strip_right, strip_top), scale,
                              (*accent[:3], 0.82 if item.is_selected else 0.48))
        if grip and right - left >= 48 * scale and top - bottom >= 48 * scale:
            inset = min(14 * scale, (right - left) * 0.18, (top - bottom) * 0.18)
            pad = min(4 * scale, inset * 0.3)
            grip = batch_for_shader(shader, 'LINES', {'pos': [
                (right - inset, bottom + pad), (right - pad, bottom + inset),
                (right - inset * 0.65, bottom + pad),
                (right - pad, bottom + inset * 0.65),
            ]})
            shader.uniform_float('color', (*accent[:3], 0.9) if item.is_selected
                                 else (*item.text_color, 0.35))
            grip.draw(shader)
    finally:
        gpu.state.blend_set(old_blend)


def _wrapped_lines(text, max_width, font_id=0):
    if not text:
        return ['']
    lines = []
    current = ''
    for word in text.split(' '):
        trial = f'{current} {word}' if current else word
        if current and blf.dimensions(font_id, trial)[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
        while current and blf.dimensions(font_id, current)[0] > max_width:
            cut = max(1, len(current) - 1)
            while cut > 1 and blf.dimensions(font_id, current[:cut])[0] > max_width:
                cut -= 1
            lines.append(current[:cut])
            current = current[cut:]
    if current or not lines:
        lines.append(current)
    return lines


def _visible_lines(text_lines, max_width, max_height, font_size, padding, font_id=0):
    """Wrap in card pixels and mark the last visible line when text overflows."""
    line_height = font_size * 1.3
    available_height = max_height - 2 * padding - font_size
    max_lines = max(0, int(available_height / line_height) + 1)
    if not max_lines:
        return [], bool(text_lines)

    visible = []
    overflow = False
    for text_line in text_lines:
        for line in _wrapped_lines(text_line, max_width, font_id):
            if len(visible) == max_lines:
                overflow = True
                break
            visible.append(line)
        if overflow:
            break

    if overflow and visible:
        last = visible[-1].rstrip()
        while last and blf.dimensions(font_id, last + '…')[0] > max_width:
            last = last[:-1]
        visible[-1] = last + '…' if blf.dimensions(font_id, last + '…')[0] <= max_width else ''
    return visible, overflow


def _checklist_lines(item, max_width, max_height, font_size, padding):
    """Return visible task rows and their source indices, including wrapped rows."""
    line_height = font_size * 1.3
    max_lines = max(0, int((max_height - 2 * padding - font_size) / line_height) + 1)
    box_width = font_size * 1.5
    rows = []
    overflow = False
    for index, task in enumerate(item.text_lines):
        for part_index, part in enumerate(_wrapped_lines(task.value, max(1, max_width - box_width))):
            if len(rows) >= max_lines:
                overflow = True
                break
            rows.append((part, index, part_index == 0))
        if overflow:
            break
    if overflow and rows:
        value, index, first = rows[-1]
        limit = max(1, max_width - box_width)
        while value and blf.dimensions(0, value + '…')[0] > limit:
            value = value[:-1]
        rows[-1] = (value + '…', index, first)
    return rows, overflow


def _show_checklist_progress(item):
    return getattr(item, 'text_checklist', False) and getattr(item, 'text_show_progress', True)


def _card_header(item):
    return item.name if getattr(item, 'text_show_header', True) and item.name.strip() else ''


def _top_band_height(item, font_size):
    return font_size * 1.6 if _card_header(item) or _show_checklist_progress(item) else 0


def _checklist_percentage(item):
    tasks = [line for line in item.text_lines if line.value.strip()]
    return round(100 * sum(line.done for line in tasks) / len(tasks)) if tasks else 0


def hit_test_checklist(item, region, position):
    """Find a checkbox under a region-space click, if any."""
    if not item.text_checklist:
        return None
    layout = _scroll_layout(item, region)
    if layout is None:
        return None
    x0, _, _, _ = layout['bounds']
    font_size, padding = layout['font_size'], layout['padding']
    x, y = position
    if not layout['bottom'] <= y <= layout['top']:
        return None
    cursor = layout['top'] + layout['scroll_screen']
    for _, height, meta in layout['rows']:
        index, first = meta
        baseline = cursor - font_size
        if (first and x0 + padding <= x <= x0 + padding + font_size * 0.82
                and baseline - 2 <= y <= baseline + font_size + 2):
            return index
        cursor -= height
    return None


def hit_test_checklist_eye(item, region, position):
    """Find the per-task paint-link eye next to a checklist checkbox."""
    if not item.text_checklist:
        return None
    from .gpu_markup import linked_card_ids
    settings = getattr(getattr(item, 'id_data', None), 'kanvas_settings', None)
    if settings is None or item.item_id not in linked_card_ids(settings):
        return None   # nothing to show or hide until an image is linked
    layout = _scroll_layout(item, region)
    if layout is None:
        return None
    x0, _, _, _ = layout['bounds']
    font_size, padding = layout['font_size'], layout['padding']
    x, y = position
    if not layout['bottom'] <= y <= layout['top']:
        return None
    cursor = layout['top'] + layout['scroll_screen']
    left = x0 + padding + font_size * 0.86
    right = x0 + padding + font_size * 1.48
    for _, height, meta in layout['rows']:
        index, first = meta
        baseline = cursor - font_size
        if (first and left <= x <= right
                and baseline - 2 <= y <= baseline + font_size + 2):
            return index
        cursor -= height
    return None


def _draw_checkbox(x, baseline, size, done, color):
    """Draw the same square for both states; only the inner tick changes."""
    y = baseline + size * 0.1
    segments = [
        (x, y), (x + size, y),
        (x + size, y), (x + size, y + size),
        (x + size, y + size), (x, y + size),
        (x, y + size), (x, y),
    ]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', (*color, 1.0))
    batch_for_shader(shader, 'LINES', {'pos': segments}).draw(shader)
    if done:
        # A filled stroke keeps the tick legible without changing the box.
        tick = [
            (x + size * 0.12, y + size * 0.50),
            (x + size * 0.22, y + size * 0.61),
            (x + size * 0.40, y + size * 0.40),
            (x + size * 0.78, y + size * 0.82),
            (x + size * 0.89, y + size * 0.72),
            (x + size * 0.40, y + size * 0.19),
        ]
        batch_for_shader(shader, 'TRIS', {'pos': tick}, indices=[
            (0, 1, 2), (0, 2, 5), (5, 2, 3), (5, 3, 4),
        ]).draw(shader)


def _draw_checklist_eye(x, baseline, size, enabled, color):
    """Compact eye that fits between the checkbox and task text."""
    cx, cy = x + size * 0.5, baseline + size * 0.56
    points = [(x, cy), (x + size * 0.25, cy + size * 0.25),
              (cx, cy + size * 0.32), (x + size * 0.75, cy + size * 0.25),
              (x + size, cy), (x + size * 0.75, cy - size * 0.25),
              (cx, cy - size * 0.32), (x + size * 0.25, cy - size * 0.25)]
    segments = [point for a, b in zip(points, points[1:] + points[:1])
                for point in (a, b)]
    if not enabled:
        segments.extend(((x + size * 0.17, cy - size * 0.36),
                         (x + size * 0.83, cy + size * 0.36)))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', (*color, 1.0))
    batch_for_shader(shader, 'LINES', {'pos': segments}).draw(shader)
    if enabled:
        pupil = [(cx, cy + size * 0.13),
                 (cx + size * 0.13, cy),
                 (cx, cy - size * 0.13),
                 (cx - size * 0.13, cy)]
        batch_for_shader(shader, 'TRIS', {'pos': pupil},
                         indices=((0, 1, 2), (0, 2, 3))).draw(shader)


def _subtract_rect(rect, cover):
    """Parts of a text clip rectangle not covered by a card above it."""
    left, bottom, right, top = rect
    cover_left, cover_bottom, cover_right, cover_top = cover
    x0 = max(left, cover_left)
    y0 = max(bottom, cover_bottom)
    x1 = min(right, cover_right)
    y1 = min(top, cover_top)
    if x0 >= x1 or y0 >= y1:
        return [rect]
    pieces = []
    if left < x0:
        pieces.append((left, bottom, x0, top))
    if x1 < right:
        pieces.append((x1, bottom, right, top))
    if bottom < y0:
        pieces.append((x0, bottom, x1, y0))
    if y1 < top:
        pieces.append((x0, y1, x1, top))
    return pieces


def _region_bounds(item, view):
    left, bottom, right, top = item_bounds(item)
    x0, y0 = view.view_to_region(left, bottom, clip=False)
    x1, y1 = view.view_to_region(right, top, clip=False)
    return x0, y0, x1, y1


@lru_cache(maxsize=512)
def _cached_markdown_rows(lines, width, font_size):
    """Keep Markdown line breaks in card coordinates, independent of viewport zoom."""
    def measure(char, size):
        blf.size(0, size)
        return blf.dimensions(0, char)[0]

    rows = tuple(markdown_layout(lines, width, font_size, measure))
    offsets = [0.0]
    for _, height, _ in rows:
        offsets.append(offsets[-1] + height)
    return rows, tuple(offsets)


@lru_cache(maxsize=4096)
def _cached_checklist_rows(source, width, font_size):
    def measure(char, size):
        blf.size(0, size)
        return blf.dimensions(0, char)[0]

    return tuple(tuple(row) for row in markdown_inline_layout(
        source, width, font_size, measure))


def _scaled_markdown_meta(meta, scale):
    result = dict(meta)
    for key in ('quote_step', 'indent', 'table_padding'):
        if key in result:
            result[key] *= scale
    for key in ('table_starts', 'table_widths'):
        if key in result:
            result[key] = tuple(value * scale for value in result[key])
    return result


def _scroll_layout(item, region):
    """Measure body rows in stable card coordinates and apply saved scrolling."""
    x0, y0, x1, y1 = _region_bounds(item, region.view2d)
    scale = (x1 - x0) / item.text_width
    font_size = item.text_font_size * scale
    if scale <= 0 or font_size < 4 or font_size > 1024:
        return None
    padding = 12 * scale
    header_height = _top_band_height(item, font_size)
    top = y1 - padding - header_height
    bottom = y0 + padding
    width = x1 - x0 - 2 * padding
    if width <= 0 or top <= bottom:
        return None

    rows = []
    row_offsets = None
    if item.text_markdown and not item.text_checklist:
        rows, row_offsets = _cached_markdown_rows(
            tuple(line.value for line in item.text_lines),
            round(item.text_width - 24, 3), item.text_font_size)
    else:
        blf.size(0, item.text_font_size)
        line_height = item.text_font_size * 1.3 * scale
        if item.text_checklist:
            box_width = item.text_font_size * 1.5
            for index, task in enumerate(item.text_lines):
                for part_index, part in enumerate(_cached_checklist_rows(
                        task.value, max(1, item.text_width - 24 - box_width),
                        item.text_font_size)):
                    rows.append((part, line_height, (index, part_index == 0)))
        else:
            for line in item.text_lines:
                for part in _wrapped_lines(line.value, max(1, item.text_width - 24)):
                    rows.append((part, line_height, None))

    content_height = (row_offsets[-1] * scale if row_offsets
                      else sum(row[1] for row in rows))
    viewport_height = top - bottom
    max_scroll_screen = max(0.0, content_height - viewport_height)
    max_scroll = max_scroll_screen / scale
    scroll = max(0.0, min(item.text_scroll, max_scroll))
    return {
        'bounds': (x0, y0, x1, y1), 'padding': padding,
        'font_size': font_size, 'scale': scale,
        'top': top, 'bottom': bottom, 'rows': rows,
        'row_offsets': row_offsets,
        'scroll_screen': scroll * scale, 'max_scroll': max_scroll,
    }


def _scrollbar_geometry(layout, item):
    """Return the visible track and thumb in region coordinates."""
    if layout is None or layout['max_scroll'] <= 0:
        return None
    x0, _, x1, _ = layout['bounds']
    scale = layout['scale']
    thickness = (10 if item.is_selected else 5) * scale
    top = layout['top']
    bottom = layout['bottom'] + 4 * scale
    height = top - bottom
    if height <= 0 or x1 - x0 < 2 * thickness:
        return None
    track = (x1 - 2 * scale - thickness, bottom, x1 - 2 * scale, top)
    content_height = height + layout['max_scroll'] * scale
    thumb_height = min(height, max(18 * scale, height * height / content_height))
    travel = max(0.0, height - thumb_height)
    fraction = layout['scroll_screen'] / (layout['max_scroll'] * scale)
    thumb_top = top - fraction * travel
    thumb = (track[0], thumb_top - thumb_height, track[2], thumb_top)
    return track, thumb


def hit_test_text_scrollbar(item, region, position):
    """Return scrollbar geometry when the pointer is on its track."""
    geometry = _scrollbar_geometry(_scroll_layout(item, region), item)
    if geometry is None:
        return None
    track, thumb = geometry
    x, y = position
    if track[0] <= x <= track[2] and track[1] <= y <= track[3]:
        return track, thumb
    return None


def scroll_text_card(item, region, delta):
    """Change a card's source-space scroll position and report whether it moved."""
    layout = _scroll_layout(item, region)
    if layout is None:
        return False
    value = max(0.0, min(layout['max_scroll'], item.text_scroll + delta))
    if abs(value - item.text_scroll) < 1e-4:
        return False
    item.text_scroll = value
    return True


CARD_WHEEL_LINES = 3


def wheel_scroll_card(item, region, direction):
    """Scroll a card by one wheel notch (`direction` 1 = wheel up, -1 = down).

    Returns True when the card has content to scroll and used the wheel, even if
    it is already at that end, so the view does not start zooming in the middle
    of a long note. Returns False for a card that fits entirely.
    """
    layout = _scroll_layout(item, region)
    if layout is None or layout['max_scroll'] <= 0:
        return False
    scroll_text_card(item, region, -direction * item.text_font_size * 1.3 * CARD_WHEEL_LINES)
    return True


def _draw_scrollbar(layout, rects, item):
    geometry = _scrollbar_geometry(layout, item)
    if geometry is None:
        return
    track, thumb = geometry
    for bounds, color in ((track, (0.55, 0.57, 0.60, 0.28)),
                          (thumb, (0.95, 0.74, 0.25, 0.9))):
        for rect in rects:
            left = max(bounds[0], rect[0])
            bottom = max(bounds[1], rect[1])
            right = min(bounds[2], rect[2])
            top = min(bounds[3], rect[3])
            if left < right and bottom < top:
                _draw_colored_rule(_underline_triangles(
                    [(left, bottom, right, top)], left, right,
                    (bottom + top) * 0.5, top - bottom), color)


def _enable_body_scissor(rect):
    """Keep body glyphs inside the card and below the title band."""
    left, bottom, right, top = rect
    viewport_x, viewport_y, _, _ = gpu.state.viewport_get()
    x = math.floor(left + viewport_x)
    y = math.floor(bottom + viewport_y)
    gpu.state.scissor_set(x, y, max(0, math.ceil(right + viewport_x) - x),
                          max(0, math.ceil(top + viewport_y) - y))
    gpu.state.scissor_test_set(True)


def _disable_body_scissor():
    gpu.state.scissor_test_set(False)


def _draw_scroll_continuation(layout, rects, item):
    """Show hidden text with a soft three-pixel accent at each relevant edge."""
    if layout['max_scroll'] <= 0:
        return
    scale = layout['scale']
    x0, _, x1, _ = layout['bounds']
    left = x0 + layout['padding']
    right = x1 - layout['padding'] - 5 * scale
    if right <= left:
        return
    scroll = layout['scroll_screen']
    max_scroll_screen = layout['max_scroll'] * scale
    accent = (0.95, 0.74, 0.25)
    for hidden, edge_y in ((scroll > 0.5 * scale, layout['top'] - 2 * scale),
                           (scroll < max_scroll_screen - 0.5 * scale,
                            layout['bottom'] + 2 * scale)):
        if hidden:
            for offset, alpha in ((-1.0, 0.2), (0.0, 0.8), (1.0, 0.2)):
                vertices = _underline_triangles(rects, left, right,
                                                edge_y + offset, 1.0)
                _draw_colored_rule(vertices, (*accent, alpha))


def _underline_triangles(rects, x0, x1, y, thickness):
    """Clip the overflow cue to the card and any cards drawn above it."""
    vertices = []
    for left, bottom, right, top in rects:
        line_left = max(x0, left)
        line_right = min(x1, right)
        line_bottom = max(y - thickness * 0.5, bottom)
        line_top = min(y + thickness * 0.5, top)
        if line_left < line_right and line_bottom < line_top:
            vertices.extend([
                (line_left, line_bottom), (line_right, line_bottom),
                (line_right, line_top), (line_left, line_bottom),
                (line_right, line_top), (line_left, line_top),
            ])
    return vertices


def _draw_colored_rule(vertices, color):
    if not vertices:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        shader.uniform_float('color', color)
        batch_for_shader(shader, 'TRIS', {'pos': vertices}).draw(shader)
    finally:
        gpu.state.blend_set(old_blend)


def _draw_overflow_underline(vertices):
    _draw_colored_rule(vertices, (0.95, 0.24, 0.22, 0.78))


def _markdown_rows(item, region, layout=None):
    if layout is None:
        layout = _scroll_layout(item, region)
    if layout is None:
        return [], False, 0, 0
    offsets = layout['row_offsets']
    start = (max(0, min(len(layout['rows']) - 1,
                         bisect_right(offsets,
                                      layout['scroll_screen'] / layout['scale']) - 1))
             if offsets and layout['rows'] else 0)
    top = (layout['top'] + layout['scroll_screen']
           - (offsets[start] * layout['scale'] if offsets else 0))
    rows = []
    for index in range(start, len(layout['rows'])):
        runs, source_height, source_meta = layout['rows'][index]
        row_height = source_height * layout['scale']
        size = source_height / 1.3 * layout['scale']
        baseline = top - size
        if baseline + size < layout['bottom']:
            break
        if baseline <= layout['top']:
            rows.append((runs, size, baseline,
                         _scaled_markdown_meta(source_meta, layout['scale'])))
        top -= row_height
    return rows, layout['max_scroll'] > 0, layout['padding'], layout['font_size']


def _table_cell_cursor(meta, column, runs, origin, size):
    """Place a wrapped cell using its declared column alignment."""
    blf.size(0, size)
    cell_left = origin + meta['table_starts'][column] + meta['table_padding']
    available = meta['table_widths'][column] - 2 * meta['table_padding']
    text_width = sum(blf.dimensions(0, value)[0] for value, _, _ in runs)
    align = meta['table_align'][column]
    offset = (max(0.0, available - text_width) / 2 if align == 'center'
              else max(0.0, available - text_width) if align == 'right' else 0.0)
    return cell_left + offset


def _vertical_rule(rect, x, bottom, top, thickness):
    left = max(rect[0], x - thickness * 0.5)
    right = min(rect[2], x + thickness * 0.5)
    bottom = max(rect[1], bottom)
    top = min(rect[3], top)
    if left >= right or bottom >= top:
        return []
    return [(left, bottom), (right, bottom), (right, top),
            (left, bottom), (right, top), (left, top)]


def _draw_table_grid(meta, body_clip, origin, baseline, size, color):
    left = origin + meta['table_starts'][0]
    right = origin + meta['table_starts'][-1] + meta['table_widths'][-1]
    top = baseline + size
    bottom = baseline - size * 0.3
    vertices = []
    for x in (origin + start for start in meta['table_starts']):
        vertices.extend(_vertical_rule(body_clip, x, bottom, top, 1.0))
    vertices.extend(_vertical_rule(body_clip, right, bottom, top, 1.0))
    if meta['table_first']:
        vertices.extend(_underline_triangles([body_clip], left, right, top, 1.0))
    if meta['table_last']:
        vertices.extend(_underline_triangles([body_clip], left, right, bottom, 1.0))
    _draw_colored_rule(vertices, (*color, 0.48 if meta['table_header'] else 0.3))


def _draw_markdown_runs(runs, cursor, baseline, size, body_clip, item):
    blf.size(0, size)
    for value, style, _ in runs:
        if not value:
            continue
        flags = set(style.split())
        color = ((0.38, 0.7, 1.0) if 'link' in flags
                 else (0.9, 0.74, 0.49) if 'code' in flags
                 else item.text_color)
        blf.color(0, *color, 1.0)
        run_start = cursor
        draw_canvas_text(0, value, cursor, baseline, (*color, 1.0), size)
        if 'bold' in flags:
            draw_canvas_text(0, value, cursor + max(0.7, size * 0.045),
                             baseline, (*color, 1.0), size)
        cursor += blf.dimensions(0, value)[0]
        if 'strike' in flags or 'italic' in flags:
            line_y = (baseline + size * 0.45 if 'strike' in flags
                      else baseline - size * 0.08)
            line = _underline_triangles([body_clip], run_start, cursor, line_y,
                                        max(1.0, size * 0.06))
            _draw_colored_rule(line, (*color, 0.85 if 'strike' in flags else 0.55))


def hit_test_markdown_link(item, region, position):
    if not (item.text_markdown or item.text_checklist):
        return None
    layout = _scroll_layout(item, region)
    if layout is None:
        return None
    x0, _, _, _ = layout['bounds']
    padding = layout['padding']
    x, y = position
    if not layout['bottom'] <= y <= layout['top']:
        return None
    if item.text_checklist:
        cursor_y = layout['top']
        for runs, height, _ in layout['rows']:
            baseline = cursor_y - layout['font_size']
            if baseline <= y <= baseline + layout['font_size']:
                cursor_x = x0 + padding + layout['font_size'] * 1.5
                blf.size(0, layout['font_size'])
                for value, _, url in runs:
                    advance = blf.dimensions(0, value)[0]
                    if url and cursor_x <= x <= cursor_x + advance:
                        return url
                    cursor_x += advance
                return None
            cursor_y -= height
        return None
    rows, _, _, _ = _markdown_rows(item, region, layout)
    for runs, size, baseline, meta in rows:
        if not baseline <= y <= baseline + size:
            continue
        groups = ([(cell, _table_cell_cursor(meta, column, cell,
                                            x0 + padding, size),
                    x0 + padding + meta['table_starts'][column]
                    + meta['table_padding'],
                    x0 + padding + meta['table_starts'][column]
                    + meta['table_widths'][column] - meta['table_padding'])
                   for column, cell in enumerate(meta['table_cells'])]
                  if meta.get('kind') == 'table'
                  else [(runs, x0 + padding, -float('inf'), float('inf'))])
        blf.size(0, size)
        for cell_runs, cursor, cell_left, cell_right in groups:
            for value, _, url in cell_runs:
                advance = blf.dimensions(0, value)[0]
                if url and max(cursor, cell_left) <= x <= min(cursor + advance, cell_right):
                    return url
                cursor += advance
    return None


def _draw_markdown(item, region, rects, x0, y0, x1, y1, layout=None):
    if layout is None:
        layout = _scroll_layout(item, region)
    if layout is None:
        return
    rows, _, padding, base_size = _markdown_rows(item, region, layout)
    header = _card_header(item)
    from .gpu_common import get_prefs
    prefs = get_prefs()
    button_bounds = (text_edit_button_bounds(item, region)
                     if prefs is None or getattr(prefs, 'show_text_edit_button', True)
                     else None)
    header_right = button_bounds[0] - 3 * (x1 - x0) / item.text_width if button_bounds else x1
    shadow_enabled = enable_soft_text_shadow(item.text_color)
    blf.enable(0, blf.CLIPPING)
    try:
        for rect in rects:
            blf.clipping(0, *rect)
            if header and header_right > rect[0]:
                blf.clipping(0, rect[0], rect[1], min(rect[2], header_right), rect[3])
                blf.size(0, base_size)
                blf.color(0, *item.text_color, 1.0)
                draw_canvas_text(0, header, x0 + padding,
                                 y1 - padding - base_size,
                                 (*item.text_color, 1.0), base_size)
                blf.clipping(0, *rect)
            body_clip = (rect[0], max(rect[1], layout['bottom']),
                         rect[2], min(rect[3], layout['top']))
            if body_clip[0] >= body_clip[2] or body_clip[1] >= body_clip[3]:
                continue
            blf.clipping(0, *body_clip)
            _enable_body_scissor(body_clip)
            try:
                for runs, size, baseline, meta in rows:
                    if baseline + size < body_clip[1] or baseline > body_clip[3]:
                        continue
                    kind = meta.get('kind', 'text')
                    if kind == 'rule':
                        vertices = _underline_triangles(
                            [body_clip], x0 + padding, x1 - padding,
                            baseline + size * 0.5, max(1.0, size * 0.08))
                        _draw_colored_rule(vertices, (*item.text_color, 0.55))
                        continue
                    if kind == 'table':
                        _draw_table_grid(meta, body_clip, x0 + padding,
                                         baseline, size, item.text_color)
                        for column, cell in enumerate(meta['table_cells']):
                            cell_left = (x0 + padding + meta['table_starts'][column]
                                         + meta['table_padding'])
                            cell_right = (x0 + padding + meta['table_starts'][column]
                                          + meta['table_widths'][column]
                                          - meta['table_padding'])
                            cell_clip = (max(body_clip[0], cell_left), body_clip[1],
                                         min(body_clip[2], cell_right), body_clip[3])
                            if cell_clip[0] >= cell_clip[2]:
                                continue
                            cursor = _table_cell_cursor(
                                meta, column, cell, x0 + padding, size)
                            blf.clipping(0, *cell_clip)
                            _enable_body_scissor(cell_clip)
                            try:
                                _draw_markdown_runs(cell, cursor, baseline, size,
                                                    cell_clip, item)
                            finally:
                                _enable_body_scissor(body_clip)
                                blf.clipping(0, *body_clip)
                        continue
                    for level in range(meta.get('quote', 0)):
                        bar_x = (x0 + padding + level * meta['quote_step']
                                 + size * 0.25)
                        bar = (max(body_clip[0], bar_x),
                               max(body_clip[1], baseline - size * 0.15),
                               min(body_clip[2], bar_x + max(1.0, size * 0.09)),
                               min(body_clip[3], baseline + size))
                        if bar[0] < bar[2] and bar[1] < bar[3]:
                            _draw_colored_rule([
                                (bar[0], bar[1]), (bar[2], bar[1]),
                                (bar[2], bar[3]), (bar[0], bar[1]),
                                (bar[2], bar[3]), (bar[0], bar[3]),
                            ], (0.95, 0.74, 0.25, 0.58))
                    _draw_markdown_runs(runs, x0 + padding, baseline,
                                        size, body_clip, item)
            finally:
                _disable_body_scissor()
    finally:
        blf.disable(0, blf.CLIPPING)
        if shadow_enabled:
            disable_soft_text_shadow()


def draw_text_label(item, region, occluders=()):
    view = region.view2d
    x0, y0, x1, y1 = _region_bounds(item, view)
    width, height = x1 - x0, y1 - y0
    if width <= 0 or height <= 0 or x1 <= 0 or y1 <= 0 or x0 >= region.width or y0 >= region.height:
        return
    pixel_scale = width / item.text_width
    font_size = item.text_font_size * pixel_scale
    # A subpixel glyph cannot be read; keeping it at a fixed screen size made
    # distant cards appear to contain more text than they actually can hold.
    if font_size < 4 or font_size > 1024:
        return
    padding = 12 * pixel_scale
    line_height = font_size * 1.3
    header_height = _top_band_height(item, font_size)
    max_width = width - 2 * padding
    if max_width <= 0:
        return

    if height - header_height <= 2 * padding + font_size:
        # Even one full-size line cannot fit. Show a smaller overflow marker.
        if not any(line.value for line in item.text_lines) and not header_height:
            return
        if header_height:
            lines = []
            overflow = False
        else:
            font_size = min(font_size, int(height - 2 * padding))
            if font_size < 4:
                return
            lines = ['…']
            overflow = True
        rows = []
        scroll_layout = None
        line_height = font_size * 1.3
    else:
        scroll_layout = _scroll_layout(item, region)
        if scroll_layout is None:
            return
        rows = []
        if item.text_markdown and not item.text_checklist:
            lines = [True] if scroll_layout['rows'] else []
        else:
            cursor = scroll_layout['top'] + scroll_layout['scroll_screen']
            for value, row_height, meta in scroll_layout['rows']:
                baseline = cursor - font_size
                if baseline + font_size >= scroll_layout['bottom'] and baseline <= scroll_layout['top']:
                    rows.append((value, meta, baseline))
                cursor -= row_height
            lines = [row[0] for row in rows]
        overflow = False
        if not lines and not header_height:
            return
    if scroll_layout is None:
        rows = [(line, None, y1 - padding - header_height - font_size - index * line_height)
                for index, line in enumerate(lines)]

    blf.size(0, font_size)
    blf.color(0, *item.text_color, 1.0)
    clip_left = max(0, x0 + 2)
    clip_bottom = max(0, y0 + 2)
    clip_right = min(region.width, x1 - 2)
    clip_top = min(region.height, y1 - 2)
    if clip_left >= clip_right or clip_bottom >= clip_top:
        return
    visible_rects = [(clip_left, clip_bottom, clip_right, clip_top)]
    for cover in occluders:
        visible_rects = [piece for rect in visible_rects
                         for piece in _subtract_rect(rect, cover)]
        if not visible_rects:
            return
    if header_height:
        rule = _underline_triangles(
            visible_rects, x0 + padding, x1 - padding,
            y1 - padding - font_size * 1.34,
            max(1.0, pixel_scale))
        _draw_colored_rule(rule, (*item.text_color, 0.55))
    if item.text_markdown and not item.text_checklist:
        _draw_markdown(item, region, visible_rects, x0, y0, x1, y1, scroll_layout)
        if scroll_layout is not None:
            _draw_scroll_continuation(scroll_layout, visible_rects, item)
            _draw_scrollbar(scroll_layout, visible_rects, item)
        return
    shadow_enabled = enable_soft_text_shadow(item.text_color)
    blf.enable(0, blf.CLIPPING)
    try:
        from .gpu_common import get_prefs
        prefs = get_prefs()
        edit_button_visible = prefs is None or getattr(prefs, 'show_text_edit_button', True)
        button_bounds = text_edit_button_bounds(item, region) if edit_button_visible else None
        header_right_limit = button_bounds[0] - 3 * pixel_scale if button_bounds else x1
        show_eyes = False
        if item.text_checklist:
            from .gpu_markup import linked_card_ids
            settings = getattr(getattr(item, 'id_data', None), 'kanvas_settings', None)
            show_eyes = settings is not None and item.item_id in linked_card_ids(settings)
        progress_text = f'{_checklist_percentage(item)}%' if _show_checklist_progress(item) else ''
        progress_size = max(4.0, font_size * 0.85)
        if progress_text:
            blf.size(0, progress_size)
            progress_left = header_right_limit - padding - blf.dimensions(0, progress_text)[0]
        for rect in visible_rects:
            blf.clipping(0, *rect)
            header = _card_header(item)
            if header:
                header_right = min(rect[2], progress_left - 4 * pixel_scale) if progress_text else min(rect[2], header_right_limit)
                if header_right > rect[0]:
                    blf.clipping(0, rect[0], rect[1], header_right, rect[3])
                    blf.size(0, font_size)
                    draw_canvas_text(0, header, x0 + padding,
                                     y1 - padding - font_size,
                                     (*item.text_color, 1.0), font_size)
                    blf.clipping(0, *rect)
            if progress_text:
                blf.size(0, progress_size)
                blf.color(0, *item.text_color, 0.85)
                draw_canvas_text(0, progress_text, progress_left,
                                 y1 - padding - font_size,
                                 (*item.text_color, 0.85), progress_size)
                blf.color(0, *item.text_color, 1.0)
                blf.size(0, font_size)
            body_clip = (rect[0], max(rect[1], scroll_layout['bottom']),
                         rect[2], min(rect[3], scroll_layout['top'])) if scroll_layout else rect
            if body_clip[0] >= body_clip[2] or body_clip[1] >= body_clip[3]:
                continue
            blf.clipping(0, *body_clip)
            _enable_body_scissor(body_clip)
            try:
                for line, meta, y in rows:
                    if y + font_size < body_clip[1] or y > body_clip[3]:
                        continue
                    if item.text_checklist and meta is not None:
                        task_index, first = meta
                        if first:
                            size = font_size * 0.78
                            bx = x0 + padding
                            if (bx >= body_clip[0] and bx + size <= body_clip[2]
                                    and y + size * 0.1 >= body_clip[1]
                                    and y + size * 1.1 <= body_clip[3]):
                                _draw_checkbox(bx, y, size,
                                               item.text_lines[task_index].done,
                                               item.text_color)
                                eye = item.text_lines[task_index]
                                eye_x = bx + font_size * 0.86
                                eye_size = font_size * 0.62
                                if show_eyes and eye_x + eye_size <= body_clip[2]:
                                    eye_color = (tuple(eye.color) if eye.show_color_links else
                                                 tuple(channel * 0.55 for channel in item.text_color))
                                    _draw_checklist_eye(eye_x, y, eye_size,
                                                        eye.show_color_links, eye_color)
                        _draw_markdown_runs(line, x0 + padding + font_size * 1.5,
                                            y, font_size, body_clip, item)
                    else:
                        draw_canvas_text(0, line, x0 + padding, y,
                                         (*item.text_color, 1.0), font_size)
            finally:
                _disable_body_scissor()
    finally:
        blf.disable(0, blf.CLIPPING)
        if shadow_enabled:
            disable_soft_text_shadow()

    if scroll_layout is not None:
        _draw_scroll_continuation(scroll_layout, visible_rects, item)
        _draw_scrollbar(scroll_layout, visible_rects, item)

    if overflow and lines:
        start_x = x0 + padding
        end_x = x1 - padding
        last_y = y1 - padding - header_height - font_size - (len(lines) - 1) * line_height
        underline = _underline_triangles(
            visible_rects, start_x, end_x,
            last_y - font_size * 0.18,
            max(1.0, 3.5 * pixel_scale))
        _draw_overflow_underline(underline)
