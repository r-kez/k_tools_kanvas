"""Draw the outline and name of a selected group.

A group has no body of its own. It only shows a thin dashed outline around its
members while it is selected, so a board with many groups stays clean.
"""

import blf
import gpu

from .gpu_arrow import _draw_plain_strokes
from .gpu_theme import (disable_soft_text_shadow, draw_canvas_text,
                        enable_soft_text_shadow, selection_color)

LABEL_PIXELS = 12


def _selected_groups(settings):
    return [item for item in settings.images
            if item.item_type == 'FRAME' and item.frame_is_group and item.show_in_editor
            and item.is_selected]


def _bounds(group):
    left, top = group.location
    return left, top - group.frame_height, left + group.frame_width, top


def draw_group_outlines(settings, pixel_size):
    groups = _selected_groups(settings)
    if not groups:
        return
    from ..arrow_geometry import dash_polylines
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    smooth = gpu.shader.from_builtin('SMOOTH_COLOR')
    color = (*selection_color()[:3], 0.9)
    thickness = 1.5 * pixel_size
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        for group in groups:
            left, bottom, right, top = _bounds(group)
            loop = [(left, bottom), (right, bottom), (right, top), (left, top), (left, bottom)]
            strokes = dash_polylines(loop, 9.0 * pixel_size, 5.0 * pixel_size)
            _draw_plain_strokes(shader, smooth, strokes, thickness, pixel_size, color)
    finally:
        gpu.state.blend_set(old_blend)


def draw_group_labels(settings, region):
    view = region.view2d
    for group in _selected_groups(settings):
        left, _, _, top = _bounds(group)
        x, y = view.view_to_region(left, top, clip=False)
        if x < -400 or y < -50 or x > region.width + 400 or y > region.height + 50:
            continue
        color = (*selection_color()[:3], 1.0)
        blf.size(0, LABEL_PIXELS)
        blf.color(0, *color)
        shadow = enable_soft_text_shadow(color)
        try:
            draw_canvas_text(0, group.name, x, y + 5, color, LABEL_PIXELS)
        finally:
            if shadow:
                disable_soft_text_shadow()
