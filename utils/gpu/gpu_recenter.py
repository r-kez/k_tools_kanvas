"""Centered canvas prompt for content outside the usable 2D viewport."""

import blf
import gpu

from .gpu_theme import draw_rounded_border, draw_rounded_fill


def draw_recenter_prompt(prompt):
    bounds = prompt['bounds']
    left, bottom, _right, _top = bounds
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        draw_rounded_fill(shader, bounds, 12.0, (0.045, 0.065, 0.085, 0.94),
                          antialias=True)
        draw_rounded_border(shader, bounds, 12.0, 1.4,
                            (0.30, 0.79, 1.0, 0.85), antialias=True)
        blf.size(0, 23)
        blf.color(0, 0.36, 0.85, 1.0, 1.0)
        blf.position(0, left + 16, bottom + 17, 0)
        blf.draw(0, prompt['direction'])
        blf.size(0, 15)
        blf.color(0, 1.0, 1.0, 1.0, 1.0)
        blf.position(0, left + 48, bottom + 29, 0)
        blf.draw(0, 'Recenter')
        blf.size(0, 11)
        blf.color(0, 0.72, 0.78, 0.82, 1.0)
        blf.position(0, left + 48, bottom + 11, 0)
        blf.draw(0, 'Return to origin' if prompt['empty']
                 else 'Content is offscreen')
    finally:
        gpu.state.blend_set(previous_blend)
