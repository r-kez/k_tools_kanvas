"""Check board-wide selection shortcuts and tree isolation in Blender."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators import ops_modal
from k_tools_kanvas.ui.selection_panel import KANVAS_PT_SelectionPanel


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Select shortcut board', 'KanvasNodeTree')
    other = bpy.data.node_groups.new('Other board', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = tree.kanvas_settings

    for kind in ('IMAGE', 'TEXT', 'FRAME', 'IMAGE'):
        item = settings.images.add()
        item.item_type = kind
    settings.images[0].image_data = bpy.data.images.new('Select test', 4, 4)
    settings.images[3].show_in_editor = False
    settings.arrows.add()
    other.kanvas_settings.images.add().item_type = 'TEXT'

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert ops_modal.KANVAS_OT_Interact.poll(bpy.context)
        assert ops_modal._select_canvas_items(settings)
        assert [item.is_selected for item in settings.images] == [True, True, True, False]
        assert settings.arrows[0].is_selected
        assert settings.active_image_index == 0
        assert settings.active_arrow_index == -1
        assert not ops_modal._select_canvas_items(settings)

        assert ops_modal._select_canvas_items(settings, invert=True)
        assert not any(item.is_selected for item in settings.images)
        assert not settings.arrows[0].is_selected
        assert settings.active_image_index == -1
        assert settings.active_arrow_index == -1
        assert ops_modal._select_canvas_items(settings, invert=True)
        assert [item.is_selected for item in settings.images] == [True, True, True, False]
        assert settings.arrows[0].is_selected
        assert not other.kanvas_settings.images[0].is_selected

        assert KANVAS_PT_SelectionPanel.poll(bpy.context)
        ops_modal._select_canvas_items(settings, invert=True)
        labels = []
        panel = SimpleNamespace(layout=SimpleNamespace(
            label=lambda **kwargs: labels.append(kwargs['text'])))
        KANVAS_PT_SelectionPanel.draw(panel, bpy.context)
        assert labels == ['Nothing selected'], labels
        settings.active_arrow_index = 0
        labels.clear()
        KANVAS_PT_SelectionPanel.draw(panel, bpy.context)
        assert labels == ['Arrow selected'], labels

        keyconfig = bpy.context.window_manager.keyconfigs.addon
        km = keyconfig.keymaps['Node Editor']
        bindings = {(item.properties.action, item.type, item.ctrl)
                    for item in km.keymap_items if item.idname == 'kanvas.interact'}
        assert ('SELECT_ALL', 'A', True) in bindings
        assert ('SELECT_INVERT', 'I', True) in bindings

    print('SELECT SHORTCUTS PASS')
finally:
    addon.unregister()
