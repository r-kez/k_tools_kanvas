import gpu
from gpu_extras.batch import batch_for_shader
from .common import get_prefs

def draw_axes(size=10000.0):
    """Draw X and Y axis lines for orientation."""
    prefs = get_prefs()
    if prefs is None:
        return

    shader  = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()

    shader.bind()
    shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
    shader.uniform_float("lineWidth", 1.0)

    batch_x = batch_for_shader(shader, 'LINES', {"pos": [(-size, 0), (size, 0)]})
    shader.uniform_float("color", prefs.color_x_axis)
    batch_x.draw(shader)

    batch_y = batch_for_shader(shader, 'LINES', {"pos": [(0, -size), (0, size)]})
    shader.uniform_float("color", prefs.color_y_axis)
    batch_y.draw(shader)
