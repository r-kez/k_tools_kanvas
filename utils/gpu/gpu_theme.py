"""Small GPU primitives shared by the optional canvas styles."""

import math
from functools import lru_cache

import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .gpu_common import get_prefs, pass_cache


def _shadow_alpha(strength, original_alpha):
    """Keep the old look at 50%, then reach full opacity at 100%."""
    if strength <= 0.5:
        return original_alpha * strength * 2.0
    return original_alpha + (1.0 - original_alpha) * (strength - 0.5) * 2.0


@lru_cache(maxsize=24)
def _diffuse_shadow_taps(outer):
    taps = [(0, 0, 0.27)]
    rings = ((outer, 0.155),) if outer <= 8 else (
        (max(2, round(outer * 0.45)), 0.155), (outer, 0.078))
    for radius, weight in rings:
        taps.extend((round(math.cos(index * math.tau / 8) * radius),
                     round(math.sin(index * math.tau / 8) * radius), weight)
                    for index in range(8))
    return tuple(taps)


def enable_soft_text_shadow(color, font_id=0):
    """Give canvas lettering a small contrast halo without extra text draws."""
    prefs = get_prefs()
    if prefs is not None and not getattr(prefs, 'text_shadow_enabled', True):
        return False
    strength = (getattr(prefs, 'text_shadow_strength', 0.5)
                if prefs is not None else 0.5)
    strength = max(0.0, min(1.0, strength))
    if strength == 0.0:
        return False
    spread = (getattr(prefs, 'text_shadow_spread', 'TIGHT')
              if prefs is not None else 'TIGHT')
    if spread == 'DIFFUSE':
        return False  # Each visible text run gets its own broad shadow pass.
    level = {'TIGHT': 3, 'WIDE': 5, 'OUTLINE': 6}.get(spread, 3)
    luminance = (0.2126 * color[0] + 0.7152 * color[1]
                 + 0.0722 * color[2])
    if luminance < 0.48:
        blf.shadow(font_id, level, 1.0, 1.0, 1.0,
                   _shadow_alpha(strength, 0.32))
        blf.shadow_offset(font_id, 0, 0)
    else:
        blf.shadow(font_id, level, 0.0, 0.0, 0.0,
                   _shadow_alpha(strength, 0.45))
        blf.shadow_offset(font_id, 0, -1)
    blf.enable(font_id, blf.SHADOW)
    return True


def disable_soft_text_shadow(font_id=0):
    blf.disable(font_id, blf.SHADOW)


def draw_canvas_text(font_id, value, x, y, color, size):
    """Draw one text run, using extra shadow passes only for large diffuse text."""
    cache = pass_cache()
    config = cache.get('shadow') if cache is not None else None
    if config is None:
        prefs = get_prefs()
        enabled = prefs is None or getattr(prefs, 'text_shadow_enabled', True)
        spread = (getattr(prefs, 'text_shadow_spread', 'TIGHT')
                  if prefs is not None else 'TIGHT')
        strength = (getattr(prefs, 'text_shadow_strength', 0.5)
                    if prefs is not None else 0.5)
        strength = max(0.0, min(1.0, strength))
        config = (enabled, spread, strength)
        if cache is not None:
            cache['shadow'] = config
    enabled, spread, strength = config
    if not enabled or spread != 'DIFFUSE' or strength == 0.0:
        blf.position(font_id, x, y, 0)
        blf.draw(font_id, value)
        return

    luminance = (0.2126 * color[0] + 0.7152 * color[1]
                 + 0.0722 * color[2])
    light_shadow = luminance < 0.48
    shadow_rgb = (1.0, 1.0, 1.0) if light_shadow else (0.0, 0.0, 0.0)
    opacity = _shadow_alpha(strength, 0.32 if light_shadow else 0.45)
    if size <= 32:
        blf.shadow(font_id, 5, *shadow_rgb, opacity)
        blf.shadow_offset(font_id, 0, 0 if light_shadow else -1)
        blf.enable(font_id, blf.SHADOW)
        try:
            blf.position(font_id, x, y, 0)
            blf.draw(font_id, value)
        finally:
            blf.disable(font_id, blf.SHADOW)
        return

    reach = (getattr(prefs, 'text_shadow_diffuse_reach', 1.0)
             if prefs is not None else 1.0)
    reach = max(0.5, min(2.0, reach))
    outer = min(32, max(5, round(size * 0.085 * reach)))
    taps = _diffuse_shadow_taps(outer)
    blf.color(font_id, color[0], color[1], color[2], 0.0)
    blf.enable(font_id, blf.SHADOW)
    try:
        for offset_x, offset_y, weight in taps:
            blf.shadow(font_id, 5, *shadow_rgb, opacity * weight)
            blf.shadow_offset(font_id, offset_x, offset_y)
            blf.position(font_id, x, y, 0)
            blf.draw(font_id, value)
    finally:
        blf.disable(font_id, blf.SHADOW)
        blf.color(font_id, *color)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, value)


def studio_enabled():
    prefs = get_prefs()
    return prefs is not None and getattr(prefs, 'visual_theme', 'CLASSIC') in {'STUDIO', 'GLASS'}


def glass_enabled():
    prefs = get_prefs()
    return prefs is not None and getattr(prefs, 'visual_theme', 'CLASSIC') == 'GLASS'


def glass_tint(color):
    """Keep the chosen color visible through a cool, low-contrast glass tint."""
    return tuple(min(1.0, 0.07 + channel * 0.42) for channel in color[:3])


def selection_color():
    prefs = get_prefs()
    return tuple(prefs.color_selection) if prefs else (0.0, 0.8, 1.0, 1.0)


def rounded_points(left, bottom, right, top, radius, steps=4):
    """Counterclockwise perimeter with a bounded radius for tiny cards."""
    steps = max(1, int(steps))
    radius = max(0.0, min(radius, (right - left) * 0.5, (top - bottom) * 0.5))
    # Keep the same vertex count when an inset corner collapses to a square.
    # Borders pair outer and inner vertices by index, including at tiny zooms.
    points = []
    corners = (
        (right - radius, bottom + radius, -math.pi * 0.5),
        (right - radius, top - radius, 0.0),
        (left + radius, top - radius, math.pi * 0.5),
        (left + radius, bottom + radius, math.pi),
    )
    for cx, cy, start in corners:
        for i in range(steps + 1):
            angle = start + (math.pi * 0.5) * i / steps
            points.append((cx + radius * math.cos(angle),
                           cy + radius * math.sin(angle)))
    return points


def _corner_steps(radius, pixel_size):
    return max(4, min(12, math.ceil(radius / max(pixel_size * 3.0, 1e-6))))


def draw_rounded_fill(shader, bounds, radius, color, pixel_size=1.0,
                      antialias=False):
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        return
    steps = _corner_steps(radius, pixel_size)
    points = rounded_points(*bounds, radius, steps=steps)
    center = ((bounds[0] + bounds[2]) * 0.5, (bounds[1] + bounds[3]) * 0.5)
    vertices = [vertex for i in range(len(points))
                for vertex in (center, points[i], points[(i + 1) % len(points)])]
    if antialias:
        feather = max(pixel_size, 1e-6)
        left, bottom, right, top = bounds
        outer = rounded_points(left - feather, bottom - feather,
                               right + feather, top + feather,
                               radius + feather, steps=steps)
        colors = [color] * len(vertices)
        transparent = (*color[:3], 0.0)
        for i in range(len(points)):
            j = (i + 1) % len(points)
            vertices.extend((points[i], points[j], outer[j],
                             points[i], outer[j], outer[i]))
            colors.extend((color, color, transparent,
                           color, transparent, transparent))
        smooth_shader = gpu.shader.from_builtin('SMOOTH_COLOR')
        smooth_shader.bind()
        batch_for_shader(smooth_shader, 'TRIS', {
            'pos': vertices, 'color': colors,
        }).draw(smooth_shader)
    else:
        shader.bind()
        shader.uniform_float('color', color)
        batch_for_shader(shader, 'TRIS', {'pos': vertices}).draw(shader)


def draw_rounded_border(shader, bounds, radius, thickness, color,
                        pixel_size=1.0, antialias=False):
    left, bottom, right, top = bounds
    if right <= left or top <= bottom:
        return
    thickness = min(thickness, (right - left) * 0.25, (top - bottom) * 0.25)
    if thickness <= 0:
        return
    steps = _corner_steps(radius, pixel_size)
    outer = rounded_points(left, bottom, right, top, radius, steps=steps)
    inner = rounded_points(left + thickness, bottom + thickness,
                           right - thickness, top - thickness,
                           max(0, radius - thickness), steps=steps)
    vertices = []
    for i in range(len(outer)):
        j = (i + 1) % len(outer)
        vertices.extend((outer[i], outer[j], inner[j],
                         outer[i], inner[j], inner[i]))
    if antialias:
        # Add a fading outer pixel to the same batch as the solid border.
        feather = max(pixel_size, 1e-6)
        fringe = rounded_points(left - feather, bottom - feather,
                                right + feather, top + feather,
                                radius + feather, steps=steps)
        colors = [color] * len(vertices)
        transparent = (*color[:3], 0.0)
        for i in range(len(outer)):
            j = (i + 1) % len(outer)
            vertices.extend((outer[i], outer[j], fringe[j],
                             outer[i], fringe[j], fringe[i]))
            colors.extend((color, color, transparent,
                           color, transparent, transparent))
        smooth_shader = gpu.shader.from_builtin('SMOOTH_COLOR')
        smooth_shader.bind()
        batch_for_shader(smooth_shader, 'TRIS', {
            'pos': vertices, 'color': colors,
        }).draw(smooth_shader)
    else:
        shader.bind()
        shader.uniform_float('color', color)
        batch_for_shader(shader, 'TRIS', {'pos': vertices}).draw(shader)


def draw_glass_surface(shader, bounds, radius, color, opacity, pixel_size=1.0):
    """A translucent tinted surface with a restrained upper-edge reflection."""
    left, bottom, right, top = bounds
    tint = glass_tint(color)
    draw_rounded_fill(shader, bounds, radius,
                      (*tint, 0.22 + 0.38 * max(0.0, min(1.0, opacity))),
                      pixel_size, antialias=True)
    if right - left > radius * 2 + 4 * pixel_size:
        reflection = batch_for_shader(shader, 'LINES', {'pos': [
            (left + radius, top - pixel_size),
            (right - radius, top - pixel_size),
        ]})
        shader.bind()
        shader.uniform_float('color', (0.88, 0.96, 1.0, 0.38))
        reflection.draw(shader)
