"""Check color dialog operator writes the selected region in this build."""

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
    tree = bpy.data.node_groups.new('Color popup test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    window_region = next(region for region in area.regions if region.type == 'WINDOW')
    item = tree.kanvas_settings.images.add()
    item.item_id = 'color-popup-image'
    item.item_type = 'IMAGE'
    item.image_data = bpy.data.images.new('Color popup source', 32, 32)
    item.is_selected = True
    tree.kanvas_settings.active_image_index = 0
    color = item.markup_regions.add()
    color.region_id = 'popup-region'
    color.name = 'Popup Region'
    with bpy.context.temp_override(area=area, region=window_region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.edit_markup_color_popup.poll()
        result = bpy.ops.kanvas.edit_markup_color_popup(
            'EXEC_DEFAULT', item_id=item.item_id, region_id=color.region_id,
            color=(0.15, 0.35, 0.75))
        assert result == {'FINISHED'}, result
        assert all(abs(actual - expected) < 1e-6
                   for actual, expected in zip(color.color, (0.15, 0.35, 0.75)))
    print('COLOR DIALOG OPERATOR PASS')
finally:
    addon.unregister()
