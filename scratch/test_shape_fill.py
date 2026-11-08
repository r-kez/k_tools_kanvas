"""The fill of shapes whose contours cross: Combine with partly overlapping shapes and a
self-crossing outline are filled by the even-odd rule (a Delaunay triangulation with a
parity flood), while ordinary shapes keep Blender's fast polygon filler."""
import math
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_shape import combine_shapes
from k_tools_kanvas.properties import set_vertex_records
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.gpu import gpu_shape


def tri_area(a, b, c):
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2


def covered(triangles, point):
    for i in range(0, len(triangles), 3):
        a, b, c = triangles[i:i + 3]
        d1 = (point[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (point[1] - b[1])
        d2 = (point[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (point[1] - c[1])
        d3 = (point[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (point[1] - a[1])
        if not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0)):
            return True
    return False


def canvas_area(item):
    t = sg.fill_canvas_triangles(item)
    return sum(tri_area(*t[i:i + 3]) for i in range(0, len(t), 3))


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Fill', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context
        # Two squares overlapping by a quarter, combined: the overlap is a hole.
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(50.0, 50.0),
                                           size=(100.0, 100.0)) == {'FINISHED'}
        first = settings.images[-1].item_id
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 100.0),
                                           size=(100.0, 100.0)) == {'FINISHED'}
        shapes = list(settings.images)
        base = next(item for item in shapes if item.item_id == first)
        both = combine_shapes(context, settings, shapes, base)
        assert abs(canvas_area(both) - (2 * 100.0 ** 2 - 2 * 50.0 ** 2)) < 0.01, canvas_area(both)
        triangles = sg.fill_canvas_triangles(both)
        assert not covered(triangles, (75.0, 75.0)), 'the overlap is empty (even-odd)'
        assert covered(triangles, (25.0, 25.0)) and covered(triangles, (125.0, 125.0))
        assert sg.contains(both, (25.0, 25.0)) and not sg.contains(both, (75.0, 75.0))
        assert gpu_shape.shape_draw_geometry(both, 1.0)['fill'] is not None

        # A five-pointed star drawn in one stroke, crossing itself: its middle is empty.
        star = [(math.cos(math.radians(90 + 144 * i)) * 0.5, math.sin(math.radians(90 + 144 * i)) * 0.5)
                for i in range(5)]
        both.shape_closed = True
        set_vertex_records(both, [(p, 'SHARP', p, p, 0) for p in star])
        triangles = sg.fill_canvas_triangles(both)
        center = sg.unit_to_canvas(both, (0.0, 0.0))
        tip = sg.unit_to_canvas(both, (0.0, 0.4))
        assert not covered(triangles, center) and covered(triangles, tip)

        # Ordinary shapes keep the fast filler: same triangles as fill_triangles, and a
        # dense outline still triangulates quickly.
        assert bpy.ops.kanvas.create_shape(kind='ELLIPSE', location=(500.0, 0.0),
                                           size=(200.0, 200.0)) == {'FINISHED'}
        circle = settings.images[-1]
        circle.shape_kind = 'POLYGON'
        n = 1920
        ring = [(0.5 * math.cos(math.tau * i / n), 0.5 * math.sin(math.tau * i / n)) for i in range(n)]
        set_vertex_records(circle, [(p, 'SHARP', p, p, 0) for p in ring])
        start = time.perf_counter()
        triangles = sg.fill_unit_triangles(circle)
        elapsed = (time.perf_counter() - start) * 1000.0
        assert len(triangles) == len(sg.fill_triangles(circle)) == n - 2
        print(f'exact fill of {n} vertices: {elapsed:.2f} ms')
        assert elapsed < 60.0, elapsed
        assert sg.fill_unit_triangles(circle) is triangles, 'cached'

        # The Shape Fill preference: Exact by default, Fast on request, the same for
        # every shape; changing it rebuilds the fills.
        from types import SimpleNamespace
        from k_tools_kanvas.preferences import KanvasPreferences
        from k_tools_kanvas.utils.gpu import gpu_common
        assert KanvasPreferences.bl_rna.properties['shape_fill'].default == 'DELAUNAY'
        prefs = SimpleNamespace(shape_fill='DELAUNAY')
        real_get_prefs = gpu_common.get_prefs
        gpu_common.get_prefs = lambda: prefs
        assert sg.fill_method() == 'DELAUNAY'
        before = sg.fill_unit_triangles(circle)
        prefs.shape_fill = 'FAST'
        assert sg.fill_method() == 'FAST'
        fast = sg.fill_unit_triangles(circle)
        assert fast is not before and len(fast) == n - 2
        start = time.perf_counter()
        circle.shape_vertices[0].co = (0.49, 0.0)
        sg.fill_unit_triangles(circle)
        print(f'fast fill of {n} vertices: {(time.perf_counter() - start) * 1000.0:.2f} ms')
        prefs.shape_fill = 'DELAUNAY'
        assert sg.fill_unit_triangles(circle) is not fast
        gpu_common.get_prefs = real_get_prefs

    print('SHAPE FILL PASS')
finally:
    addon.unregister()
