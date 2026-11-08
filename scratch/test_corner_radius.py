"""Rounded corners: a corner radius in canvas units that stays round on stretched shapes,
shrinks on short edges, leaves curves and open-path ends alone, keeps the box, and is
exported to SVG."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_shape import PolygonSession, normalize_shape, set_vertex_type
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils import svg_shapes as svg
from k_tools_kanvas.utils.gpu import gpu_shape


def area_of(points):
    return abs(sg.signed_area(list(points)))


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Corners', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context
        # A 400 x 100 rectangle: stretched, so a unit-box rounding would be oval.
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(200.0, 50.0),
                                           size=(400.0, 100.0)) == {'FINISHED'}
        box = settings.images[-1]
        assert box.shape_corner_radius == 0.0
        assert len(sg.outline(box)) == 4
        box.shape_corner_radius = 20.0
        points = sg.outline(box)
        assert len(points) > 4 and box.shape_kind == 'RECTANGLE', 'the kind stays'
        # Every point of the bottom-left arc is 20 from (20, 20): a circle, not an ellipse.
        arc = [p for p in points if p[0] < 20.0 + 1e-6 and p[1] < 20.0 + 1e-6]
        assert len(arc) >= 3
        assert all(abs(math.dist(p, (20.0, 20.0)) - 20.0) < 1e-6 for p in arc), arc
        expected = 400.0 * 100.0 - (4.0 - math.pi) * 20.0 ** 2
        assert abs(area_of(points) - expected) < 0.01 * expected
        # The fill and the line follow the rounding; the box does not change.
        fill = sum(area_of(points[i] for i in triangle) for triangle in sg.fill_triangles(box))
        assert abs(fill - area_of(points)) < 1e-3 * fill
        assert gpu_shape.shape_draw_geometry(box, 1.0)['line'] is not None
        left, bottom, right, top = sg.bounds(box)
        assert abs(left) < 1e-6 and abs(right - 400.0) < 1e-6
        width = box.shape_width
        normalize_shape(box)
        assert box.shape_width == width, 'fitting the box ignores the rounding'
        # Corners do not hit the outside of the rounding any more.
        assert not sg.hit_shape(box, (1.0, 1.0), 0.5)
        assert sg.hit_shape(box, (25.0, 25.0), 0.5)

        # The Curve Resolution sets how many segments round each corner.
        assert not sg.has_curves(box) and sg.uses_curve_resolution(box)
        count = len(sg.outline(box))
        box.shape_curve_resolution = 4
        fewer = len(sg.outline(box))
        assert fewer < count and fewer == 4 * (4 + 1), fewer
        box.shape_curve_resolution = 16

        # A huge radius is limited by the edges: the short sides become half circles.
        box.shape_corner_radius = 500.0
        points = sg.outline(box)
        left_end = [p for p in points if p[0] < 50.0 + 1e-6]
        assert all(abs(math.dist(p, (50.0, 50.0)) - 50.0) < 1e-6 for p in left_end)
        box.shape_corner_radius = 20.0

        # Curved edges are left alone; only corners between two straight edges round.
        set_vertex_type(box, [0], 'AUTO')
        rounded = len(sg.outline(box))
        box.shape_corner_radius = 0.0
        plain = len(sg.outline(box))
        assert rounded > plain, 'the corners away from the curve still round'
        box.shape_corner_radius = 20.0

        # Open path: the two ends stay pointed, the middle corner rounds.
        pen = PolygonSession('PEN')
        for point in ((0.0, 300.0), (100.0, 300.0), (100.0, 400.0)):
            pen.add_point(context, settings, point)
        assert pen.finish(context, settings)
        line = settings.images[settings.active_image_index]
        line.shape_corner_radius = 10.0
        points = sg.outline(line)
        assert math.dist(points[0], (0.0, 300.0)) < 1e-6
        assert math.dist(points[-1], (100.0, 400.0)) < 1e-6
        assert len(points) > 3
        assert all(math.dist(p, (100.0, 300.0)) > 2.0 for p in points), 'corner cut off'

        # SVG: the rounded outline is written out.
        text = svg.export_svg([box])
        data = text.split(' d="', 1)[1].split('"', 1)[0]
        assert data.count('L') > 8 and data.endswith('Z')

        # Copy Style and duplicates carry the radius.
        from k_tools_kanvas.operators.ops_style import STYLE_PROPERTIES
        assert 'shape_corner_radius' in STYLE_PROPERTIES['SHAPE']

    print('CORNER RADIUS PASS')
finally:
    addon.unregister()
