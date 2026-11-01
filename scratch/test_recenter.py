"""Check empty and offscreen recenter behavior in Blender background mode."""

from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_focus import (
    expand_zoom_box_for_panels, hit_recenter_prompt, offscreen_target,
    recenter_prompt, usable_canvas_rect,
)
from k_tools_kanvas.operators.ops_modal import KANVAS_OT_Interact

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Recenter Test', 'KanvasNodeTree')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        settings = area.spaces.active.edit_tree.kanvas_settings
        assert offscreen_target(settings, (-100, -100, 100, 100)) is None
        assert recenter_prompt(settings, area, region) is None
        item = settings.images.add()
        item.item_type = 'TEXT'
        item.location = (2000, 1000)
        assert offscreen_target(settings, (-100, -100, 100, 100)) == (2000, 1000)
        assert offscreen_target(settings, (1800, 800, 2200, 1200)) is None
        prompt = recenter_prompt(settings, area, region)
        assert prompt is not None
        x0, y0, x1, y1 = prompt['bounds']
        assert hit_recenter_prompt(settings, area, region,
                                  ((x0 + x1) / 2, (y0 + y1) / 2))
        assert not hit_recenter_prompt(settings, area, region, (0, 0))
        mouse_x, mouse_y = (x0 + x1) / 2, (y0 + y1) / 2
        event = SimpleNamespace(mouse_region_x=mouse_x, mouse_region_y=mouse_y,
                                mouse_x=region.x + mouse_x,
                                mouse_y=region.y + mouse_y)
        gesture = SimpleNamespace(action='CLICK')
        assert KANVAS_OT_Interact.invoke(gesture, bpy.context, event) == {'CANCELLED'}
        assert recenter_prompt(settings, area, region) is None
        item.show_in_editor = False
        assert offscreen_target(settings, (-100, -100, 100, 100)) is None
        assert bpy.ops.kanvas.recenter() == {'FINISHED'}
    view = SimpleNamespace(region_to_view=lambda x, y: (x, y),
                           view_to_region=lambda x, y, clip=False: (x, y))
    canvas = SimpleNamespace(type='WINDOW', x=0, y=0, width=1000, height=600,
                             view2d=view)
    tools = SimpleNamespace(type='TOOLS', x=0, y=0, width=180, height=600)
    sidebar = SimpleNamespace(type='UI', x=740, y=0, width=260, height=600)
    mock_area = SimpleNamespace(regions=(canvas, tools, sidebar))
    assert usable_canvas_rect(mock_area, canvas) == (180, 0, 740, 600)
    expanded = expand_zoom_box_for_panels((200, 100, 800, 500),
                                          (180, 0, 740, 600), (1000, 600))
    assert expanded[0] < 200 and expanded[2] > 800
    assert expanded[1] == 100 and expanded[3] == 500
    item.show_in_editor = True
    item.location = (2000, 1000)
    prompt = recenter_prompt(settings, mock_area, canvas)
    assert prompt['direction'] == '→'
    assert prompt['bounds'] == (366, 272, 554, 328)
    assert hit_recenter_prompt(settings, mock_area, canvas, (460, 300))
    other_tree = bpy.data.node_groups.new('Empty Recenter Test', 'KanvasNodeTree')
    empty_settings = other_tree.kanvas_settings
    assert recenter_prompt(empty_settings, mock_area, canvas)['empty']
    assert recenter_prompt(empty_settings,
                           SimpleNamespace(regions=(canvas,)), canvas) is None
    panned_view = SimpleNamespace(region_to_view=lambda x, y: (x + 1000, y + 1000),
                                  view_to_region=lambda x, y, clip=False: (x - 1000, y - 1000))
    canvas.view2d = panned_view
    origin_prompt = recenter_prompt(empty_settings, mock_area, canvas)
    assert origin_prompt and origin_prompt['empty']
    assert hit_recenter_prompt(empty_settings, mock_area, canvas, (460, 300))
    print('RECENTER PASS')
finally:
    addon.unregister()
