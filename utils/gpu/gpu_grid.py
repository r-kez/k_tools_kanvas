import math

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from .gpu_common import get_prefs


def native_node_grid_levels(view_pixel_size, ui_scale=1.0):
    """Blend two adjacent levels of Blender's 20-unit, base-5 dot grid."""
    base_step = 20.0 * max(float(ui_scale), 0.01)
    # Keep the visible spacing near 32 pixels while fading between powers of five.
    level = max(0.0, math.log(32.0 * max(float(view_pixel_size), 1e-8)
                              / base_step, 5.0))
    lower_level = math.floor(level)
    fraction = level - lower_level
    fade = fraction * fraction * (3.0 - 2.0 * fraction)
    lower_step = base_step * 5.0 ** lower_level
    return ((lower_step, 1.0 - fade), (lower_step * 5.0, fade))


def _grid_coordinates(lower, upper, step):
    first = math.ceil(lower / step)
    last = math.floor(upper / step)
    return [index * step for index in range(first, min(last, first + 2047) + 1)]


def _grid_vertices(view_bounds, step):
    x0, y0, x1, y1 = view_bounds
    vertices = []
    for x in _grid_coordinates(x0, x1, step):
        vertices.extend(((x, y0), (x, y1)))
    for y in _grid_coordinates(y0, y1, step):
        vertices.extend(((x0, y), (x1, y)))
    return vertices


def draw_canvas_backdrop(view_bounds, view_pixel_size):
    """Draw optional solid canvas and square guides in Node Editor view space."""
    prefs = get_prefs()
    if prefs is None:
        return
    solid = prefs.canvas_background_enabled
    grid = prefs.canvas_grid_enabled
    if not solid and not grid:
        return

    x0, y0, x1, y1 = view_bounds
    if solid:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'TRIS', {"pos": [
            (x0, y0), (x1, y0), (x1, y1),
            (x0, y0), (x1, y1), (x0, y1),
        ]})
        gpu.state.blend_set('NONE')
        shader.bind()
        shader.uniform_float('color', (*prefs.canvas_background_color, 1.0))
        batch.draw(shader)

    if not grid:
        return

    system_scale = bpy.context.preferences.system.ui_scale
    ui_scale = system_scale if system_scale > 0 else bpy.context.preferences.view.ui_scale
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        shader.uniform_float('viewportSize', (viewport[2], viewport[3]))
        shader.uniform_float('lineWidth', 1.0)
        color = tuple(prefs.canvas_grid_color)
        for step, weight in native_node_grid_levels(view_pixel_size, ui_scale):
            if weight <= 0.001:
                continue
            vertices = _grid_vertices(view_bounds, step)
            if not vertices:
                continue
            shader.uniform_float('color', (*color[:3], color[3] * weight))
            batch_for_shader(shader, 'LINES', {"pos": vertices}).draw(shader)
    finally:
        gpu.state.blend_set('NONE')

def draw_axes(size=10000.0):
    """Draw X and Y axis lines for orientation."""
    prefs = get_prefs()
    if prefs is None:
        return

    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
        shader.uniform_float("lineWidth", 1.0)

        batch_x = batch_for_shader(shader, 'LINES', {"pos": [(-size, 0), (size, 0)]})
        shader.uniform_float("color", prefs.color_x_axis)
        batch_x.draw(shader)

        batch_y = batch_for_shader(shader, 'LINES', {"pos": [(0, -size), (0, size)]})
        shader.uniform_float("color", prefs.color_y_axis)
        batch_y.draw(shader)
    finally:
        gpu.state.blend_set('NONE')
