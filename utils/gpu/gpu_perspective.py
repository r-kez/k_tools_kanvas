"""The four corners of the perspective correction, drawn on the canvas while they are edited:
a quadrilateral over the image as it is in the photo, a square handle on each corner and a
heavier bottom edge, so the way the image will turn is clear. Nothing here is drawn into an
exported picture."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .. import perspective

COLOR = (0.35, 1.0, 0.55, 0.95)
BOTTOM_COLOR = (1.0, 0.72, 0.15, 1.0)
FILL_ALPHA = 0.08
LINE_WIDTH = 2.0
HANDLE_HALF = 5.0


def draw_corners(settings, view_pixel_size):
    item = perspective.editing_item(settings, bpy.context.window_manager)
    if item is None:
        return
    points = perspective.corner_canvas_points(item)
    if points is None:
        return
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    fill_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()
    previous = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        fill_shader.bind()
        fill_shader.uniform_float('color', (*COLOR[:3], FILL_ALPHA))
        batch_for_shader(fill_shader, 'TRI_FAN', {'pos': points}).draw(fill_shader)
        shader.bind()
        shader.uniform_float('viewportSize', (viewport[2], viewport[3]))
        shader.uniform_float('lineWidth', LINE_WIDTH)
        shader.uniform_float('color', COLOR)
        sides = []
        for index in range(1, 4):
            sides += [points[index], points[(index + 1) % 4]]
        batch_for_shader(shader, 'LINES', {'pos': sides}).draw(shader)
        shader.uniform_float('lineWidth', LINE_WIDTH * 2.0)
        shader.uniform_float('color', BOTTOM_COLOR)
        batch_for_shader(shader, 'LINES', {'pos': [points[0], points[1]]}).draw(shader)
        half = HANDLE_HALF * view_pixel_size
        fill_shader.bind()
        for index, (x, y) in enumerate(points):
            square = [(x - half, y - half), (x + half, y - half), (x + half, y + half), (x - half, y + half)]
            outer = [(px + (px - x) * 0.4, py + (py - y) * 0.4) for px, py in square]
            fill_shader.uniform_float('color', (1.0, 1.0, 1.0, 0.95))
            batch_for_shader(fill_shader, 'TRI_FAN', {'pos': outer}).draw(fill_shader)
            fill_shader.uniform_float('color', BOTTOM_COLOR if index < 2 else COLOR)
            batch_for_shader(fill_shader, 'TRI_FAN', {'pos': square}).draw(fill_shader)
    finally:
        gpu.state.blend_set(previous)
