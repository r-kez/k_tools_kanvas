"""Time the CPU side of drawing a curved shape at the highest curve resolution.

    blender -b --factory-startup -P scratch/bench_shape_curves.py
"""
import math
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_shape import set_vertex_type
from k_tools_kanvas.properties import set_shape_vertices
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.gpu import gpu_arrow, gpu_shape


def timed(label, function, repeat=5):
    start = time.perf_counter()
    for _ in range(repeat):
        result = function()
    elapsed = (time.perf_counter() - start) / repeat * 1000.0
    print(f'{label:<34} {elapsed:9.2f} ms')
    return result


addon.register()
try:
    tree = bpy.data.node_groups.new('Bench', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    item = settings.images.add()
    item.item_type = 'SHAPE'
    item.item_id = 'bench'
    item.shape_kind = 'POLYGON'
    count = 30
    # A wavy star: concave, so the triangulation has real work to do.
    set_shape_vertices(item, [(0.5 * (1.0 if i % 2 else 0.6) * math.cos(math.tau * i / count),
                               0.5 * (1.0 if i % 2 else 0.6) * math.sin(math.tau * i / count))
                              for i in range(count)])
    item.shape_width = item.shape_height = 400.0
    set_vertex_type(item, list(range(count)), 'AUTO')
    item.shape_curve_resolution = 64
    item.rotation = 10.0

    points = timed('outline (cached curve)', lambda: sg.outline(item))
    print('outline points:', len(points))
    triangles = timed('triangulate', lambda: sg.triangulate(points), repeat=1)
    print('triangles:', len(triangles))
    timed('fill fringe', lambda: gpu_arrow._antialias_fringe(gpu_shape._clockwise(points), 1.0, (1, 1, 1, 1)))
    strokes = gpu_shape._outline_strokes(points, 'SOLID', 3.0)

    def stroke_geometry():
        total = 0
        for stroke in strokes:
            tris, contour = gpu_arrow._rounded_stroke(stroke, 1.5)
            total += len(tris)
            if contour:
                gpu_arrow._antialias_fringe(contour, 0.75, (1, 1, 1, 1))
        return total
    timed('outline strokes (per segment)', stroke_geometry, repeat=1)
    if hasattr(gpu_shape, 'shape_draw_geometry'):
        gpu_shape._geometry_cache.clear()
        timed('draw geometry, first frame', lambda: gpu_shape.shape_draw_geometry(item, 1.0), repeat=1)
        timed('draw geometry, next frames', lambda: gpu_shape.shape_draw_geometry(item, 1.0))
        timed('hit test', lambda: sg.hit_shape(item, (0.0, 0.0), 2.0))
    print('BENCH DONE')
finally:
    addon.unregister()
