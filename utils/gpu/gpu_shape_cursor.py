"""Small shape icon next to the mouse while a shape tool is waiting or drawing.

Mask and Color mode show an icon beside the cursor so the user knows a drawing
mode is active; the shape tools do the same. Nothing here runs a modal operator:
the position comes from the one-shot MOUSEMOVE operator (armed shape) or from the
polygon operator, which is modal only while the user is clicking vertices.
"""

import math

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

# (window pointer, area pointer) -> mouse position inside the WINDOW region.
positions = {}
# Areas where the polygon tool is running: (window pointer, area pointer) -> True.
polygon_areas = {}

COLOR = (0.30, 0.85, 1.0, 1.0)


def area_key(window, area):
    return (window.as_pointer(), area.as_pointer())


def active_kind(key):
    """The shape kind to show for this area, or None."""
    if key in polygon_areas:
        return 'POLYGON'
    from ...operators.ops_modal import _shape_armed_areas
    return _shape_armed_areas.get(key)


def is_active():
    from ...operators.ops_modal import _shape_armed_areas
    return bool(polygon_areas or _shape_armed_areas)


def _icon_lines(kind, cx, cy, r):
    def ring(points):
        return [p for i, a in enumerate(points)
                for p in (a, points[(i + 1) % len(points)])]

    def regular(count, start=math.pi / 2):
        return ring([(cx + math.cos(start + i * math.tau / count) * r,
                      cy + math.sin(start + i * math.tau / count) * r)
                     for i in range(count)])

    if isinstance(kind, str) and kind.startswith('MEASURE:'):
        if kind.split(':')[2] == 'RECT':
            return ring([(cx - r * 1.2, cy - r * 0.85), (cx + r * 1.2, cy - r * 0.85),
                         (cx + r * 1.2, cy + r * 0.85), (cx - r * 1.2, cy + r * 0.85)])
        return [(cx - r * 1.2, cy - r * 0.7), (cx + r * 1.2, cy + r * 0.7),
                (cx - r * 1.2, cy - r * 0.7 - r * 0.5), (cx - r * 1.2, cy - r * 0.7 + r * 0.5),
                (cx + r * 1.2, cy + r * 0.7 - r * 0.5), (cx + r * 1.2, cy + r * 0.7 + r * 0.5)]
    if kind == 'RECTANGLE':
        return ring([(cx - r * 1.2, cy - r * 0.85), (cx + r * 1.2, cy - r * 0.85),
                     (cx + r * 1.2, cy + r * 0.85), (cx - r * 1.2, cy + r * 0.85)])
    if kind == 'ELLIPSE':
        return ring([(cx + math.cos(i * math.tau / 24) * r * 1.2,
                      cy + math.sin(i * math.tau / 24) * r * 0.9) for i in range(24)])
    if kind == 'DIAMOND':
        return regular(4)
    if kind == 'PENTAGON':
        return regular(5)
    if kind == 'HEXAGON':
        return regular(6, 0.0)
    if kind == 'STAR':
        return ring([(cx + math.cos(math.pi / 2 + i * math.pi / 5)
                      * r * (1.1 if i % 2 == 0 else 0.45),
                      cy + math.sin(math.pi / 2 + i * math.pi / 5)
                      * r * (1.1 if i % 2 == 0 else 0.45)) for i in range(10)])
    return regular(3)   # TRIANGLE and POLYGON


def draw_shape_cursor(region):
    window = bpy.context.window
    area = bpy.context.area
    if window is None or area is None:
        return
    key = area_key(window, area)
    kind = active_kind(key)
    position = positions.get(key)
    if kind is None or position is None:
        return
    x, y = position
    if not (0 <= x <= region.width and 0 <= y <= region.height):
        return
    offset_x = 18 if x + 46 < region.width else -30
    offset_y = -22 if y > 42 else 22
    lines = _icon_lines(kind, x + offset_x, y + offset_y, 9)
    lines += [(x - 5, y), (x + 5, y), (x, y - 5), (x, y + 5)]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    previous_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        shader.uniform_float('color', COLOR)
        batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)
    finally:
        gpu.state.blend_set(previous_blend)


def clear():
    positions.clear()
    polygon_areas.clear()
