"""Edit Vertices: vertex selection (click, Shift, box, Ctrl+A/I), moving several vertices,
inserting on an edge, deleting (X/Delete, Ctrl+click, minimum of three) and arrow ends
that sat on a removed vertex dropping onto the new outline."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_arrow import _create_arrow
from k_tools_kanvas.operators.ops_modal import KANVAS_OT_Interact, KanvasInteractionHelpers
from k_tools_kanvas.operators.ops_shape import (delete_shape_vertices, selected_vertex_indices,
                                                select_shape_vertices)
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.arrow_geometry import endpoint
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


def close(a, b, tol=1e-4):
    return math.dist(a, b) < tol


def corners(shape):
    return [tuple(round(c, 4) for c in p) for p in sg.outline(shape)]


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Vertex editing', 'KanvasNodeTree')
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
        assert gpu_shape.vertex_edit_shape(settings) is not None

        def press(x, y, shift=False, ctrl=False):
            helper = Helper()
            result = helper._start_shape_vertex_gesture(
                fake, event(x, y, shift=shift, ctrl=ctrl), settings, (x, y), 1.0)
            return helper, result

        def release(helper, x, y):
            if helper.drag_mode in {'PENDING_VERTEX_BOX', 'VERTEX_BOX'}:
                if (x, y) != tuple(helper.pending_region_start):
                    helper._modal_vertex_box(fake, event(x, y, 'MOUSEMOVE', 'NOTHING'),
                                             settings, (x, y))
                return helper._modal_vertex_box(fake, event(x, y, value='RELEASE'),
                                                settings, (x, y))
            helper._update_shape_gesture(settings, x, y, False, False)
            helper._finish_shape_gesture(fake, settings)
            return {'FINISHED'}

        # A click selects one vertex and never nudges it, even off-center.
        start = corners(shape)
        helper, result = press(2.0, 2.0)
        assert result == {'RUNNING_MODAL'} and helper.drag_mode == 'SHAPE_VERTEX'
        release(helper, 3.0, 2.5)
        assert selected_vertex_indices(shape) == [0]
        assert corners(shape) == start, 'a click does not move the vertex'
        assert shape.shape_kind == 'RECTANGLE', 'selecting keeps the preset'
        assert '1 selected' in gpu_shape.vertex_edit_title(shape)

        # Shift+click adds and removes, without starting a drag.
        _, result = press(199.0, 1.0, shift=True)
        assert result == {'CANCELLED'} and selected_vertex_indices(shape) == [0, 1]
        _, result = press(199.0, 1.0, shift=True)
        assert selected_vertex_indices(shape) == [0]
        press(199.0, 1.0, shift=True)

        # Dragging a selected vertex moves every selected vertex by the same amount,
        # keeping the grab offset (the vertex does not jump onto the pointer).
        helper, _ = press(2.0, 1.0)
        assert helper.shape_vertex_collapse
        release(helper, 12.0, 21.0)
        assert shape.shape_kind == 'POLYGON'
        assert corners(shape)[:2] == [(10.0, 20.0), (210.0, 20.0)], corners(shape)
        assert corners(shape)[2:] == [(200.0, 100.0), (0.0, 100.0)]
        assert selected_vertex_indices(shape) == [0, 1], 'a drag keeps the selection'

        # A click on a selected vertex without moving keeps only that one.
        helper, _ = press(210.0, 20.0)
        release(helper, 210.0, 20.0)
        assert selected_vertex_indices(shape) == [1]

        # Escape restores positions, kind and selection.
        before = corners(shape)
        helper, _ = press(0.0, 100.0)
        helper._update_shape_gesture(settings, 50.0, 150.0, False, False)
        assert corners(shape) != before and selected_vertex_indices(shape) == [3]
        helper._cancel_shape_gesture(fake, settings)
        assert corners(shape) == before and selected_vertex_indices(shape) == [1]

        # Box select from empty canvas: replaces, Shift adds, Ctrl removes.
        helper, result = press(-50.0, -50.0)
        assert result == {'RUNNING_MODAL'} and helper.drag_mode == 'PENDING_VERTEX_BOX'
        release(helper, 300.0, 60.0)
        assert selected_vertex_indices(shape) == [0, 1] and not settings.show_box_sel
        helper, _ = press(-50.0, 90.0, shift=True)
        release(helper, 50.0, 150.0)
        assert selected_vertex_indices(shape) == [0, 1, 3]
        helper, _ = press(-50.0, -50.0, ctrl=True)
        release(helper, 50.0, 150.0)
        assert selected_vertex_indices(shape) == [1]

        # A click inside the shape clears the vertex selection and keeps editing.
        helper, _ = press(100.0, 60.0)
        assert helper.vertex_box_inside
        release(helper, 100.0, 60.0)
        assert selected_vertex_indices(shape) == [] and shape.is_selected

        # A box can also start inside the shape.
        helper, _ = press(100.0, 60.0)
        release(helper, 250.0, -10.0)
        assert selected_vertex_indices(shape) == [1]

        # A click on an edge selects its two vertices and changes nothing.
        helper, _ = press(100.0, 100.0)
        assert helper.drag_mode == 'SHAPE_BEND'
        release(helper, 100.0, 100.0)
        assert selected_vertex_indices(shape) == [2, 3] and len(shape.shape_vertices) == 4
        assert not sg.has_curves(shape)

        # Ctrl+click on an edge adds a vertex there and selects only it.
        helper, _ = press(100.0, 100.0, ctrl=True)
        assert len(shape.shape_vertices) == 5 and selected_vertex_indices(shape) == [3]
        release(helper, 100.0, 100.0)
        assert close(sg.outline(shape)[3], (100.0, 100.0))

        # Ctrl+A selects all, again deselects; Ctrl+I inverts; they never touch the board.
        class Invoker(Helper):
            def __init__(self, action):
                super().__init__()
                self.action = action

        def key(action):
            e = SimpleNamespace(type='A', value='PRESS', shift=False, alt=False, ctrl=True,
                                oskey=False, mouse_x=region.x + 5, mouse_y=region.y + 5,
                                mouse_region_x=5, mouse_region_y=5)
            return KANVAS_OT_Interact.invoke(Invoker(action), bpy.context, e)

        import k_tools_kanvas.operators.ops_modal as modal_module
        original_prefs = modal_module.get_prefs
        modal_module.get_prefs = lambda: SimpleNamespace(box_select_alt_drag=True,
                                                         box_select_on_drag=True)
        try:
            in_canvas = modal_module._event_in_canvas
            modal_module._event_in_canvas = lambda context, e: True
            key('SELECT_ALL')
            assert selected_vertex_indices(shape) == [0, 1, 2, 3, 4]
            key('SELECT_ALL')
            assert selected_vertex_indices(shape) == []
            select_shape_vertices(shape, [0, 2])
            key('SELECT_INVERT')
            assert selected_vertex_indices(shape) == [1, 3, 4]
            assert shape.is_selected and len(settings.images) == 1

            # Delete with nothing selected removes nothing, and never the shape.
            select_shape_vertices(shape, [])
            key('DELETE')
            assert len(settings.images) == 1 and len(shape.shape_vertices) == 5

            # An arrow end on a vertex about to go, and one inside the shape.
            on_vertex = _create_arrow(settings, (0.0, 0.0))
            vertex_point = sg.outline(shape)[1]
            on_vertex.end_item_id = shape.item_id
            on_vertex.end_uv = sg.uv_at(shape, vertex_point)
            inside = _create_arrow(settings, (0.0, 0.0))
            inside.end_item_id = shape.item_id
            inside.end_uv = sg.uv_at(shape, (100.0, 60.0))
            for item in settings.images:
                item.is_selected = item.item_id == shape.item_id
            settings.active_image_index = 0
            for arrow in settings.arrows:
                arrow.is_selected = False

            # X / Delete removes the selected vertices.
            select_shape_vertices(shape, [1, 3])
            key('DELETE')
            assert len(settings.images) == 1 and len(shape.shape_vertices) == 3, \
                len(shape.shape_vertices)
            assert gpu_shape.vertex_edit_shape(settings) is not None, 'still editing'
            points = sg.outline(shape)
            _, distance, _ = sg.nearest_edge(points, endpoint(settings, on_vertex, 'end'))
            assert distance < 1e-3, 'the end on a removed vertex drops onto the outline'
            assert close(endpoint(settings, inside, 'end'), (100.0, 60.0)), \
                'an end inside the shape keeps its place'
        finally:
            modal_module.get_prefs = original_prefs
            modal_module._event_in_canvas = in_canvas

        # A shape keeps at least three vertices.
        assert 'at least 3' in delete_shape_vertices(shape, [0])
        select_shape_vertices(shape, [0])
        helper, result = press(*sg.outline(shape)[0], ctrl=True)
        assert result == {'CANCELLED'} and len(shape.shape_vertices) == 3
        assert any('at least 3' in message for message in helper.reports)
        assert delete_shape_vertices(shape, []) == 'Select vertices to delete'

        # Ctrl+click deletes the vertex under the pointer.
        shape.shape_kind = 'HEXAGON'
        before = len(shape.shape_vertices)
        _, result = press(*sg.outline(shape)[2], ctrl=True)
        assert result == {'FINISHED'} and len(shape.shape_vertices) == before - 1
        assert shape.shape_kind == 'POLYGON'

        # The operator behind X / Delete and the Selection panel button.
        select_shape_vertices(shape, [0])
        assert bpy.ops.kanvas.delete_shape_vertices() == {'FINISHED'}
        assert len(shape.shape_vertices) == before - 2

        # A click on another item still selects it, and leaving the mode drops the selection.
        shape_id = shape.item_id
        assert bpy.ops.kanvas.create_text(location=(900.0, 0.0)) == {'FINISHED'}
        card = settings.images[-1]
        # Adding an item can move the collection in memory: look the shape up again.
        shape = next(item for item in settings.images if item.item_id == shape_id)
        for item in settings.images:
            item.is_selected = item.item_id == shape.item_id
        settings.active_image_index = 0
        select_shape_vertices(shape, [0])
        card_center = (card.location[0] + 5.0, card.location[1] - 5.0)
        _, result = press(*card_center)
        assert result is None, 'a press on another item is left to the normal click'
        shape.shape_edit_vertices = False
        assert selected_vertex_indices(shape) == []
        assert not bpy.ops.kanvas.delete_shape_vertices.poll()

        # A click on empty canvas deselects the shape, which leaves the mode as before.
        shape.shape_edit_vertices = True
        helper, _ = press(-400.0, -400.0)
        assert not helper.vertex_box_inside
        release(helper, -400.0, -400.0)
        assert not shape.is_selected and gpu_shape.vertex_edit_shape(settings) is None

    print('VERTEX EDIT ADVANCED PASS')
finally:
    addon.unregister()
