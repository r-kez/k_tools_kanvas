"""A drag begun inside a frame body should select by box, not grab the frame."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
import k_tools_kanvas.operators.ops_modal as modal_module
from k_tools_kanvas.operators.ops_modal import KANVAS_OT_Interact, KanvasInteractionHelpers


class DummyInteraction(KanvasInteractionHelpers):
    action = 'CLICK'

    def _begin_gesture(self, context):
        return {'RUNNING_MODAL'}

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Body selection', 'KanvasNodeTree')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        settings = get_settings(bpy.context)
        point = region.view2d.region_to_view(region.width // 2, region.height // 2)
        frame = settings.images.add()
        frame.item_type = 'FRAME'
        frame.frame_node_name = 'body-hit-test'
        frame.name = 'Body'
        frame.location = (point[0] - 50, point[1] + 60)
        frame.frame_width = 120
        frame.frame_height = 130
        frame.auto_resize = False
        event = SimpleNamespace(type='LEFTMOUSE', value='PRESS', shift=False,
                                alt=False, ctrl=False,
                                mouse_region_x=region.width // 2,
                                mouse_region_y=region.height // 2)
        operator = DummyInteraction()
        assert operator._frame_hit(bpy.context, point)[2] == 'BODY'
        original_prefs = modal_module.get_prefs
        modal_module.get_prefs = lambda: SimpleNamespace(
            box_select_alt_drag=True, box_select_on_drag=True)
        try:
            result = KANVAS_OT_Interact.invoke(operator, bpy.context, event)
        finally:
            modal_module.get_prefs = original_prefs
        assert result == {'RUNNING_MODAL'}
        assert operator.drag_mode == 'PENDING_BOX'
        assert not frame.is_selected
    print('Frame body box selection check passed')
finally:
    addon.unregister()
