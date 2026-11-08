"""Shape tools on the board: boolean union / difference / intersection / exclusion,
Offset Outline, Line to Shape and Simplify, with arrows, holes and the menu."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_arrow import _create_arrow
from k_tools_kanvas.operators.ops_shape import (PolygonSession, combine_shapes, offset_rings,
                                                simplify_shape)
from k_tools_kanvas.utils import shape_boolean as sb
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.arrow_geometry import endpoint


def close(a, b, tol=1e-3):
    return math.dist(a, b) < tol


def filled_area(item):
    """Even-odd area: contours inside an odd number of others are holes."""
    rings = [list(ring) for ring in sg.outlines(item)]
    depths = sg.contour_depths(rings)
    return sum(abs(sb.area([ring])) * (-1 if depth % 2 else 1)
               for ring, depth in zip(rings, depths))


def shapes(settings):
    return [item for item in settings.images if item.item_type == 'SHAPE']


def add(kind, location, size):
    assert bpy.ops.kanvas.create_shape(kind=kind, location=location, size=size) == {'FINISHED'}
    return bpy.context.space_data.edit_tree.kanvas_settings.images[-1].item_id


def select(settings, ids, active=None):
    """Select `ids` in the given order (a list), or in list order (a set)."""
    for item in settings.images:
        item.is_selected = False
    order = ids if isinstance(ids, list) else [item.item_id for item in settings.images
                                               if item.item_id in ids]
    for item_id in order:
        next(item for item in settings.images if item.item_id == item_id).is_selected = True
    if active:
        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_id == active)


def clear(settings):
    while len(settings.images):
        settings.images.remove(0)
    while len(settings.arrows):
        settings.arrows.remove(0)


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Tools', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context
        # --- Union of two overlapping squares, with an arrow on the top one ------------
        a = add('RECTANGLE', (50.0, 50.0), (100.0, 100.0))
        b = add('RECTANGLE', (100.0, 100.0), (100.0, 100.0))
        arrow = _create_arrow(settings, (0.0, 0.0))
        arrow.end_item_id = b
        arrow.end_uv = (1.0, 1.0)
        tip = endpoint(settings, arrow, 'end')
        select(settings, {a, b}, active=a)
        assert bpy.ops.kanvas.boolean_shapes(operation='UNION') == {'FINISHED'}
        [union] = shapes(settings)
        assert union.item_id == a, 'the active shape keeps its look'
        assert abs(filled_area(union) - (2 * 100.0 ** 2 - 50.0 ** 2)) < 0.01
        assert len(union.shape_vertices) == 8 and union.shape_kind == 'POLYGON'
        assert arrow.end_item_id == a and close(endpoint(settings, arrow, 'end'), tip)
        clear(settings)

        # --- Difference: the bottom shape minus the ones above it, holes included -------
        base = add('RECTANGLE', (0.0, 0.0), (200.0, 200.0))
        hole = add('ELLIPSE', (0.0, 0.0), (80.0, 80.0))
        bite = add('RECTANGLE', (100.0, 100.0), (60.0, 60.0))
        # The order of selection decides, not the stacking: the bite, selected first,
        # minus the square leaves the part of the bite outside the square.
        bite_item = next(item for item in shapes(settings) if item.item_id == bite)
        bite_item.z_index = 100                   # on top: the stacking plays no part
        select(settings, [bite, base], active=base)
        assert bpy.ops.kanvas.boolean_shapes(operation='DIFFERENCE') == {'FINISHED'}
        rest = next(item for item in shapes(settings) if item.item_id == bite)
        assert abs(filled_area(rest) - (60.0 ** 2 - 30.0 ** 2)) < 0.01, filled_area(rest)
        assert not any(item.item_id == base for item in shapes(settings))
        clear(settings)
        base = add('RECTANGLE', (0.0, 0.0), (200.0, 200.0))
        hole = add('ELLIPSE', (0.0, 0.0), (80.0, 80.0))
        bite = add('RECTANGLE', (100.0, 100.0), (60.0, 60.0))
        select(settings, [base, bite, hole], active=hole)
        assert bpy.ops.kanvas.boolean_shapes(operation='DIFFERENCE') == {'FINISHED'}
        [cut] = shapes(settings)
        assert cut.item_id == base, 'the first selected shape is cut, whatever is active'
        assert len(sg.item_contour_ranges(cut)) == 2, 'the circle became a hole'
        assert not sg.contains(cut, (0.0, 0.0)) and not sg.contains(cut, (95.0, 95.0))
        assert sg.contains(cut, (-90.0, -90.0))
        disc = math.pi * 40.0 ** 2          # the hole: a circle of radius 40, flattened
        assert abs(filled_area(cut) - (200.0 ** 2 - disc - 30.0 ** 2)) < 0.01 * disc
        clear(settings)

        # --- Intersection, exclusion, and nothing left ---------------------------------
        left = add('ELLIPSE', (0.0, 0.0), (100.0, 100.0))
        right = add('ELLIPSE', (50.0, 0.0), (100.0, 100.0))
        select(settings, {left, right})
        assert bpy.ops.kanvas.boolean_shapes(operation='INTERSECT') == {'FINISHED'}
        [lens] = shapes(settings)
        assert sg.contains(lens, (25.0, 0.0)) and not sg.contains(lens, (-25.0, 0.0))
        clear(settings)
        left = add('RECTANGLE', (0.0, 0.0), (100.0, 100.0))
        right = add('RECTANGLE', (50.0, 0.0), (100.0, 100.0))
        select(settings, {left, right})
        assert bpy.ops.kanvas.boolean_shapes(operation='EXCLUDE') == {'FINISHED'}
        [both] = shapes(settings)
        assert len(sg.item_contour_ranges(both)) == 2, 'two separate pieces in one shape'
        assert abs(filled_area(both) - 2 * 50.0 * 100.0) < 0.01
        assert not sg.contains(both, (25.0, 0.0)) and sg.contains(both, (-25.0, 0.0))
        clear(settings)
        far_a = add('RECTANGLE', (0.0, 0.0), (10.0, 10.0))
        far_b = add('RECTANGLE', (500.0, 0.0), (10.0, 10.0))
        select(settings, {far_a, far_b})
        assert bpy.ops.kanvas.boolean_shapes(operation='INTERSECT') == {'CANCELLED'}
        assert len(shapes(settings)) == 2, 'nothing changed'
        # Open paths are refused.
        pen = PolygonSession('PEN')
        for point in ((0.0, 50.0), (40.0, 80.0)):
            pen.add_point(context, settings, point)
        assert pen.finish(context, settings)
        select(settings, {item.item_id for item in shapes(settings)})
        assert bpy.ops.kanvas.boolean_shapes(operation='UNION') == {'CANCELLED'}
        clear(settings)

        # --- Offset Outline ---------------------------------------------------------------
        square_id = add('RECTANGLE', (0.0, 0.0), (100.0, 100.0))
        select(settings, {square_id}, active=square_id)
        assert bpy.ops.kanvas.offset_shape(distance=10.0) == {'FINISHED'}
        assert len(shapes(settings)) == 2, 'a copy is added'
        bigger = next(item for item in shapes(settings) if item.item_id != square_id)
        assert bigger.is_selected and 'Offset' in bigger.name
        assert abs(filled_area(bigger) - 120.0 ** 2) < 0.01
        select(settings, {square_id}, active=square_id)
        assert bpy.ops.kanvas.offset_shape(distance=-10.0, replace=True) == {'FINISHED'}
        square = next(item for item in shapes(settings) if item.item_id == square_id)
        assert abs(filled_area(square) - 80.0 ** 2) < 0.01 and len(shapes(settings)) == 2
        # A hole shrinks when the shape grows.
        outer = add('RECTANGLE', (500.0, 0.0), (200.0, 200.0))
        inner = add('RECTANGLE', (500.0, 0.0), (100.0, 100.0))
        both = [item for item in shapes(settings) if item.item_id in {outer, inner}]
        ring = combine_shapes(context, settings, both, both[0])
        rings = offset_rings(ring, 10.0)
        sizes = sorted(abs(sb.area([r])) for r in rings)
        assert abs(sizes[1] - 220.0 ** 2) < 0.01 and abs(sizes[0] - 80.0 ** 2) < 0.01, sizes
        clear(settings)

        # --- Line to Shape ----------------------------------------------------------------
        pen = PolygonSession('PEN')
        for point in ((0.0, 0.0), (200.0, 0.0)):
            pen.add_point(context, settings, point)
        assert pen.finish(context, settings)
        line_id = settings.images[settings.active_image_index].item_id
        line = shapes(settings)[0]
        line.shape_line_width = 10.0
        line.shape_line_cap = 'FLAT'
        line.shape_line_color = (0.2, 0.4, 0.6)
        select(settings, {line_id}, active=line_id)
        assert bpy.ops.kanvas.line_to_shape() == {'FINISHED'}
        [band] = shapes(settings)
        assert band.item_id != line_id, 'a line alone is replaced'
        assert band.shape_show_fill and not band.shape_show_outline and band.shape_closed
        assert tuple(round(c, 4) for c in band.shape_fill_color) == (0.2, 0.4, 0.6)
        assert abs(filled_area(band) - 200.0 * 10.0) < 0.01
        clear(settings)
        frame_id = add('RECTANGLE', (0.0, 0.0), (100.0, 100.0))
        frame = shapes(settings)[0]
        frame.shape_line_width = 10.0
        frame.shape_line_join = 'MITER'
        select(settings, {frame_id}, active=frame_id)
        assert bpy.ops.kanvas.line_to_shape() == {'FINISHED'}
        kept = next(item for item in shapes(settings) if item.item_id == frame_id)
        band = next(item for item in shapes(settings) if item.item_id != frame_id)
        assert kept.shape_show_fill and not kept.shape_show_outline, 'the fill stays'
        assert len(sg.item_contour_ranges(band)) == 2
        assert abs(filled_area(band) - (110.0 ** 2 - 90.0 ** 2)) < 0.01
        clear(settings)

        # --- Simplify ----------------------------------------------------------------------
        # A dense polygon (traced or imported) loses the vertices it does not need.
        circle_id = add('RECTANGLE', (0.0, 0.0), (200.0, 200.0))
        circle = shapes(settings)[0]
        from k_tools_kanvas.properties import set_vertex_records
        ring = [(0.5 * math.cos(math.tau * i / 48), 0.5 * math.sin(math.tau * i / 48))
                for i in range(48)]
        circle.shape_kind = 'POLYGON'
        set_vertex_records(circle, [(p, 'SHARP', p, p) for p in ring])
        before, after = simplify_shape(circle, 2.0)
        assert before == 48 and 6 <= after < before, after
        outline = sg.outline(circle)
        assert all(abs(math.dist(p, (0.0, 0.0)) - 100.0) < 2.5 for p in outline)
        simplify_shape(circle, 2.0, smooth=True)
        assert all(v.handle_type == 'AUTO' for v in circle.shape_vertices)
        select(settings, {circle_id}, active=circle_id)
        assert bpy.ops.kanvas.simplify_shape(tolerance=50.0) == {'FINISHED'}
        assert len(circle.shape_vertices) >= 3

        # --- The menu lists the tools ----------------------------------------------------
        from k_tools_kanvas.operators.ops_shape import KANVAS_MT_shape_tools
        assert KANVAS_MT_shape_tools.bl_idname in dir(bpy.types)

    print('SHAPE TOOLS PASS')
finally:
    addon.unregister()
