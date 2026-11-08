"""Line options of shapes: joins (round, miter, bevel), ends (round, flat, square) and
alignment (center, inside, outside), checked by which canvas points the line covers,
plus SVG export and import of the same options."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_shape import PolygonSession, combine_shapes, import_svg_shapes
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils import stroke_geometry as sk
from k_tools_kanvas.utils import svg_shapes as svg
from k_tools_kanvas.utils.gpu import gpu_shape


def close(a, b, tol=1e-6):
    return math.dist(a, b) < tol


def inside_triangle(p, a, b, c):
    def side(u, v, w):
        return (w[0] - u[0]) * (v[1] - u[1]) - (v[0] - u[0]) * (w[1] - u[1])
    d1, d2, d3 = side(a, b, p), side(b, c, p), side(c, a, p)
    negative = d1 < -1e-9 or d2 < -1e-9 or d3 < -1e-9
    positive = d1 > 1e-9 or d2 > 1e-9 or d3 > 1e-9
    return not (negative and positive)


def covered(triangles, point):
    return any(inside_triangle(point, *triangles[i:i + 3]) for i in range(0, len(triangles), 3))


def line_triangles(item):
    gpu_shape._geometry_cache.clear()
    (triangles, fringe, _), _color = gpu_shape.shape_draw_geometry(item, 1.0)['line']
    assert fringe, 'the line keeps its anti-aliasing'
    return triangles


def extent(triangles):
    xs, ys = [p[0] for p in triangles], [p[1] for p in triangles]
    return min(xs), min(ys), max(xs), max(ys)


# --- pure geometry ----------------------------------------------------------------------
# A right-angle corner turning left at (10, 0): the outer corner is at the bottom right.
tri, contour = sk.join((10.0, 0.0), (1.0, 0.0), (0.0, 1.0), 1.0, 'MITER')
assert any(close(p, (11.0, -1.0)) for p in contour), contour
tri, contour = sk.join((10.0, 0.0), (1.0, 0.0), (0.0, 1.0), 1.0, 'BEVEL')
assert len(contour) == 3 and not any(close(p, (11.0, -1.0)) for p in contour)
tri, contour = sk.join((10.0, 0.0), (1.0, 0.0), (0.0, 1.0), 1.0, 'ROUND')
assert all(abs(math.dist(p, (10.0, 0.0)) - 1.0) < 1e-9 for p in contour[1:])
# A hairpin is beyond the miter limit: bevelled instead of a long spike.
angle = math.radians(170.0)
tri, contour = sk.join((0.0, 0.0), (1.0, 0.0), (math.cos(angle), math.sin(angle)), 1.0, 'MITER')
assert len(contour) == 3 and max(math.dist(p, (0.0, 0.0)) for p in contour) <= 1.0 + 1e-9
# Straight on: no join at all.
assert sk.join((0.0, 0.0), (1.0, 0.0), (1.0, 0.0), 1.0, 'MITER') == ([], [])
# Ends.
assert sk.cap((0.0, 0.0), (1.0, 0.0), 1.0, 'FLAT') == ([], [])
tri, contour = sk.cap((0.0, 0.0), (1.0, 0.0), 1.0, 'SQUARE')
assert max(p[0] for p in contour) == 1.0 and min(p[0] for p in contour) == 0.0
# Offset: a counter-clockwise square moved 5 to the left (inwards) is 10 smaller.
square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
moved = sk.offset_contour(square, 5.0)
assert all(close(a, b) for a, b in zip(moved, [(5, 5), (95, 5), (95, 95), (5, 95)])), moved
assert len(sk.offset_contour(square + [(0.0, 100.0)], 5.0)) == 5, 'one point per point'

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Lines', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(50.0, 50.0),
                                           size=(100.0, 100.0)) == {'FINISHED'}
        box = settings.images[-1]
        box.shape_line_width = 10.0
        assert (box.shape_line_join, box.shape_line_cap, box.shape_line_align) == \
            ('ROUND', 'ROUND', 'CENTER'), 'defaults keep the old look'
        corner = (104.0, 104.0)                   # inside the square corner of the line only
        assert not covered(line_triangles(box), corner), 'round join'
        box.shape_line_join = 'MITER'
        triangles = line_triangles(box)
        assert covered(triangles, corner)
        assert all(abs(a - b) < 1e-6 for a, b in zip(extent(triangles), (-5, -5, 105, 105)))
        box.shape_line_join = 'BEVEL'
        triangles = line_triangles(box)
        assert not covered(triangles, corner) and covered(triangles, (101.0, 101.0))
        # Alignment.
        box.shape_line_join = 'MITER'
        box.shape_line_align = 'INSIDE'
        triangles = line_triangles(box)
        assert all(abs(a - b) < 1e-6 for a, b in zip(extent(triangles), (0, 0, 100, 100)))
        box.shape_line_align = 'OUTSIDE'
        triangles = line_triangles(box)
        assert all(abs(a - b) < 1e-6 for a, b in zip(extent(triangles), (-10, -10, 110, 110)))
        # Dashes follow the alignment and the end style.
        box.shape_line_style = 'DASHED'
        box.shape_line_cap = 'FLAT'
        triangles = line_triangles(box)
        assert extent(triangles)[0] >= -10.0 - 1e-6
        box.shape_line_style = 'DOTTED'
        assert line_triangles(box), 'dots keep round ends, so they never vanish'
        box.shape_line_style = 'SOLID'

        # A hole: inside a frame, the hole's line lies in the material, not in the hole.
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(50.0, 50.0),
                                           size=(40.0, 40.0)) == {'FINISHED'}
        hole_id = settings.images[-1].item_id
        box_id = box.item_id
        shapes = [item for item in settings.images if item.item_id in {box_id, hole_id}]
        base = next(item for item in shapes if item.item_id == box_id)
        frame = combine_shapes(context, settings, shapes, base)
        frame.shape_line_align = 'INSIDE'
        triangles = line_triangles(frame)
        assert covered(triangles, (72.0, 50.0)), 'line beside the hole, in the material'
        assert not covered(triangles, (68.0, 50.0)), 'nothing inside the hole'
        frame.shape_line_align = 'OUTSIDE'
        triangles = line_triangles(frame)
        assert covered(triangles, (68.0, 50.0)) and not covered(triangles, (72.0, 50.0))

        # Open path ends.
        pen = PolygonSession('PEN')
        for point in ((0.0, 300.0), (200.0, 300.0)):
            pen.add_point(context, settings, point)
        assert pen.finish(context, settings)
        line = settings.images[settings.active_image_index]
        line_id = line.item_id
        line.shape_line_width = 10.0
        line.shape_line_align = 'INSIDE'          # ignored: an open path has no inside
        for cap, low, high in (('FLAT', 0.0, 200.0), ('SQUARE', -5.0, 205.0),
                               ('ROUND', -5.0, 205.0)):
            line.shape_line_cap = cap
            line.shape_line_join = 'MITER' if cap != 'ROUND' else 'ROUND'
            left, bottom, right, top = extent(line_triangles(line))
            assert abs(left - low) < 0.05 and abs(right - high) < 0.05, (cap, left, right)
            assert abs(bottom - 295.0) < 0.05 and abs(top - 305.0) < 0.05

        # --- SVG -------------------------------------------------------------------------
        for item in settings.images:
            item.is_selected = item.item_id in {line_id, frame.item_id}
        frame = next(item for item in settings.images if item.item_id == box_id)
        line = next(item for item in settings.images if item.item_id == line_id)
        line.shape_line_cap = 'SQUARE'
        line.shape_line_join = 'BEVEL'
        text = svg.export_svg([frame, line])
        assert 'stroke-linecap="square"' in text and 'stroke-linejoin="bevel"' in text
        assert 'stroke-miterlimit="4"' in text, 'the frame uses miter'
        assert 'stroke="none"' in text and f'id="{frame.name} line"' in text, \
            'an outside line goes on its own path'
        [parsed] = [o for o in svg.parse_svg(text) if o['name'] == line.name]
        assert parsed['cap'] == 'SQUARE' and parsed['join'] == 'BEVEL'
        defaults = svg.parse_svg('<svg xmlns="http://www.w3.org/2000/svg">'
                                 '<path d="M0 0 L10 0 L10 10" stroke="red" fill="none"/></svg>')
        assert defaults[0]['join'] == 'MITER' and defaults[0]['cap'] == 'FLAT', 'SVG defaults'
        for item in settings.images:
            item.is_selected = False
        [copy] = import_svg_shapes(context, settings, '<svg xmlns="http://www.w3.org/2000/svg">'
                                   '<path d="M0 0 L10 0 L10 10" stroke="red" fill="none" '
                                   'stroke-linejoin="bevel" stroke-linecap="square"/></svg>',
                                   (0.0, 600.0), 0.0)[0]
        assert copy.shape_line_join == 'BEVEL' and copy.shape_line_cap == 'SQUARE'
        assert not copy.shape_closed

        # Copy Style carries the line options.
        from k_tools_kanvas.operators.ops_style import STYLE_PROPERTIES
        assert {'shape_line_join', 'shape_line_cap', 'shape_line_align'} <= set(
            STYLE_PROPERTIES['SHAPE'])

    print('STROKE OPTIONS PASS')
finally:
    addon.unregister()
