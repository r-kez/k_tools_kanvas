"""Regression for the first drag versus dragging an already selected image."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.operators import ops_modal
from k_tools_kanvas.operators.gizmos import KANVAS_GGT_ImageGizmos
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers, KANVAS_OT_Interact


class TestInteract(KanvasInteractionHelpers):
    invoke = KANVAS_OT_Interact.invoke
    _begin_gesture = lambda self, context: {'RUNNING_MODAL'}


addon.register()
original_prefs = ops_modal.get_prefs
original_canvas_check = ops_modal._event_in_canvas
try:
    tree = bpy.data.node_groups.new('Selected image snap test', 'KanvasNodeTree')
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    ops_modal.get_prefs = lambda: SimpleNamespace(key_shear_mod='ALT')
    ops_modal._event_in_canvas = lambda context, event: True

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        settings = get_settings(bpy.context)
        bpy.context.tool_settings.use_snap_node = True
        settings.snap_images = True
        settings.snap_grid = False
        image = bpy.data.images.new('selected-snap-image', 40, 40)
        moving = settings.images.add()
        moving.name = 'moving'
        moving.image_data = image
        moving.location = (0, 0)
        reference = settings.images.add()
        reference.name = 'reference'
        reference.image_data = image
        reference.location = (100, 0)
        assert KANVAS_GGT_ImageGizmos.poll(bpy.context) is False

        rx, ry = region.view2d.view_to_region(0, 0, clip=False)
        event = SimpleNamespace(mouse_region_x=rx, mouse_region_y=ry,
                                shift=False, ctrl=False, alt=False,
                                type='LEFTMOUSE', value='PRESS')
        for already_selected in (False, True):
            moving.location = (0, 0)
            moving.is_selected = already_selected
            interact = TestInteract()
            interact.action = 'CLICK'
            assert interact.invoke(bpy.context, event) == {'RUNNING_MODAL'}
            assert interact.drag_mode == 'MOVE'
            interact._update_drag(bpy.context, 59.9, 0)
            assert abs(moving.location[0] - 60) < 0.001, (
                already_selected, tuple(moving.location))
            assert settings.show_snap_viz_x and settings.snap_viz_x == 80
            interact._stop_drag(bpy.context)

        print('Selected image snap checks passed')
finally:
    ops_modal.get_prefs = original_prefs
    ops_modal._event_in_canvas = original_canvas_check
    addon.unregister()
