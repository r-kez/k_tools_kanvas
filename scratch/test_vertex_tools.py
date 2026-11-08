"""Edit Vertices tools: select a contour (L), reverse a contour, flip shapes and selected
vertices, type the position of the selection, G / R / S on selected vertices, and
snapping a dragged vertex to the vertices of other shapes."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_arrow import _create_arrow
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.operators.ops_shape import (combine_shapes, contour_at, flip_vertices,
                                                reverse_contours, select_shape_vertices,
                                                selected_vertex_indices)
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.arrow_geometry import endpoint


class View:
    def region_to_view(self, x, y):
        return (x, y)

    def view_to_region(self, x, y, clip=False):
        return (x, y)


class Helper(KanvasInteractionHelpers):
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


def points(item, indices):
    return [sg.vertex_points(item)[i] for i in indices]


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Vertex tools', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    statuses = []
    fake = SimpleNamespace(area=SimpleNamespace(tag_redraw=lambda: None),
                           region=SimpleNamespace(view2d=View()),
                           space_data=SimpleNamespace(edit_tree=tree),
                           workspace=SimpleNamespace(status_text_set=statuses.append))

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context
        # A frame: outer square (0..200) and a hole (50..150).
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 100.0),
                                           size=(200.0, 200.0)) == {'FINISHED'}
        outer_id = settings.images[-1].item_id
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 100.0),
                                           size=(100.0, 100.0)) == {'FINISHED'}
        inner_id = settings.images[-1].item_id
        shapes = [by_id(settings, outer_id), by_id(settings, inner_id)]
        frame = combine_shapes(context, settings, shapes, shapes[0])
        frame.shape_edit_vertices = True

        # --- L: the contour under the pointer, or of the selection ---------------------
        assert contour_at(frame, (100.0, 50.0), 3.0) == [4, 5, 6, 7], 'hole edge'
        assert contour_at(frame, (0.0, 0.0), 3.0) == [0, 1, 2, 3], 'outer corner'
        assert contour_at(frame, (25.0, 25.0), 3.0) == []
        select_shape_vertices(frame, [5])
        assert bpy.ops.kanvas.select_contour() == {'FINISHED'}
        assert selected_vertex_indices(frame) == [4, 5, 6, 7]
        assert bpy.ops.kanvas.select_contour(location=(0.0, 100.0), use_location=True,
                                             extend=True) == {'FINISHED'}
        assert selected_vertex_indices(frame) == list(range(8))

        # --- Reverse: same outline, the other way round --------------------------------
        before = sorted(points(frame, range(4, 8)))
        first = sg.vertex_points(frame)[4]
        select_shape_vertices(frame, [4])
        assert reverse_contours(frame, [4])
        assert sorted(points(frame, range(4, 8))) == before
        assert close(sg.vertex_points(frame)[7], first), 'order reversed'
        assert selected_vertex_indices(frame) == [7], 'selection follows its vertex'
        assert [v.contour for v in frame.shape_vertices] == [0] * 4 + [1] * 4

        # --- Position: type where the selected vertices go ------------------------------
        select_shape_vertices(frame, [4, 5, 6, 7])
        assert close(tuple(frame.shape_vertex_location), (100.0, 100.0))
        frame.shape_vertex_location = (120.0, 90.0)
        assert close(tuple(frame.shape_vertex_location), (120.0, 90.0))
        xs = [p[0] for p in points(frame, range(4, 8))]
        assert close((min(xs), max(xs)), (70.0, 170.0)), 'the hole moved, not resized'
        assert close(sg.vertex_points(frame)[0], (0.0, 0.0)), 'the outer square stays'

        # --- G / R / S on the selected vertices -----------------------------------------
        def transform(action, start, end, ctrl=False):
            helper = Helper()
            result = helper._start_vertex_transform(fake, settings, action, start)
            assert result == {'RUNNING_MODAL'} and helper.keyboard_transform
            helper._update_shape_gesture(settings, *end, False, ctrl)
            return helper

        helper = transform('MOVE', (0.0, 0.0), (-20.0, 10.0))
        helper._finish_shape_gesture(fake, settings)
        assert close(tuple(frame.shape_vertex_location), (100.0, 100.0))
        assert statuses and statuses[-1] is None, 'the hint is cleared'
        helper = transform('SCALE', (150.0, 100.0), (175.0, 100.0))   # 50 -> 75 from the middle
        helper._finish_shape_gesture(fake, settings)
        xs = [p[0] for p in points(frame, range(4, 8))]
        assert close((min(xs), max(xs)), (25.0, 175.0), 0.01), xs
        helper = transform('ROTATE', (200.0, 100.0), (100.0, 200.0), ctrl=True)  # 90 degrees
        moved = points(frame, range(4, 8))
        ys = [p[1] for p in moved]
        assert close((min(ys), max(ys)), (25.0, 175.0), 0.01), 'a wide hole turned upright'
        helper._cancel_shape_gesture(fake, settings)
        xs = [p[0] for p in points(frame, range(4, 8))]
        assert close((min(xs), max(xs)), (25.0, 175.0), 0.01), 'Esc puts them back'
        select_shape_vertices(frame, [4])
        assert Helper()._start_vertex_transform(fake, settings, 'ROTATE', (0.0, 0.0)) is None, \
            'one vertex: R and S work on the shape'
        select_shape_vertices(frame, [])
        assert Helper()._start_vertex_transform(fake, settings, 'MOVE', (0.0, 0.0)) is None

        # --- Flip -----------------------------------------------------------------------
        frame.shape_edit_vertices = False
        assert bpy.ops.kanvas.create_shape(kind='TRIANGLE', location=(500.0, 0.0),
                                           size=(100.0, 100.0)) == {'FINISHED'}
        triangle_id = settings.images[-1].item_id
        triangle = by_id(settings, triangle_id)
        arrow = _create_arrow(settings, (0.0, 0.0))
        arrow.end_item_id = triangle_id
        arrow.end_uv = (0.5, 1.0)                  # the tip of the triangle, at the top
        tip = endpoint(settings, arrow, 'end')
        for item in settings.images:
            item.is_selected = item.item_id == triangle_id
        assert bpy.ops.kanvas.flip_shape(axis='Y') == {'FINISHED'}
        triangle = by_id(settings, triangle_id)
        tips = [p for p in sg.vertex_points(triangle) if abs(p[0] - 500.0) < 0.01]
        assert len(tips) == 1 and close(tips[0], (500.0, -50.0), 0.01), 'tip now at the bottom'
        assert close(endpoint(settings, arrow, 'end'), (tip[0], -tip[1]), 0.01), \
            'the arrow stays on the tip'
        assert bpy.ops.kanvas.flip_shape(axis='X') == {'FINISHED'}
        assert close(sg.bounds(triangle)[:2], (450.0, -50.0), 0.01), 'stays in its box'
        # In Edit Vertices, only the selection flips.
        triangle.shape_edit_vertices = True
        select_shape_vertices(triangle, [0])
        others = points(triangle, [1, 2])
        assert flip_vertices(triangle, [0, 1], 'Y')
        assert close(points(triangle, [2])[0], others[1], 0.01), 'vertex 2 does not move'

        # --- Vertex snap ----------------------------------------------------------------
        triangle.shape_edit_vertices = False
        frame = by_id(settings, outer_id)
        frame.shape_edit_vertices = True
        for item in settings.images:
            item.is_selected = item.item_id == outer_id
        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_id == outer_id)
        target = sg.vertex_points(by_id(settings, triangle_id))[1]

        def drag_corner_to(point):
            frame = by_id(settings, outer_id)
            select_shape_vertices(frame, [])
            helper = Helper()
            corner = sg.vertex_points(frame)[2]
            helper._start_shape_vertex_gesture(fake, event(*corner), settings, corner, 1.0)
            assert helper.drag_mode == 'SHAPE_VERTEX'
            helper._update_shape_gesture(settings, *point, False, False)
            result = sg.vertex_points(frame)[2]
            helper._cancel_shape_gesture(fake, settings)
            return result

        near = (target[0] + 4.0, target[1] - 3.0)
        assert not settings.snap_shape_vertices, 'off by default'
        assert close(drag_corner_to(near), near, 0.01)
        settings.snap_shape_vertices = True
        assert close(drag_corner_to(near), target, 0.01), 'lands on the other vertex'
        far = (target[0] + 40.0, target[1])
        assert close(drag_corner_to(far), far, 0.01)

    print('VERTEX TOOLS PASS')
finally:
    addon.unregister()
