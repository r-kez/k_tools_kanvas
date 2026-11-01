"""Edit / Move switch drawn at the top of the canvas."""

import blf
import gpu

from .gpu_theme import (draw_rounded_border, draw_rounded_fill,
                        selection_color)

SEGMENT_W = 66.0
HEIGHT = 28.0
TOP_MARGIN = 14.0


def mode_switch_layout(area, region):
    """Rectangles in region pixels, or None when hidden or the canvas is too narrow."""
    from .gpu_common import get_prefs
    prefs = get_prefs()
    if prefs is not None and not getattr(prefs, 'show_mode_overlay', True):
        return None
    from ...operators.ops_focus import usable_canvas_rect
    left, _bottom, right, top = usable_canvas_rect(area, region)
    total = SEGMENT_W * 2
    if right - left < total + 40:
        return None
    x0 = (left + right) * 0.5 - total * 0.5
    y1 = top - TOP_MARGIN
    y0 = y1 - HEIGHT
    return {
        'bounds': (x0, y0, x0 + total, y1),
        'EDIT': (x0, y0, x0 + SEGMENT_W, y1),
        'MOVE': (x0 + SEGMENT_W, y0, x0 + SEGMENT_W * 2, y1),
    }


def hit_mode_switch(area, region, position):
    layout = mode_switch_layout(area, region)
    if layout is None:
        return None
    x, y = position
    for mode in ('EDIT', 'MOVE'):
        left, bottom, right, top = layout[mode]
        if left <= x <= right and bottom <= y <= top:
            return mode
    return None


def _centered_text(text, rect, size, color):
    blf.size(0, size)
    width, height = blf.dimensions(0, text)
    blf.color(0, *color)
    blf.position(0, (rect[0] + rect[2] - width) * 0.5,
                 (rect[1] + rect[3] - height) * 0.5, 0)
    blf.draw(0, text)


def draw_mode_switch(settings, area, region):
    layout = mode_switch_layout(area, region)
    if layout is None:
        return
    accent = selection_color()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        bounds = layout['bounds']
        radius = HEIGHT * 0.5
        draw_rounded_fill(shader, bounds, radius, (0.045, 0.065, 0.085, 0.92),
                          antialias=True)
        active = layout[settings.canvas_mode]
        inset = 3.0
        draw_rounded_fill(shader, (active[0] + inset, active[1] + inset,
                                   active[2] - inset, active[3] - inset),
                          radius - inset, (*accent[:3], 0.9), antialias=True)
        draw_rounded_border(shader, bounds, radius, 1.2,
                            (0.75, 0.88, 1.0, 0.35), antialias=True)
        for mode, label in (('EDIT', 'Edit'), ('MOVE', 'Move')):
            selected = settings.canvas_mode == mode
            _centered_text(label, layout[mode], 13,
                           (0.02, 0.04, 0.06, 1.0) if selected
                           else (0.85, 0.9, 0.95, 1.0))
    finally:
        gpu.state.blend_set(previous_blend)
