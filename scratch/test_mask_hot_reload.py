"""A stale paint modal must not hand M to Blender's Mute Node after reload."""

from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas import keymap
from k_tools_kanvas.operators.ops_mask import _active_painters, clear_stale_paint_state


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Mask reload', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        image = settings.images.add()
        image.item_id = 'reload-image'
        image.item_type = 'IMAGE'
        image.image_data = bpy.data.images.new('Mask reload image', 32, 32)
        image.is_selected = True
        settings.active_image_index = 0
        assert bpy.ops.kanvas.interact.poll()
        image.mask_editing = True  # Simulate an invalidated modal after script reload.
        assert not bpy.ops.kanvas.interact.poll()
        addon.unregister()
        addon.register()
        addon._restore_loaded_frames()
        tree = bpy.data.node_groups['Mask reload']
        image = tree.kanvas_settings.images[0]
        assert bpy.ops.kanvas.interact.poll()
        assert bpy.ops.kanvas.paint_image_mask.poll()
        assert bpy.ops.kanvas.edit_color_markup.poll()
        tool_items = image.bl_rna.properties['mask_tool'].enum_items
        assert {entry.identifier for entry in tool_items} == {
            'BRUSH', 'POLYGON', 'RECTANGLE'}
        km = bpy.context.window_manager.keyconfigs.addon.keymaps['Node Editor']
        mask_bindings = [item for item in km.keymap_items
                         if item.idname == 'kanvas.interact'
                         and item.properties.action == 'MASK']
        assert len(mask_bindings) == 1 and mask_bindings[0].active
        keymap._items.clear()  # Simulate losing module-local handles on hot reload.
        keymap.rebuild()
        mask_bindings = [item for item in km.keymap_items
                         if item.idname == 'kanvas.interact'
                         and item.properties.action == 'MASK']
        assert len(mask_bindings) == 1
        state = {'tree': tree, 'item_id': image.item_id,
                 'editing_attr': 'mask_editing'}
        image.mask_editing = True
        _active_painters.append(state)
        clear_stale_paint_state(tree)
        assert image.mask_editing  # Deferred cleanup must spare a live modal.
        _active_painters.remove(state)
        clear_stale_paint_state(tree)
        assert not image.mask_editing
        for _ in range(3):
            addon.unregister()
            addon.register()
            addon._restore_loaded_frames()
            assert bpy.ops.kanvas.interact.poll()
            assert bpy.ops.kanvas.paint_image_mask.poll()
            assert bpy.ops.kanvas.edit_color_markup.poll()
            km = bpy.context.window_manager.keyconfigs.addon.keymaps['Node Editor']
            assert sum(1 for item in km.keymap_items
                       if item.idname == 'kanvas.interact'
                       and item.properties.action == 'MASK') == 1
    print('MASK HOT RELOAD PASS')
finally:
    addon.unregister()
