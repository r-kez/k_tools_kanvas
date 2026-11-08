"""Open paths and the pen: open-path geometry (no closing edge), drawing with the pen
(corners, dragged curves, open or closed, a new contour of the shape in Edit Vertices),
Ctrl+click on empty space adding a vertex, and SVG lines in and out."""
import math
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.operators.ops_shape import (PolygonSession, add_vertex_at,
                                                delete_shape_vertices, import_svg_shapes,
                                                select_shape_vertices, selected_vertex_indices,
                                                set_vertex_type)
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.gpu import gpu_shape


class View:
    def region_to_view(self, x, y):
        return (x, y)

    def view_to_region(self, x, y, clip=False):
        return (x, y)


class Helper(KanvasInteractionHelpers):
    """The gesture code without a window: one region pixel is one canvas unit."""
    def __init__(self):
        self.reports = []
        self.drag_mode = 'NONE'
        self.keyboard_transform = False

    def _begin_gesture(self, context):
        return {'RUNNING_MODAL'}

    def _end(self, context, result):
        return result

    def report(self, kind, message):
        self.reports.append(message)


def event(x, y, kind='LEFTMOUSE', value='PRESS', shift=False, ctrl=False):
    return SimpleNamespace(type=kind, value=value, shift=shift, ctrl=ctrl, alt=False,
                           oskey=False, mouse_region_x=x, mouse_region_y=y)


def close(a, b, tol=1e-3):
    return math.dist(a, b) < tol


def by_id(settings, item_id):
    return next(item for item in settings.images if item.item_id == item_id)


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Paths', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    fake = SimpleNamespace(area=SimpleNamespace(tag_redraw=lambda: None),
                           region=SimpleNamespace(view2d=View()),
                           space_data=SimpleNamespace(edit_tree=tree))

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context

        # --- Pen: corners and a dragged curve, finished open ---------------------------
        pen = PolygonSession('PEN')
        pen.add_point(context, settings, (0.0, 0.0))
        live = pen.item(settings)
        assert not live.shape_closed and not live.shape_show_fill, 'drawn as an open line'
        pen.add_point(context, settings, (100.0, 0.0))
        pen.drag_handle(settings, (130.0, 40.0))          # a drag after the click curves it
        pen.add_point(context, settings, (200.0, 0.0))
        assert pen.closes_on_finish(settings) is False
        assert pen.finish(context, settings)
        path_id = live.item_id
        path = by_id(settings, path_id)
        assert not path.shape_closed and not path.shape_show_fill and path.shape_show_outline
        kinds = [v.handle_type for v in path.shape_vertices]
        assert kinds == ['SHARP', 'MIRRORED', 'SHARP'], kinds
        left, right = sg.handle_points(path, 1)
        assert close(right, (130.0, 40.0), 0.01) and close(left, (70.0, -40.0), 0.01)
        assert close(sg.outline(path)[0], (0.0, 0.0), 0.01)
        assert close(sg.outline(path)[-1], (200.0, 0.0), 0.01), 'the last point ends the path'

        # Open geometry: no closing edge anywhere.
        assert len(sg.edge_midpoints(path)) == 2
        strokes = gpu_shape._contour_strokes(path, 'SOLID', 3.0)
        assert len(strokes) == 2, 'one stroke per edge, none back to the start'
        assert not sg.hit_shape(path, (40.0, 0.0), 1.0), 'nothing along the missing edge'
        assert sg.hit_shape(path, sg.outline(path)[5], 1.0)
        assert sg.hit_edge(path, (40.0, 0.0), 3.0) is None or sg.hit_edge(
            path, (40.0, 0.0), 3.0)[0] != 2
        assert gpu_shape.shape_draw_geometry(path, 1.0)['line'] is not None

        # Auto at an end of an open path uses the vertex itself for the missing neighbour.
        set_vertex_type(path, [0], 'AUTO')
        records = sg.item_records(path)
        handles = sg.effective_handles(records, False)
        co, nxt = records[0][0], records[1][0]
        assert close(handles[0][1], (co[0] + (nxt[0] - co[0]) / 6, co[1] + (nxt[1] - co[1]) / 6), 1e-6)
        set_vertex_type(path, [0], 'SHARP')

        # An open path keeps two vertices at least.
        assert delete_shape_vertices(path, [1]) == '' and len(path.shape_vertices) == 2
        assert delete_shape_vertices(path, [0]) != ''
        # A straight horizontal line keeps a usable box.
        left, bottom, right, top = sg.bounds(path)
        assert abs(top - bottom) < 1e-6 and abs(right - left - 200.0) < 0.01
        assert path.shape_height >= sg.MIN_SIZE

        # Closing it again: fill comes back only if asked; the outline closes.
        path.shape_closed = True
        assert len(gpu_shape._contour_strokes(path, 'SOLID', 3.0)) == 2   # A->B and B->A
        path.shape_closed = False

        # --- Ctrl+click on empty space extends the path from its selected end ------------
        for item in settings.images:
            item.is_selected = item.item_id == path_id
        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_id == path_id)
        path.shape_edit_vertices = True
        assert gpu_shape.vertex_edit_shape(settings) is not None
        select_shape_vertices(path, [1])                   # the end at (200, 0)

        def ctrl_click(x, y):
            helper = Helper()
            result = helper._start_shape_vertex_gesture(fake, event(x, y, ctrl=True), settings,
                                                        (x, y), 1.0)
            assert result == {'RUNNING_MODAL'} and helper.drag_mode == 'PENDING_VERTEX_BOX'
            return helper._modal_vertex_box(fake, event(x, y, value='RELEASE'), settings, (x, y))

        assert ctrl_click(260.0, 80.0) == {'FINISHED'}
        path = by_id(settings, path_id)
        assert len(path.shape_vertices) == 3 and selected_vertex_indices(path) == [2]
        assert close(sg.vertex_points(path)[2], (260.0, 80.0), 0.01), sg.vertex_points(path)
        assert ctrl_click(300.0, 0.0) == {'FINISHED'}, 'keeps growing from the new end'
        assert close(sg.vertex_points(path)[3], (300.0, 0.0), 0.01)
        # From the first vertex, it grows backwards.
        select_shape_vertices(path, [0])
        assert ctrl_click(-60.0, 50.0) == {'FINISHED'}
        assert close(sg.vertex_points(path)[0], (-60.0, 50.0), 0.01)
        assert selected_vertex_indices(path) == [0] and len(path.shape_vertices) == 5
        # A Ctrl+drag is still a box that removes from the selection.
        helper = Helper()
        helper._start_shape_vertex_gesture(fake, event(-100.0, -100.0, ctrl=True), settings,
                                           (-100.0, -100.0), 1.0)
        helper._modal_vertex_box(fake, event(0.0, 100.0, 'MOUSEMOVE', 'NOTHING'), settings,
                                 (0.0, 100.0))
        helper._modal_vertex_box(fake, event(0.0, 100.0, value='RELEASE'), settings, (0.0, 100.0))
        assert len(path.shape_vertices) == 5 and selected_vertex_indices(path) == []
        # With nothing selected, a closed shape takes the vertex into its nearest edge.
        path.shape_edit_vertices = False
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(0.0, -400.0),
                                           size=(100.0, 100.0)) == {'FINISHED'}
        box = settings.images[-1]
        index = add_vertex_at(box, (0.0, -300.0))           # above the top edge
        assert index == 3 and len(box.shape_vertices) == 5
        assert close(sg.vertex_points(box)[3], (0.0, -300.0), 0.01)

        # --- Pen closed by clicking the first vertex, and as a new contour ---------------
        pen = PolygonSession('PEN')
        for point in ((500.0, 0.0), (700.0, 0.0), (700.0, 200.0), (500.0, 200.0)):
            pen.add_point(context, settings, point)
        assert pen.finish(context, settings, True)
        square_id = pen.item_id
        square = by_id(settings, square_id)
        assert square.shape_closed and square.shape_show_fill
        square.shape_edit_vertices = True
        hole = PolygonSession('PEN', square_id)
        for point in ((550.0, 50.0), (650.0, 50.0), (650.0, 150.0), (550.0, 150.0)):
            hole.add_point(context, settings, point)
        assert hole.closes_on_finish(settings), 'a contour of a closed shape closes'
        assert hole.finish(context, settings)
        square = by_id(settings, square_id)
        assert [b - a for a, b in sg.item_contour_ranges(square)] == [4, 4]
        assert square.shape_edit_vertices and square.is_selected, 'still editing it'
        assert not sg.contains(square, (600.0, 100.0)), 'the new contour is a hole'
        assert sum(1 for item in settings.images if item.item_type == 'SHAPE') == 3
        # Cancelling a contour goes back to the shape.
        again = PolygonSession('PEN', square_id)
        again.add_point(context, settings, (900.0, 0.0))
        again.cancel(settings)
        assert by_id(settings, square_id).is_selected
        # Open and closed shapes are not combined.
        for item in settings.images:
            item.is_selected = item.item_type == 'SHAPE'
        assert bpy.ops.kanvas.combine_shapes() == {'CANCELLED'}

        # --- SVG -----------------------------------------------------------------------
        for item in settings.images:
            item.is_selected = item.item_id == path_id
        folder = tempfile.mkdtemp()
        target = os.path.join(folder, 'path.svg')
        assert bpy.ops.kanvas.export_shapes_svg(filepath=target) == {'FINISHED'}
        text = open(target, encoding='utf-8').read()
        assert 'Z' not in text and 'fill="none"' in text, text
        path = by_id(settings, path_id)
        before = list(sg.outline(path))
        [copy] = import_svg_shapes(context, settings, text, tuple(path.location), 0.0)[0]
        assert not copy.shape_closed and len(copy.shape_vertices) == 5
        assert all(any(close(a, b, 0.05) for b in sg.outline(copy)) for a in before)
        lines, skipped = import_svg_shapes(
            context, settings, '<svg xmlns="http://www.w3.org/2000/svg"><line x1="0" y1="0" '
            'x2="50" y2="0" stroke="red"/><polyline points="0,0 10,10 20,0" fill="none" '
            'stroke="blue"/></svg>', (0.0, 800.0), 0.0)
        assert skipped == 0 and [len(s.shape_vertices) for s in lines] == [2, 3]
        assert all(not s.shape_closed for s in lines)

    print('SHAPE PATHS PASS')
finally:
    addon.unregister()
