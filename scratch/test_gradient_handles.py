"""Gradient handles on the canvas: when they show (one gradient shape selected, the
sidebar open on the Fill tab), the hit test, dragging the start, the end and the line,
Ctrl snapping to the box, Shift 15° steps, Esc, an undo step, and the box handles
giving way to them."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import shape_gradient as sg


def close(a, b, tol=1e-3):
    return all(abs(x - y) < tol for x, y in zip(a, b))


# --- Pure geometry ---------------------------------------------------------------------
assert sg.hit_handle((0, 0), (100, 0), (2, 1), 5) == 'start'
assert sg.hit_handle((0, 0), (100, 0), (99, -2), 5) == 'end'
assert sg.hit_handle((0, 0), (100, 0), (50, 2), 5) == 'line'
assert sg.hit_handle((0, 0), (100, 0), (50, 20), 5) is None
assert sg.hit_handle((0, 0), (100, 0), (130, 0), 5) is None
assert close(sg.constrain_angle((0, 0), (10, 1)), (math.hypot(10, 1), 0.0))
assert close(sg.constrain_angle((0, 0), (10, 9)), (math.hypot(10, 9) * math.cos(math.radians(45)),
                                                   math.hypot(10, 9) * math.sin(math.radians(45))))
assert sg.nearest_box_point((0.4, -0.1)) == (0.5, 0.0)
markers = sg.stop_markers((0, 0), (100, 0), [(1, 0, 0, 1, 0.25)])
assert close(markers[0][0], (25, 0)) and markers[0][1] == (1, 0, 0, 1)

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Gradient handles', 'KanvasNodeTree')
    space = area.spaces.active
    space.node_tree = tree
    space.show_region_ui = True
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    wm = bpy.context.window_manager

    with bpy.context.temp_override(area=area, region=region, space_data=space):
        context = bpy.context
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 50.0),
                                           size=(200.0, 100.0)) == {'FINISHED'}
        shape = settings.images[-1]
        settings.active_image_index = len(settings.images) - 1
        shape.is_selected = True
        wm.kanvas_tabs.shape = 'FILL'

        # --- When they show ----------------------------------------------------------
        assert sg.gradient_edit_shape(settings) is None, 'a solid fill has no handles'
        shape.shape_fill_type = 'LINEAR'
        assert sg.gradient_edit_shape(settings) == shape
        wm.kanvas_tabs.shape = 'LINE'
        assert sg.gradient_edit_shape(settings) is None, 'only on the Fill tab'
        wm.kanvas_tabs.shape = 'FILL'
        # (Inside temp_override Blender ignores hiding the sidebar: ask with a context.)
        from types import SimpleNamespace
        closed = SimpleNamespace(window_manager=wm, space_data=SimpleNamespace(show_region_ui=False))
        assert sg.gradient_edit_shape(settings, closed) is None, 'only with the sidebar open'
        shape.shape_edit_vertices = True
        assert sg.gradient_edit_shape(settings) is None, 'Edit Vertices has its own handles'
        shape.shape_edit_vertices = False
        wm.kanvas_tabs.shape = 'FILL'   # Edit Vertices opened the Shape tab

        from k_tools_kanvas.operators.ops_modal import (KanvasInteractionHelpers,
                                                        _undo_content_signature)
        helper = KanvasInteractionHelpers()
        assert helper._get_gizmo_under_mouse(context, (0.0, 50.0)) == -1, \
            'the box handles give way to the gradient handles'

        def gesture(at):
            g = KanvasInteractionHelpers()
            g._begin_gesture = lambda context: {'RUNNING_MODAL'}
            assert g._start_gradient_gesture(context, settings, at, 1.0) == {'RUNNING_MODAL'}
            return g

        # The canvas points: start (0, 50), end (200, 50).
        assert helper._start_gradient_gesture(context, settings, (100.0, 90.0), 1.0) is None, \
            'a press away from the handles is an ordinary click'

        # --- Drag the end, with Shift ------------------------------------------------
        before = _undo_content_signature(settings)
        g = gesture((200.0, 50.0))
        g._update_drag(context, 150.0, 101.0, shift=True)   # 45 degrees from the start
        start, end = sg.canvas_points(shape)
        assert close(start, (0.0, 50.0))
        assert abs(math.degrees(math.atan2(end[1] - start[1], end[0] - start[0])) - 15 * round(
            math.degrees(math.atan2(51, 150)) / 15)) < 1e-3, end
        g._stop_drag(context)
        assert _undo_content_signature(settings) != before, 'the drag is an undo step'

        # --- Esc puts it back ----------------------------------------------------------
        kept = (tuple(shape.shape_gradient_start), tuple(shape.shape_gradient_end))
        g = gesture(sg.canvas_points(shape)[0])
        g._update_drag(context, 60.0, 60.0)
        assert not close(tuple(shape.shape_gradient_start), kept[0])
        g._cancel_drag(context)
        assert close(tuple(shape.shape_gradient_start), kept[0])

        # --- Ctrl snaps the start onto the box ----------------------------------------
        bpy.ops.kanvas.gradient_reset_points()
        g = gesture((0.0, 50.0))
        g._update_drag(context, 98.0, 47.0, ctrl=True)
        assert close(tuple(shape.shape_gradient_start), (0.0, 0.0)), 'onto the middle'
        g._stop_drag(context)

        # --- The line moves both -------------------------------------------------------
        bpy.ops.kanvas.gradient_reset_points()
        g = gesture((100.0, 50.0))
        g._update_drag(context, 100.0, 80.0)
        start, end = sg.canvas_points(shape)
        assert close(start, (0.0, 80.0)) and close(end, (200.0, 80.0)), (start, end)
        g._stop_drag(context)

        # --- A small move is a click: nothing changes -----------------------------------
        bpy.ops.kanvas.gradient_reset_points()
        g = gesture((0.0, 50.0))
        g._update_drag(context, 1.0, 50.5)
        assert close(tuple(shape.shape_gradient_start), (-0.5, 0.0))
        g._stop_drag(context)
    print('test_gradient_handles: OK')
finally:
    addon.unregister()
