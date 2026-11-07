"""Edit Vertices, Bezier: bending an edge, vertex types (Sharp, Auto, Aligned, Free),
dragging handles, inserting on a curved edge, the box fitting the curve, undo state,
duplicate, and the flattened outline used for picking and arrow anchors."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers, _undo_content_signature
from k_tools_kanvas.operators.ops_shape import (insert_shape_vertex, select_shape_vertices,
                                                set_vertex_type)
from k_tools_kanvas.properties import vertex_records
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.gpu import gpu_shape
from k_tools_kanvas.utils.item_geometry import item_bounds


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


def event(x, y, shift=False, ctrl=False):
    return SimpleNamespace(type='LEFTMOUSE', value='PRESS', shift=shift, ctrl=ctrl, alt=False,
                           oskey=False, mouse_region_x=x, mouse_region_y=y)


def close(a, b, tol=1e-3):
    return math.dist(a, b) < tol


def outline_through(shape, point, tol=0.5):
    _, distance, _ = sg.nearest_edge(sg.outline(shape), point)
    return distance < tol


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Bezier', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    fake = SimpleNamespace(area=SimpleNamespace(tag_redraw=lambda: None),
                           region=SimpleNamespace(view2d=View()),
                           space_data=SimpleNamespace(edit_tree=tree))

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 50.0),
                                           size=(200.0, 100.0)) == {'FINISHED'}
        shape = settings.images[0]            # box (0, 0) to (200, 100)
        shape.shape_edit_vertices = True

        def press(x, y, shift=False, ctrl=False):
            helper = Helper()
            result = helper._start_shape_vertex_gesture(
                fake, event(x, y, shift, ctrl), settings, (x, y), 1.0)
            return helper, result

        def drag(helper, x, y, finish=True):
            helper._update_shape_gesture(settings, x, y, False, False)
            if finish:
                helper._finish_shape_gesture(fake, settings)

        # Sharp vertices: the outline is exactly the vertices (old files look the same).
        assert not sg.has_curves(shape)
        assert sg.outline(shape) == sg.vertex_points(shape)

        # Dragging the middle of the bottom edge bends it: the curve passes through the
        # pointer, the other edges stay straight, and the box grows to fit the curve.
        helper, result = press(100.0, 0.0)
        assert result == {'RUNNING_MODAL'} and helper.drag_mode == 'SHAPE_BEND'
        drag(helper, 100.0, -40.0, finish=False)
        assert shape.shape_kind == 'POLYGON'
        assert [v.handle_type for v in shape.shape_vertices] == ['FREE', 'FREE', 'SHARP', 'SHARP']
        assert outline_through(shape, (100.0, -40.0)), 'the curve follows the pointer'
        helper._finish_shape_gesture(fake, settings)
        left, bottom, right, top = item_bounds(shape)
        assert abs(bottom + 40.0) < 0.5 and abs(top - 100.0) < 1e-3, (bottom, top)
        assert abs(left) < 1e-3 and abs(right - 200.0) < 1e-3
        assert outline_through(shape, (100.0, -40.0)), 'normalizing keeps the curve'
        assert outline_through(shape, (200.0, 50.0)) and outline_through(shape, (0.0, 50.0))
        # The side edges stay straight: their handles at the bottom corners are on the vertex.
        v0 = shape.shape_vertices[0]
        assert close(tuple(v0.handle_left), tuple(v0.co))
        assert len(sg.outline(shape)) == 4 + sg.CURVE_STEPS - 1

        # Picking: inside the curved bulge picks the shape, the edge hit reports the curve.
        assert sg.hit_shape(shape, (100.0, -30.0), 1.0)
        edge, t = sg.hit_edge(shape, (100.0, -40.0), 2.0)
        assert edge == 0 and abs(t - 0.5) < 0.05, (edge, t)
        # Arrow anchors use the middle of the curve.
        midpoint = sg.unit_to_canvas(shape, sg.edge_midpoints(shape)[0])
        assert close(midpoint, (100.0, -40.0), 0.5), midpoint
        assert any(close(point, midpoint) for _, point in sg.anchor_points(shape))

        # The undo signature sees handle changes.
        signature = _undo_content_signature(settings)
        shape.shape_vertices[0].handle_right = (0.0, -0.5)
        assert _undo_content_signature(settings) != signature

        # Escape during a bend restores everything.
        before = vertex_records(shape)
        helper, _ = press(100.0, 100.0)
        drag(helper, 100.0, 160.0, finish=False)
        assert vertex_records(shape) != before
        helper._cancel_shape_gesture(fake, settings)
        assert vertex_records(shape) == before

        # Vertex types. Start again from a clean rectangle.
        shape.shape_kind = 'RECTANGLE'
        assert not sg.has_curves(shape)
        flat = sg.outline(shape)
        # Sharp -> Free: handles a third of the way to the neighbours, no visible change.
        assert set_vertex_type(shape, [1], 'FREE')
        assert shape.shape_vertices[1].handle_type == 'FREE'
        assert all(outline_through(shape, p, 1e-3) for p in flat)
        assert outline_through(shape, (200.0, 50.0), 1e-3), 'edges stay straight'
        # Auto: smooth; the corner is rounded off, the curve still passes the vertex.
        assert set_vertex_type(shape, [0, 1, 2, 3], 'AUTO')
        assert not outline_through(shape, (200.0, 50.0), 0.5), 'the edges now curve'
        for point in sg.vertex_points(shape):
            assert outline_through(shape, point, 1e-3)
        left, right = sg.handle_points(shape, 1)
        vertex = sg.vertex_points(shape)[1]
        cross = (left[0] - vertex[0]) * (right[1] - vertex[1]) - (left[1] - vertex[1]) * (right[0] - vertex[0])
        assert abs(cross) < 1e-3, 'auto handles are in line'
        # Auto -> Aligned keeps the curve; Aligned -> Sharp makes the corner again.
        curve = sg.outline(shape)
        assert set_vertex_type(shape, [1], 'ALIGNED')
        assert all(close(a, b, 1e-2) for a, b in zip(curve, sg.outline(shape)))
        assert not set_vertex_type(shape, [1], 'ALIGNED'), 'same type: nothing to do'

        # Dragging a handle of a selected Aligned vertex turns the other one to stay in line.
        select_shape_vertices(shape, [1])
        left, right = sg.handle_points(shape, 1)
        helper, result = press(*right)
        assert helper.drag_mode == 'SHAPE_HANDLE' and helper.shape_handle == (1, 'right')
        drag(helper, right[0] + 30.0, right[1] + 10.0)
        left, right = sg.handle_points(shape, 1)
        vertex = sg.vertex_points(shape)[1]
        cross = (left[0] - vertex[0]) * (right[1] - vertex[1]) - (left[1] - vertex[1]) * (right[0] - vertex[0])
        assert abs(cross) < 1e-2, 'aligned handles stay in line'
        # A Free handle moves alone.
        set_vertex_type(shape, [1], 'FREE')
        left_before, right = sg.handle_points(shape, 1)
        helper, _ = press(*right)
        drag(helper, right[0] - 20.0, right[1] + 25.0)
        left_after, _ = sg.handle_points(shape, 1)
        assert close(left_before, left_after, 1e-2), 'free: the other handle does not move'
        # Dragging an Auto handle makes the vertex Mirrored: the other handle repeats it.
        select_shape_vertices(shape, [2])
        _, right = sg.handle_points(shape, 2)
        helper, _ = press(*right)
        drag(helper, right[0] + 15.0, right[1] + 25.0)
        assert shape.shape_vertices[2].handle_type == 'MIRRORED'

        def mirrored(index, tol=1e-2):
            left, right = sg.handle_points(shape, index)
            vertex = sg.vertex_points(shape)[index]
            return close(((left[0] + right[0]) * 0.5, (left[1] + right[1]) * 0.5), vertex, tol)

        assert mirrored(2), 'same angle and same length'
        # A second drag of the other handle keeps the mirror (after normalize).
        left, _ = sg.handle_points(shape, 2)
        helper, _ = press(*left)
        drag(helper, left[0] - 40.0, left[1] + 5.0)
        assert shape.shape_vertices[2].handle_type == 'MIRRORED' and mirrored(2)
        # Aligned keeps each length; Mirrored makes them equal.
        set_vertex_type(shape, [2], 'ALIGNED')
        left, right = sg.handle_points(shape, 2)
        helper, _ = press(*right)
        drag(helper, right[0] + 60.0, right[1])
        assert not mirrored(2), 'aligned: the lengths differ'
        assert set_vertex_type(shape, [2], 'MIRRORED') and mirrored(2)
        assert shape.shape_vertices[2].handle_type == 'MIRRORED'
        # Free -> Mirrored and Sharp -> Mirrored give a symmetric pair too.
        set_vertex_type(shape, [2], 'FREE')
        set_vertex_type(shape, [2], 'MIRRORED')
        assert mirrored(2)
        set_vertex_type(shape, [0], 'SHARP')
        set_vertex_type(shape, [0], 'MIRRORED')
        assert mirrored(0)
        # Saved files keep their meaning: the stored enum values of older types are unchanged.
        items = shape.shape_vertices[0].bl_rna.properties['handle_type'].enum_items
        assert [items[k].value for k in ('SHARP', 'AUTO', 'ALIGNED', 'FREE', 'MIRRORED')] == [0, 1, 2, 3, 4]
        # Handles are hidden (and cannot be grabbed) on unselected and Sharp vertices.
        select_shape_vertices(shape, [])
        assert sg.hit_handle(shape, right, 5.0, []) is None
        set_vertex_type(shape, [3], 'SHARP')
        assert sg.hit_handle(shape, sg.vertex_points(shape)[3], 5.0, [3]) is None

        # Moving a vertex carries its stored handles.
        select_shape_vertices(shape, [1])
        vertex = sg.vertex_points(shape)[1]
        offset = [(h[0] - vertex[0], h[1] - vertex[1]) for h in sg.handle_points(shape, 1)]
        helper, _ = press(*vertex)
        assert helper.drag_mode == 'SHAPE_VERTEX'
        drag(helper, vertex[0] + 20.0, vertex[1] + 20.0)
        vertex = sg.vertex_points(shape)[1]
        after = [(h[0] - vertex[0], h[1] - vertex[1]) for h in sg.handle_points(shape, 1)]
        assert all(close(a, b, 0.5) for a, b in zip(offset, after)), (offset, after)

        # Inserting on a curved edge keeps the curve exactly.
        curve = sg.outline(shape)
        count = len(shape.shape_vertices)
        index = insert_shape_vertex(shape, 1, 0.4)
        assert len(shape.shape_vertices) == count + 1 and index == 2
        assert shape.shape_vertices[index].handle_type == 'ALIGNED'
        for point in curve:
            assert outline_through(shape, point, 0.3), point

        # Ctrl+click on a curved edge inserts too.
        point = sg.unit_to_canvas(shape, sg.edge_midpoints(shape)[0])
        count = len(shape.shape_vertices)
        helper, _ = press(*point, ctrl=True)
        helper._finish_shape_gesture(fake, settings)
        assert len(shape.shape_vertices) == count + 1

        # Duplicate copies the vertex types and handles.
        records = vertex_records(shape)
        shape_id = shape.item_id
        for item in settings.images:
            item.is_selected = item.item_id == shape.item_id
        settings.active_image_index = 0
        assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
        copies = [item for item in settings.images
                  if item.item_type == 'SHAPE' and item.item_id != shape.item_id]
        assert copies and vertex_records(copies[0]) == records
        # Adding an item can move the collection in memory: look the shape up again.
        shape = next(item for item in settings.images if item.item_id == shape_id)

        # The operator and the V menu.
        for item in settings.images:
            item.is_selected = item.item_id == shape.item_id
        settings.active_image_index = 0
        select_shape_vertices(shape, [0])
        assert bpy.ops.kanvas.set_vertex_type(kind='AUTO') == {'FINISHED'}
        assert shape.shape_vertices[0].handle_type == 'AUTO'
        select_shape_vertices(shape, [])
        assert bpy.ops.kanvas.set_vertex_type(kind='SHARP') == {'CANCELLED'}
        assert hasattr(bpy.types, 'KANVAS_MT_vertex_type')
        icons = bpy.types.UILayout.bl_rna.functions['prop'].parameters['icon'].enum_items.keys()
        assert all(icon in icons for _, _, _, icon in sg.HANDLE_TYPES)
        keys = [key for key, _ in gpu_shape.VERTEX_EDIT_ROWS]
        assert 'V' in keys and 'Drag edge' in keys and 'Ctrl+Click edge' in keys

    print('VERTEX BEZIER PASS')
finally:
    addon.unregister()
