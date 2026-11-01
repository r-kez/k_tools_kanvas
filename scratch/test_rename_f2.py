"""Quick rename smoke test for Blender background mode."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Rename test', 'KanvasNodeTree')
    settings = area.spaces.active.edit_tree.kanvas_settings
    with bpy.context.temp_override(area=area, space_data=area.spaces.active):
        image = settings.images.add()
        image.item_type = 'IMAGE'
        image.name = 'Original'
        image.is_selected = True
        settings.active_image_index = 0
        assert bpy.ops.kanvas.rename_item.poll()
        assert bpy.ops.kanvas.rename_item(new_name='Renamed image') == {'FINISHED'}
        assert image.name == 'Renamed image'

        frame = settings.images.add()
        frame.item_type = 'FRAME'
        frame.frame_node_name = 'rename_test_frame'
        frame.name = 'Old frame'
        image.is_selected = False
        frame.is_selected = True
        settings.active_image_index = 1
        assert bpy.ops.kanvas.rename_item(new_name='New frame') == {'FINISHED'}
        assert frame.name == 'New frame'
        assert frame.frame_node_name == 'rename_test_frame'

        frame.is_selected = False
        assert not bpy.ops.kanvas.rename_item.poll()

        from k_tools_kanvas import keymap
        from k_tools_kanvas.utils.gpu import gpu_common
        old_get_prefs = gpu_common.get_prefs
        gpu_common.get_prefs = lambda: SimpleNamespace()
        try:
            keymap.rebuild()
            assert any(item.properties.action == 'RENAME' and item.type == 'F2'
                       for _, item in keymap._items)
        finally:
            keymap.unregister()
            gpu_common.get_prefs = old_get_prefs
        print('RENAME F2 PASS')
finally:
    addon.unregister()
