"""Comparison card: two board images (A and B) compared in one card.

The card is a text card flagged with `text_compare`, so it moves, resizes, locks,
snaps and joins frames like any other card. Modes: SPLIT (divider), FADE (B over A
with adjustable opacity) and DIFF (absolute difference).

Images are drawn in the canvas pass, exactly like board images, so they look the
same in the card as on the board. Buttons and labels are drawn in the pixel pass.
Geometry helpers are pure so they can be tested without a GPU.
"""

import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .gpu_theme import (draw_canvas_text, draw_rounded_border, draw_rounded_fill,
                        selection_color, studio_enabled)

MODES = ('SPLIT', 'FADE', 'DIFF')
MODE_LABELS = {'SPLIT': 'Split', 'FADE': 'Fade', 'DIFF': 'Diff'}
DIVIDER_GRAB_PIXELS = 9
MIN_BUTTON_PIXELS = 12


def next_mode(mode, step=1):
    return MODES[(MODES.index(mode) + step) % len(MODES)] if mode in MODES else MODES[0]


def compare_layout(item, bounds):
    """Button and content rectangles for a card whose bounds are given.

    Works in any units (canvas or region pixels): sizes scale with the card.
    Returns None when the card is too small to show anything useful.
    """
    x0, y0, x1, y1 = bounds
    width = x1 - x0
    if width <= 0 or item.text_width <= 0:
        return None
    scale = width / item.text_width
    size = max(item.text_font_size * 1.9, 30.0) * scale
    margin = 10 * scale
    gap = 6 * scale
    top = y1 - margin
    button_b = (x1 - margin - size, top - size, x1 - margin, top)
    button_a = (button_b[0] - gap - size, top - size, button_b[0] - gap, top)
    mode_width = size * 1.9
    button_mode = (button_a[0] - gap - mode_width, top - size, button_a[0] - gap, top)
    pad = 10 * scale
    content = (x0 + pad, y0 + pad, x1 - pad, top - size - margin)
    if content[2] - content[0] < size or content[3] - content[1] < size * 0.8:
        return None
    if button_mode[0] < x0 + margin:
        button_mode = None            # a very narrow card keeps just A and B
    return {'MODE': button_mode, 'A': button_a, 'B': button_b, 'content': content,
            'scale': scale, 'size': size}


def _inside(rect, position):
    return rect is not None and rect[0] <= position[0] <= rect[2] and rect[1] <= position[1] <= rect[3]


def hit_compare_button(item, bounds, position):
    """'MODE', 'A', 'B' or None for a position in the same units as `bounds`."""
    layout = compare_layout(item, bounds)
    if layout is None:
        return None
    for name in ('A', 'B', 'MODE'):
        if _inside(layout[name], position):
            return name
    return None


def hit_compare_divider(item, bounds, position, grab):
    """True when the position grabs the divider line (SPLIT mode only)."""
    layout = compare_layout(item, bounds)
    if layout is None or item.compare_mode != 'SPLIT':
        return False
    content = layout['content']
    return (abs(position[0] - divider_x(content, item.compare_split)) <= grab
            and content[1] <= position[1] <= content[3])


def split_from_position(item, bounds, x):
    layout = compare_layout(item, bounds)
    if layout is None:
        return item.compare_split
    content = layout['content']
    return min(1.0, max(0.0, (x - content[0]) / max(content[2] - content[0], 1e-6)))


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


def uv_window(rect, window):
    """UV window of `rect` covered by `window`, or None when they do not overlap."""
    left, bottom, right, top = rect
    wl, wb = max(left, window[0]), max(bottom, window[1])
    wr, wt = min(right, window[2]), min(top, window[3])
    if wr - wl <= 1e-6 or wt - wb <= 1e-6:
        return None
    width, height = right - left, top - bottom
    return ((wl - left) / width, (wb - bottom) / height,
            (wr - left) / width, (wt - bottom) / height), (wl, wb, wr, wt)


def crop_to_range(rect, low, high):
    """Visible part of `rect` between two x positions, with the matching UV window."""
    shown = uv_window(rect, (low, rect[1], high, rect[3]))
    if shown is None or shown[1][2] - shown[1][0] <= 1e-3:
        return None
    return shown[1], shown[0]


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


def side_rect(settings, item, content, side):
    source = side_item(settings, item, side)
    if source is None:
        return None, None
    width, height = source.image_data.size
    return source, fit_rect(content, width * abs(source.scale_xy[0]),
                            height * abs(source.scale_xy[1]))


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

_diff_shader = None
_diff_failed = False


def get_diff_shader():
    """Shader that shows |A - B|; None when it cannot be built (callers fall back to FADE)."""
    global _diff_shader, _diff_failed
    if _diff_failed:
        return None
    if _diff_shader is not None:
        try:
            if hasattr(_diff_shader, 'program'):
                return _diff_shader
        except Exception:
            _diff_shader = None
    try:
        interface = gpu.types.GPUStageInterfaceInfo('kanvas_diff_iface')
        interface.smooth('VEC2', 'uv_a')
        interface.smooth('VEC2', 'uv_b')
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', 'ModelViewProjectionMatrix')
        info.push_constant('VEC4', 'params_a')
        info.push_constant('VEC4', 'params_b')
        info.push_constant('FLOAT', 'gain')
        info.sampler(0, 'FLOAT_2D', 'image_a')
        info.sampler(1, 'FLOAT_2D', 'image_b')
        info.vertex_in(0, 'VEC2', 'pos')
        info.vertex_in(1, 'VEC2', 'texCoordA')
        info.vertex_in(2, 'VEC2', 'texCoordB')
        info.vertex_out(interface)
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source(
            'void main() {'
            '  uv_a = texCoordA; uv_b = texCoordB;'
            '  gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0);'
            '}')
        info.fragment_source(
            'vec3 adjust(vec3 c, vec4 p) {'
            '  c = max(c * p.x, vec3(0.0));'
            '  c = clamp((c - 0.5) * p.y + 0.5, 0.0, 1.0);'
            '  float g = dot(c, vec3(0.2126, 0.7152, 0.0722));'
            '  c = clamp(mix(vec3(g), c, p.z), 0.0, 1.0);'
            '  if (p.w > 0.5) { c = pow(c, vec3(1.0 / 2.2)); }'
            '  return c;'
            '}'
            'void main() {'
            '  vec3 a = adjust(texture(image_a, uv_a).rgb, params_a);'
            '  vec3 b = adjust(texture(image_b, uv_b).rgb, params_b);'
            '  fragColor = vec4(clamp(abs(a - b) * gain, 0.0, 1.0), 1.0);'
            '}')
        _diff_shader = gpu.shader.create_from_info(info)
        return _diff_shader
    except Exception as exc:
        print(f'Kanvas: difference shader failed ({exc}); Diff falls back to Fade')
        _diff_failed = True
        return None


def _flip_uv(window, source):
    u0, v0, u1, v1 = window
    if source.flip_h:
        u0, u1 = 1.0 - u0, 1.0 - u1
    if source.flip_v:
        v0, v1 = 1.0 - v0, 1.0 - v1
    return u0, v0, u1, v1


def _draw_difference(item, source_a, rect_a, source_b, rect_b):
    """|A - B| over the area both images cover; returns False if it cannot be drawn."""
    from .gpu_image import get_kanvas_texture

    shader = get_diff_shader()
    overlap = (max(rect_a[0], rect_b[0]), max(rect_a[1], rect_b[1]),
               min(rect_a[2], rect_b[2]), min(rect_a[3], rect_b[3]))
    if shader is None or overlap[2] <= overlap[0] or overlap[3] <= overlap[1]:
        return shader is not None
    window_a = uv_window(rect_a, overlap)
    window_b = uv_window(rect_b, overlap)
    if window_a is None or window_b is None:
        return True
    tex_a = get_kanvas_texture(source_a.image_data)
    tex_b = get_kanvas_texture(source_b.image_data)
    if not tex_a.texture or not tex_b.texture:
        return True
    ua0, va0, ua1, va1 = _flip_uv(window_a[0], source_a)
    ub0, vb0, ub1, vb1 = _flip_uv(window_b[0], source_b)
    left, bottom, right, top = overlap
    batch = batch_for_shader(shader, 'TRI_FAN', {
        'pos': [(left, bottom), (right, bottom), (right, top), (left, top)],
        'texCoordA': [(ua0, va0), (ua1, va0), (ua1, va1), (ua0, va1)],
        'texCoordB': [(ub0, vb0), (ub1, vb0), (ub1, vb1), (ub0, vb1)],
    })
    shader.bind()
    shader.uniform_sampler('image_a', tex_a.texture)
    shader.uniform_sampler('image_b', tex_b.texture)
    shader.uniform_float('params_a', (source_a.brightness, source_a.contrast, source_a.saturation,
                                      float(source_a.use_color_correction)))
    shader.uniform_float('params_b', (source_b.brightness, source_b.contrast, source_b.saturation,
                                      float(source_b.use_color_correction)))
    shader.uniform_float('gain', float(item.compare_gain))
    batch.draw(shader)
    return True


def _triangles(shader, vertices, color):
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, 'TRIS', {'pos': vertices}).draw(shader)


def _quad(left, bottom, right, top):
    return [(left, bottom), (right, bottom), (right, top),
            (left, bottom), (right, top), (left, top)]


def _draw_source(source, rect, window, opacity):
    from .gpu_image import get_kanvas_texture
    uv = uv_window(rect, window)
    if uv is None:
        return
    get_kanvas_texture(source.image_data).draw_rect(
        uv[1], uv[0], opacity, source.color_tint, source.brightness, source.contrast,
        source.saturation, source.use_color_correction, source.flip_h, source.flip_v)


def draw_compare_content(item, settings, pixel_size):
    """Card background, images and divider, in canvas space (same pass as board images)."""
    from ..item_geometry import item_bounds
    from .gpu_text import draw_text_card

    bounds = item_bounds(item)
    layout = compare_layout(item, bounds)
    draw_text_card(item, pixel_size)
    if layout is None:
        return
    content = layout['content']
    scale = layout['scale']
    source_a, rect_a = side_rect(settings, item, content, 'A')
    source_b, rect_b = side_rect(settings, item, content, 'B')
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        mode = item.compare_mode
        if mode == 'DIFF' and source_a is not None and source_b is not None and rect_a and rect_b:
            if _draw_difference(item, source_a, rect_a, source_b, rect_b):
                return
            mode = 'FADE'
        if mode == 'SPLIT':
            split = divider_x(content, item.compare_split)
            halves = (('A', source_a, rect_a, content[0], split),
                      ('B', source_b, rect_b, split, content[2]))
            for _side, source, rect, low, high in halves:
                if source is None or rect is None:
                    if high - low > 0:
                        _triangles(shader, _quad(low, content[1], high, content[3]), (0.0, 0.0, 0.0, 0.28))
                    continue
                _draw_source(source, rect, (low, content[1], high, content[3]), 1.0)
            line = max(2.0 * pixel_size, 1.5 * scale)
            _triangles(shader, _quad(split - line * 0.5, content[1], split + line * 0.5, content[3]),
                       (1.0, 1.0, 1.0, 0.92))
            grip = min(content[3] - content[1], 26 * scale) * 0.5
            cy = (content[1] + content[3]) * 0.5
            grip_rect = (split - grip * 0.45, cy - grip, split + grip * 0.45, cy + grip)
            if studio_enabled():
                draw_rounded_fill(shader, grip_rect, grip * 0.4, (1.0, 1.0, 1.0, 0.95), pixel_size)
            else:
                _triangles(shader, _quad(*grip_rect), (1.0, 1.0, 1.0, 0.95))
        else:   # FADE (and DIFF without both images): B over A
            if source_a is not None and rect_a:
                _draw_source(source_a, rect_a, content, 1.0)
            if source_b is not None and rect_b:
                _draw_source(source_b, rect_b, content,
                             item.compare_blend if source_a is not None else 1.0)
            if source_a is None and source_b is None:
                _triangles(shader, _quad(*content), (0.0, 0.0, 0.0, 0.28))
    finally:
        gpu.state.blend_set(previous)


def _centered_text(text, rect, size, color):
    blf.size(0, size)
    width, height = blf.dimensions(0, text)
    draw_canvas_text(0, text, (rect[0] + rect[2]) * 0.5 - width * 0.5,
                     (rect[1] + rect[3]) * 0.5 - height * 0.5, color, size)


def draw_compare_overlay(item, region, settings, bounds):
    """Buttons, title and 'Pick' hints, in region pixels above the card."""
    layout = compare_layout(item, bounds)
    if layout is None or layout['size'] < MIN_BUTTON_PIXELS:
        return          # too small on screen to show readable buttons
    x0, y0, x1, y1 = bounds
    scale = layout['scale']
    font = max(6, round(layout['size'] * 0.5))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        accent = selection_color()
        content = layout['content']
        for side in ('A', 'B'):
            if side_item(settings, item, side) is not None:
                continue
            if item.compare_mode == 'SPLIT':
                split = divider_x(content, item.compare_split)
                area = (content[0], content[1], split, content[3]) if side == 'A' \
                    else (split, content[1], content[2], content[3])
            else:
                area = content
            if area[2] - area[0] > font * 3:
                _centered_text(f'Pick {side}', area, font, (1.0, 1.0, 1.0, 0.5))
        for name in ('MODE', 'A', 'B'):
            rect = layout[name]
            if rect is None:
                continue
            assigned = name == 'MODE' or side_item(settings, item, name) is not None
            fill = (*accent[:3], 0.92) if assigned else (0.035, 0.055, 0.075, 0.94)
            if studio_enabled():
                radius = max(1.0, (rect[3] - rect[1]) * 0.22)
                draw_rounded_fill(shader, rect, radius, fill, antialias=True)
                draw_rounded_border(shader, rect, radius, max(1.0, scale), (*accent[:3], 0.9),
                                    antialias=True)
            else:
                _triangles(shader, _quad(*rect), fill)
            label = MODE_LABELS.get(item.compare_mode, 'Split') if name == 'MODE' else name
            _centered_text(label, rect, font if name == 'MODE' else round(font * 1.35),
                           (0.05, 0.07, 0.1, 1.0) if assigned else (1.0, 1.0, 1.0, 0.95))
    finally:
        gpu.state.blend_set(previous)

    if item.text_show_header and item.name:
        left_limit = (layout['MODE'] or layout['A'])[0] - 6 * scale
        size = max(5, round(item.text_font_size * scale))
        blf.size(0, size)
        blf.enable(0, blf.CLIPPING)
        blf.clipping(0, x0 + 2, y0, left_limit, y1)
        try:
            draw_canvas_text(0, item.name, x0 + 12 * scale, y1 - 12 * scale - size,
                             (*item.text_color, 1.0), size)
        finally:
            blf.disable(0, blf.CLIPPING)
