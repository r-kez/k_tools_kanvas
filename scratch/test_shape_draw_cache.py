"""Shape drawing caches: the outline, the fill triangles and the draw geometry are reused
while nothing changes and rebuilt as soon as anything that shows does; a curved edge is
one outline stroke; filling a concave curved shape covers exactly its area."""
import math
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_shape import normalize_shape, set_vertex_type
from k_tools_kanvas.properties import set_shape_vertices
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.gpu import gpu_shape

addon.register()
try:
    tree = bpy.data.node_groups.new('Cache', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    item = settings.images.add()
    item.item_type = 'SHAPE'
    item.item_id = 'cache'
    item.shape_kind = 'POLYGON'
    count = 30
    set_shape_vertices(item, [(0.5 * (1.0 if i % 2 else 0.6) * math.cos(math.tau * i / count),
                               0.5 * (1.0 if i % 2 else 0.6) * math.sin(math.tau * i / count))
                              for i in range(count)])
    item.shape_width = item.shape_height = 400.0
    set_vertex_type(item, list(range(count)), 'AUTO')
    item.shape_curve_resolution = 64

    # Same object while nothing changes.
    first = gpu_shape.shape_draw_geometry(item, 1.0)
    assert gpu_shape.shape_draw_geometry(item, 1.0) is first
    assert sg.outline(item) is sg.outline(item)
    assert sg.fill_triangles(item) is sg.fill_triangles(item)

    # Anything that shows rebuilds it.
    def changes(action):
        before = gpu_shape.shape_draw_geometry(item, 1.0)
        action()
        return gpu_shape.shape_draw_geometry(item, 1.0) is not before

    assert changes(lambda: setattr(item, 'location', (10.0, 0.0)))
    assert changes(lambda: setattr(item, 'rotation', 15.0))
    assert changes(lambda: setattr(item, 'scale_master', 1.5))
    assert changes(lambda: setattr(item, 'shape_fill_color', (0.1, 0.2, 0.3)))
    assert changes(lambda: setattr(item, 'opacity', 0.5))
    assert changes(lambda: setattr(item, 'shape_line_style', 'DASHED'))
    assert changes(lambda: setattr(item, 'shape_curve_resolution', 32))
    vertex = item.shape_vertices[3]
    assert changes(lambda: setattr(vertex, 'co', (vertex.co[0] * 0.9, vertex.co[1] * 0.9)))
    assert changes(lambda: setattr(vertex, 'handle_type', 'SHARP'))
    before = gpu_shape.shape_draw_geometry(item, 1.0)
    assert gpu_shape.shape_draw_geometry(item, 2.0) is not before, 'zoom changes the fringe'
    # The cached outline follows the transform exactly.
    expected = [sg.unit_to_canvas(item, unit) for unit, _, _ in sg.curve_units(item)]
    assert all(math.dist(a, b) < 1e-6 for a, b in zip(expected, sg.outline(item)))

    # Fill: concave and curved, the triangles cover exactly the outline's area.
    points = sg.outline(item)
    area = sum(abs(sg.signed_area([points[a], points[b], points[c]]))
               for a, b, c in sg.fill_triangles(item))
    assert abs(area - abs(sg.signed_area(points))) < 1e-3 * abs(sg.signed_area(points)), area
    # The plain ear clipping (used outside Blender) agrees on a small concave case.
    star = [(0.5 * (1.0 if i % 2 else 0.4) * math.cos(math.tau * i / 10),
             0.5 * (1.0 if i % 2 else 0.4) * math.sin(math.tau * i / 10)) for i in range(10)]
    assert abs(sum(abs(sg.signed_area(list(t))) for t in sg._ear_clip(star))
               - abs(sg.signed_area(star))) < 1e-9

    # Solid outline: one stroke per edge, not one per flattened segment.
    item.shape_line_style = 'SOLID'
    edges = [edge for _, edge, _ in sg.curve_units(item)]
    strokes = gpu_shape._outline_strokes(sg.outline(item), 'SOLID', 3.0, edges)
    assert len(strokes) == count, len(strokes)
    assert sum(len(s) - 1 for s in strokes) == len(sg.outline(item)), 'every segment drawn once'
    assert len(gpu_shape._outline_strokes(sg.vertex_points(item), 'SOLID', 3.0)) == count

    # A redraw of an unchanged, heavily curved shape costs (almost) nothing.
    gpu_shape.shape_draw_geometry(item, 1.0)
    start = time.perf_counter()
    for _ in range(100):
        gpu_shape.shape_draw_geometry(item, 1.0)
    assert (time.perf_counter() - start) / 100 < 0.005, 'cached redraw stays cheap'
    normalize_shape(item)
    print('SHAPE DRAW CACHE PASS')
finally:
    addon.unregister()
