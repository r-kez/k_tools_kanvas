"""Comparison card: two board images (A and B) shown side by side with a divider.

The card is a text card flagged with `text_compare`, so it moves, resizes, locks,
snaps and joins frames like any other card. Geometry helpers are pure so they can
be tested without a GPU.
"""

import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .gpu_theme import (draw_canvas_text, draw_rounded_border, draw_rounded_fill,
                        selection_color, studio_enabled)

MIN_BUTTON_PIXELS = 7


def compare_layout(item, bounds):
    """Button and content rectangles for a card whose region bounds are given.

    Returns None when the card is too small to show anything useful.
    """
    x0, y0, x1, y1 = bounds
    width = x1 - x0
    if width <= 0 or item.text_width <= 0:
        return None
    scale = width / item.text_width
    size = item.text_font_size * scale
    if size < MIN_BUTTON_PIXELS:
        return None
    margin = 12 * scale
    gap = 6 * scale
    button_b = (x1 - margin - size, y1 - margin - size, x1 - margin, y1 - margin)
    button_a = (button_b[0] - gap - size, button_b[1], button_b[0] - gap, button_b[3])
    pad = 10 * scale
    content = (x0 + pad, y0 + pad, x1 - pad, y1 - 2 * margin - size)
    if content[2] - content[0] < size or content[3] - content[1] < size:
        return None
    return {'A': button_a, 'B': button_b, 'content': content, 'scale': scale, 'size': size}


def hit_compare_button(item, bounds, position):
    layout = compare_layout(item, bounds)
    if layout is None:
        return None
    for side in ('A', 'B'):
        left, bottom, right, top = layout[side]
        if left <= position[0] <= right and bottom <= position[1] <= top:
            return side
    return None


def fit_rect(content, image_width, image_height):
    """Largest rectangle with the image's proportions that fits inside `content`, centered."""
    left, bottom, right, top = content
    width, height = right - left, top - bottom
    if image_width <= 0 or image_height <= 0 or width <= 0 or height <= 0:
        return None
    ratio = image_width / image_height
    if width / height > ratio:
        fitted_w, fitted_h = height * ratio, height
    else:
        fitted_w, fitted_h = width, width / ratio
    cx, cy = (left + right) * 0.5, (bottom + top) * 0.5
    return (cx - fitted_w * 0.5, cy - fitted_h * 0.5, cx + fitted_w * 0.5, cy + fitted_h * 0.5)


def crop_to_range(rect, low, high):
    """Visible part of `rect` between two x positions, with the matching UV window.

    Returns (screen_rect, uv_rect) or None when nothing is visible.
    """
    left, bottom, right, top = rect
    visible_left, visible_right = max(left, low), min(right, high)
    if visible_right - visible_left <= 0.25:
        return None
    span = right - left
    u0 = (visible_left - left) / span
    u1 = (visible_right - left) / span
    return (visible_left, bottom, visible_right, top), (u0, 0.0, u1, 1.0)


def divider_x(content, split):
    return content[0] + (content[2] - content[0]) * min(1.0, max(0.0, split))


def side_item(settings, item, side):
    """The board image assigned to A or B, or None if unset or gone."""
    target = item.compare_a_id if side == 'A' else item.compare_b_id
    if not target:
        return None
    return next((other for other in settings.images
                 if other.item_id == target and other.item_type == 'IMAGE'
                 and other.image_data), None)


def _triangles(shader, vertices, color):
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, 'TRIS', {'pos': vertices}).draw(shader)


def _quad(left, bottom, right, top):
    return [(left, bottom), (right, bottom), (right, top),
            (left, bottom), (right, top), (left, top)]


def _centered_text(text, rect, size, color):
    blf.size(0, size)
    width, height = blf.dimensions(0, text)
    draw_canvas_text(0, text, (rect[0] + rect[2]) * 0.5 - width * 0.5,
                     (rect[1] + rect[3]) * 0.5 - height * 0.5, color, size)


def draw_compare_buttons(item, layout, settings):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        accent = selection_color()
        for side in ('A', 'B'):
            rect = layout[side]
            assigned = side_item(settings, item, side) is not None
            fill = (*accent[:3], 0.9) if assigned else (0.035, 0.055, 0.075, 0.92)
            if studio_enabled():
                radius = max(1.0, (rect[2] - rect[0]) * 0.2)
                draw_rounded_fill(shader, rect, radius, fill)
                draw_rounded_border(shader, rect, radius, max(0.8, layout['scale']),
                                    (*accent[:3], 0.8 if not assigned else 0.0))
            else:
                _triangles(shader, _quad(*rect), fill)
            _centered_text(side, rect, max(6, round(layout['size'] * 0.72)),
                           (0.05, 0.07, 0.1, 1.0) if assigned else (1.0, 1.0, 1.0, 0.95))
    finally:
        gpu.state.blend_set(previous)


def draw_compare_card(item, region, settings, bounds):
    """Draw buttons, title and the two images with their divider."""
    from .gpu_image import get_kanvas_texture

    x0, y0, x1, y1 = bounds
    layout = compare_layout(item, bounds)
    if layout is None:
        return
    draw_compare_buttons(item, layout, settings)
    content = layout['content']
    scale = layout['scale']

    if item.text_show_header and item.name:
        size = max(5, round(layout['size']))
        blf.size(0, size)
        blf.enable(0, blf.CLIPPING)
        blf.clipping(0, x0 + 2, y0, layout['A'][0] - 4 * scale, y1)
        try:
            draw_canvas_text(0, item.name, x0 + 12 * scale, y1 - 12 * scale - layout['size'],
                             (*item.text_color, 1.0), size)
        finally:
            blf.disable(0, blf.CLIPPING)

    split = divider_x(content, item.compare_split)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        halves = {'A': (content[0], split), 'B': (split, content[2])}
        for side, (low, high) in halves.items():
            source = side_item(settings, item, side)
            if source is None:
                half = (low, content[1], high, content[3])
                if high - low > 1:
                    _triangles(shader, _quad(*half), (0.0, 0.0, 0.0, 0.28))
                    _centered_text(f'Pick {side}', half, max(6, round(layout['size'] * 0.8)),
                                   (1.0, 1.0, 1.0, 0.45))
                continue
            width, height = source.image_data.size
            fitted = fit_rect(content, width * abs(source.scale_xy[0]),
                              height * abs(source.scale_xy[1]))
            cropped = crop_to_range(fitted, low, high) if fitted else None
            if cropped is None:
                continue
            screen_rect, uv_rect = cropped
            texture = get_kanvas_texture(source.image_data)
            texture.draw_rect(screen_rect, uv_rect, 1.0, source.color_tint,
                              source.brightness, source.contrast, source.saturation,
                              source.use_color_correction, source.flip_h, source.flip_v)
        line = max(1.5, 2.0 * scale)
        _triangles(shader, _quad(split - line * 0.5, content[1], split + line * 0.5, content[3]),
                   (1.0, 1.0, 1.0, 0.92))
        grip = min(content[3] - content[1], max(14 * scale, 10)) * 0.5
        cy = (content[1] + content[3]) * 0.5
        grip_rect = (split - grip * 0.55, cy - grip, split + grip * 0.55, cy + grip)
        if studio_enabled():
            draw_rounded_fill(shader, grip_rect, grip * 0.4, (1.0, 1.0, 1.0, 0.95))
        else:
            _triangles(shader, _quad(*grip_rect), (1.0, 1.0, 1.0, 0.95))
    finally:
        gpu.state.blend_set(previous)
