"""Operators edit only the board currently selected in the Node Editor."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    first = bpy.data.node_groups.new('First board', 'KanvasNodeTree')
    second = bpy.data.node_groups.new('Second board', 'KanvasNodeTree')
    region = next(region for region in area.regions if region.type == 'WINDOW')

    area.spaces.active.node_tree = first
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_text(location=(10, 20)) == {'FINISHED'}
    assert len(first.kanvas_settings.images) == 1
    assert len(second.kanvas_settings.images) == 0

    area.spaces.active.node_tree = second
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_text(location=(100, 200)) == {'FINISHED'}
    assert len(first.kanvas_settings.images) == 1
    assert len(second.kanvas_settings.images) == 1
    assert tuple(first.kanvas_settings.images[0].location) == (10, 20)
    assert tuple(second.kanvas_settings.images[0].location) == (100, 200)

    area.spaces.active.node_tree = first
    assert len(area.spaces.active.edit_tree.kanvas_settings.images) == 1
    print('tree operator isolation check passed')
finally:
    addon.unregister()
