"""Shapes with holes: several contours per shape, even-odd fill and picking, editing
vertices per contour, Combine Shapes / Separate Contours, and SVG subpaths, fill-rule
and export."""
import math
import os
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_arrow import _create_arrow
from k_tools_kanvas.operators.ops_shape import (combine_shapes, delete_shape_vertices,
                                                import_svg_shapes, insert_shape_vertex,
                                                separate_contours, set_vertex_type)
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils import svg_shapes as svg
from k_tools_kanvas.utils.arrow_geometry import endpoint
from k_tools_kanvas.utils.gpu import gpu_shape


def close(a, b, tol=1e-3):
    return math.dist(a, b) < tol


def fill_area(item):
    points = sg.outline(item)
    return sum(abs(sg.signed_area([points[a], points[b], points[c]]))
               for a, b, c in sg.fill_triangles(item))


def contours_of(item):
    return [stop - start for start, stop in sg.item_contour_ranges(item)]


# --- pure helpers ---------------------------------------------------------------------
records = [((0, 0), 'SHARP', (0, 0), (0, 0), 0), ((1, 0), 'SHARP', (0, 0), (0, 0), 0),
           ((1, 1), 'SHARP', (0, 0), (0, 0), 0),
           ((5, 5), 'SHARP', (0, 0), (0, 0), 1), ((6, 5), 'SHARP', (0, 0), (0, 0), 1),
           ((6, 6), 'SHARP', (0, 0), (0, 0), 1), ((5, 6), 'SHARP', (0, 0), (0, 0), 1)]
assert sg.contour_ranges(records) == [(0, 3), (3, 7)]
assert [sg.next_index(records, i) for i in range(7)] == [1, 2, 0, 4, 5, 6, 3]
assert [sg.prev_index(records, i) for i in range(7)] == [2, 0, 1, 6, 3, 4, 5]
assert sg.contour_ranges([r[:4] for r in records]) == [(0, 7)], 'four-item records: one contour'
square = [(0, 0), (10, 0), (10, 10), (0, 10)]
inner = [(3, 3), (7, 3), (7, 7), (3, 7)]
assert sg.contour_depths([square, inner]) == [0, 1]
assert not sg.point_in_contours((5, 5), [square, inner])
assert sg.point_in_contours((1, 5), [square, inner])

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Holes', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        # --- Combine: a big square and a small one inside make a frame with a hole --------
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 100.0),
                                           size=(200.0, 200.0)) == {'FINISHED'}
        outer_id = settings.images[-1].item_id
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 100.0),
                                           size=(100.0, 100.0)) == {'FINISHED'}
        inner_id = settings.images[-1].item_id
        by_id = {item.item_id: item for item in settings.images}
        by_id[inner_id].rotation = 45.0
        # An arrow attached to the inner square keeps its place on the canvas.
        arrow = _create_arrow(settings, (0.0, 0.0))
        arrow.end_item_id = inner_id
        arrow.end_uv = (1.0, 0.5)
        tip = endpoint(settings, arrow, 'end')
        for item in settings.images:
            item.is_selected = True
        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_id == outer_id)
        assert bpy.ops.kanvas.combine_shapes() == {'FINISHED'}
        shapes = [item for item in settings.images if item.item_type == 'SHAPE']
        assert len(shapes) == 1 and shapes[0].item_id == outer_id, 'the active shape stays'
        ring = shapes[0]
        assert contours_of(ring) == [4, 4] and ring.shape_kind == 'POLYGON'
        assert arrow.end_item_id == outer_id and close(endpoint(settings, arrow, 'end'), tip)
        left, bottom, right, top = sg.bounds(ring)
        assert close((left, bottom), (0.0, 0.0)) and close((right, top), (200.0, 200.0))
        # Even-odd fill: the triangles cover the frame only.
        assert abs(fill_area(ring) - (200.0 ** 2 - 100.0 ** 2)) < 1.0, fill_area(ring)
        assert sg.hit_shape(ring, (10.0, 100.0), 1.0), 'the frame is picked'
        assert not sg.hit_shape(ring, (100.0, 100.0), 1.0), 'the hole is not'
        assert not sg.contains(ring, (100.0, 100.0))
        assert sg.hit_shape(ring, sg.outlines(ring)[1][0], 1.0), 'the hole edge is'
        # Arrows attach to the hole's edge too.
        hit = sg.outline_attach(ring, (100.0 + 73.0, 100.0), 5.0)  # just past the corner
        assert hit is not None and close(hit[1], (100.0 + 50.0 * math.sqrt(2), 100.0), 0.5)

        # Drawing: one stroke per edge of each contour, and a fringe around both.
        parts = gpu_shape.shape_draw_geometry(ring, 1.0)
        assert parts['fill'] is not None and parts['line'] is not None
        strokes = gpu_shape._contour_strokes(ring, 'SOLID', 3.0)
        assert len(strokes) == 8 and all(len(s) == 2 for s in strokes)
        assert all(not (close(s[0], sg.outlines(ring)[0][3]) and close(s[1], sg.outlines(ring)[1][0]))
                   for s in strokes), 'no stroke jumps between contours'
        fringe, _ = gpu_shape._fill_fringe(sg.outlines(ring), 1.0, (1, 1, 1, 1))
        # The hole's fringe lies inside the hole (outside the filled area).
        hole_fringe = fringe[len(fringe) // 2:]
        assert all(not sg.point_in_contours(p, sg.outlines(ring)) or sg.nearest_outline_edge(
            ring, p)[2] < 1e-6 for p in hole_fringe)
        assert '2 contours' in gpu_shape.vertex_edit_title(ring)

        # --- Editing per contour --------------------------------------------------------
        # Inserting on the closing edge of the hole keeps the vertex in the hole.
        hole_last = 7
        index = insert_shape_vertex(ring, hole_last, 0.5)
        assert index == 8 and contours_of(ring) == [4, 5] and ring.shape_vertices[8].contour == 1
        assert abs(fill_area(ring) - (200.0 ** 2 - 100.0 ** 2)) < 1.0, 'shape unchanged'
        # Auto handles take their neighbours from their own contour.
        set_vertex_type(ring, [4], 'AUTO')
        handles = sg.effective_handles(sg.item_records(ring))
        prev, nxt = ring.shape_vertices[8].co, ring.shape_vertices[5].co
        expected = ((nxt[0] - prev[0]) / 6.0, (nxt[1] - prev[1]) / 6.0)
        co = ring.shape_vertices[4].co
        assert close((handles[4][1][0] - co[0], handles[4][1][1] - co[1]), expected, 1e-6)
        set_vertex_type(ring, [4], 'SHARP')
        # Deleting until the hole has fewer than three vertices closes it.
        assert delete_shape_vertices(ring, [5, 6]) == ''
        assert contours_of(ring) == [4, 3]
        assert delete_shape_vertices(ring, [5]) == '' and contours_of(ring) == [4]
        assert abs(fill_area(ring) - 200.0 ** 2) < 1.0, 'no hole any more'
        assert delete_shape_vertices(ring, [0, 1]) != '', 'the last contour stays'
        assert len(ring.shape_vertices) == 4

        # --- Separate ------------------------------------------------------------------
        assert bpy.ops.kanvas.create_shape(kind='ELLIPSE', location=(500.0, 0.0),
                                           size=(60.0, 60.0)) == {'FINISHED'}
        dot_id = settings.images[-1].item_id
        for item in settings.images:
            item.is_selected = item.item_type == 'SHAPE'
        ring.text_lines.add().value = 'Label'
        ring = next(item for item in settings.images if item.item_id == outer_id)
        combined = combine_shapes(bpy.context, settings,
                                  [item for item in settings.images if item.is_selected], ring)
        assert contours_of(combined) == [4, 4]
        assert not any(item.item_id == dot_id for item in settings.images)
        count = len(settings.images)
        assert bpy.ops.kanvas.separate_contours() == {'FINISHED'}
        assert len(settings.images) == count + 1
        pieces = [item for item in settings.images if item.item_type == 'SHAPE']
        assert sorted(len(p.shape_vertices) for p in pieces) == [4, 4]
        assert all(contours_of(p) == [len(p.shape_vertices)] for p in pieces)
        circle = next(p for p in pieces if sg.has_curves(p))
        assert close(tuple(circle.location), (500.0, 0.0), 0.01)
        assert abs(circle.shape_width * circle.scale_master - 60.0) < 0.01
        assert not circle.text_body and 'Label' in next(
            p for p in pieces if p.item_id == outer_id).text_body
        assert arrow.end_item_id == outer_id, 'the arrow stays with its contour'
        assert all(p.is_selected for p in pieces)

        # --- SVG ------------------------------------------------------------------------
        def document(path, rule=''):
            attribute = f' fill-rule="{rule}"' if rule else ''
            return (f'<svg xmlns="http://www.w3.org/2000/svg"><path id="ring" d="{path}"'
                    f' fill="#ff0000"{attribute}/></svg>')

        same = 'M0 0 H100 V100 H0 Z M25 25 H75 V75 H25 Z'           # both counter-clockwise on screen
        opposite = 'M0 0 H100 V100 H0 Z M25 25 V75 H75 V25 Z'       # the hole wound the other way
        [parsed] = svg.parse_svg(document(same, 'evenodd'))
        assert len(parsed['contours']) == 2 and parsed['fill_rule'] == 'evenodd'
        assert svg.parse_svg(document(same))[0]['fill_rule'] == 'nonzero'

        def imported(text):
            for item in settings.images:
                item.is_selected = False
            shapes, skipped = import_svg_shapes(bpy.context, settings, text, (0.0, -500.0), 0.0)
            assert skipped == 0
            return shapes

        [evenodd] = imported(document(same, 'evenodd'))
        assert contours_of(evenodd) == [4, 4]
        assert abs(fill_area(evenodd) - (100.0 ** 2 - 50.0 ** 2)) < 1.0
        evenodd_id = evenodd.item_id  # later imports add items, which can move this one
        [hole] = imported(document(opposite))
        assert contours_of(hole) == [4, 4], 'nonzero, opposite winding: a hole'
        solid = imported(document(same))
        assert [contours_of(s) for s in solid] == [[4], [4]], 'nonzero, same winding: no hole'
        assert solid[0].name == 'ring 1' and solid[1].name == 'ring 2'

        # Export: one subpath per contour, even-odd; reading it back gives the same shape.
        evenodd = next(item for item in settings.images if item.item_id == evenodd_id)
        for item in settings.images:
            item.is_selected = item.item_id == evenodd.item_id
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, 'ring.svg')
        assert bpy.ops.kanvas.export_shapes_svg(filepath=path) == {'FINISHED'}
        text = open(path, encoding='utf-8').read()
        assert 'fill-rule="evenodd"' in text and text.count('M ') == 2 and text.count('Z') == 2
        before = list(sg.outline(evenodd))
        middle = tuple(evenodd.location)
        [copy] = import_svg_shapes(bpy.context, settings, text, middle, 0.0)[0]
        assert contours_of(copy) == [4, 4]
        assert all(any(close(a, b, 0.05) for b in sg.outline(copy)) for a in before)

        # Undo state covers the contour numbers.
        from k_tools_kanvas.operators.ops_modal import _undo_content_signature
        signature = _undo_content_signature(settings)
        copy.shape_vertices[-1].contour = 5
        assert _undo_content_signature(settings) != signature

    print('SHAPE HOLES PASS')
finally:
    addon.unregister()
