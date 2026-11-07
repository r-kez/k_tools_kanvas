"""The mode badge and the collapsible Shortcuts panel shared by Mask, Color and Edit Vertices.

Both are drawn in region pixels (POST_PIXEL). The panel remembers whether it is collapsed
across modes and edit sessions, and returns its header rectangle so the caller can hit-test
a click on the minus / plus button.
"""

import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .gpu_theme import draw_rounded_border, draw_rounded_fill

# Shared by every mode that shows the panel.
PANEL_STATE = {'collapsed': False}

BADGE_NORMAL = (0.4, 0.86, 1.0, 1.0)
BADGE_ALERT = (1.0, 0.48, 0.32, 1.0)


def badge_rect(area, region, width, height):
    """Where the badge goes: centered in the free canvas, under the Edit | Move switch.

    The switch sits at the top center, so the badge steps below it while it is visible
    and takes the top slot when the switch is hidden.
    """
    left_edge, right_edge, top_edge = 0.0, float(region.width), region.height - 10.0
    if area is not None:
        try:
            from ...operators.ops_focus import usable_canvas_rect
            left_edge, _bottom, right_edge, _top = usable_canvas_rect(area, region)
            from .gpu_mode_switch import mode_switch_layout
            layout = mode_switch_layout(area, region)
            if layout is not None:
                top_edge = layout['bounds'][1] - 8.0
        except Exception:
            pass
    left = (left_edge + right_edge - width) * 0.5
    left = max(4.0, min(left, region.width - width - 4.0))
    return left, top_edge - height


def draw_mode_badge(region, title, color=BADGE_NORMAL, area=None):
    """A centered pill near the top of the canvas naming the active mode."""
    blf.size(0, 13)
    width = blf.dimensions(0, title)[0] + 28
    height = 31
    left, bottom = badge_rect(area, region, width, height)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        bounds = (left, bottom, left + width, bottom + height)
        draw_rounded_fill(shader, bounds, 6, (0.055, 0.075, 0.095, 0.88))
        draw_rounded_border(shader, bounds, 6, 1, (0.30, 0.70, 0.85, 0.55))
        blf.color(0, *color)
        blf.position(0, left + 14, bottom + 9, 0)
        blf.draw(0, title)
    finally:
        gpu.state.blend_set(previous_blend)


def draw_shortcut_panel(area, region, rows, title='Shortcuts'):
    """Draw the panel at the bottom left; returns the header rectangle, or None if hidden.

    ``rows`` is a sequence of (key, description). The panel steps aside for the toolbar and
    sidebar, and falls back to its header when the area is too small for every row.
    """
    font_size = 11 if region.width < 380 else 12
    blf.size(0, font_size)
    key_width = max(blf.dimensions(0, key)[0] for key, _ in rows)
    description_width = max(blf.dimensions(0, label)[0] for _, label in rows)
    collapsed = PANEL_STATE['collapsed']
    header_height = 26
    header_width = blf.dimensions(0, title)[0] + 62
    width = max(key_width + description_width + 43, header_width)
    if collapsed:
        width = header_width
        height = header_height
    else:
        height = len(rows) * 19 + 18 + header_height
    left = 14
    bottom = 14
    for panel in area.regions:
        if (panel.type != 'WINDOW' and panel.width > 1 and panel.height > 1
                and panel.x <= region.x + left < panel.x + panel.width
                and panel.y <= region.y + bottom < panel.y + panel.height):
            left = max(left, panel.x + panel.width - region.x + 12)
    if left + width > region.width - 10 or bottom + height > region.height - 46:
        if collapsed or left + header_width > region.width - 10:
            return None
        # Too tall for this area: fall back to the header only.
        collapsed = True
        width = header_width
        height = header_height
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        bounds = (left, bottom, left + width, bottom + height)
        draw_rounded_fill(shader, bounds, 7, (0.045, 0.06, 0.075, 0.86))
        header_bottom = bottom + height - header_height
        toggle = (left, header_bottom, left + width, bottom + height)
        blf.color(0, 0.72, 0.78, 0.84, 1.0)
        blf.position(0, left + 12, header_bottom + 8, 0)
        blf.draw(0, title)
        # Collapse / expand button: a minus (collapse) or plus (expand).
        cx = left + width - 17
        cy = header_bottom + header_height * 0.5
        button = (cx - 9, cy - 9, cx + 9, cy + 9)
        draw_rounded_fill(shader, button, 4, (0.30, 0.70, 0.85, 0.30))
        shader.bind()
        shader.uniform_float('color', (0.9, 0.96, 1.0, 1.0))
        lines = [(cx - 5, cy), (cx + 5, cy)]
        if collapsed:
            lines += [(cx, cy - 5), (cx, cy + 5)]
        batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)
        if not collapsed:
            key_x = left + 12
            description_x = key_x + key_width + 17
            for index, (key, description) in enumerate(rows):
                y = header_bottom - 22 - index * 19 + 4
                blf.color(0, 0.38, 0.83, 1.0, 1.0)
                blf.position(0, key_x, y, 0)
                blf.draw(0, key)
                blf.color(0, 0.96, 0.97, 0.98, 1.0)
                blf.position(0, description_x, y, 0)
                blf.draw(0, description)
        return toggle
    finally:
        gpu.state.blend_set(previous_blend)


def toggle_collapsed():
    PANEL_STATE['collapsed'] = not PANEL_STATE['collapsed']
