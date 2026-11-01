"""Regression checks for Kanvas transform modifier gestures."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.operators.ops_modal import (
    KanvasInteractionHelpers, _apply_rotation_delta, _sync_modifiers,
)

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Transform modifiers', 'KanvasNodeTree')
    settings = area.spaces.active.edit_tree.kanvas_settings
    with bpy.context.temp_override(area=area, space_data=area.spaces.active):
        img = settings.images.add()
        img.item_type = 'IMAGE'
        img.image_data = bpy.data.images.new('Modifier test', 100, 100)
        img.is_selected = True
        settings.active_image_index = 0
        helper = KanvasInteractionHelpers()

        helper.start_drag(bpy.context, img, 'ROTATE', (100, 0))
        point = (100 * math.cos(math.radians(13)), 100 * math.sin(math.radians(13)))
        helper._update_drag(bpy.context, *point, ctrl=True)
        assert abs(img.rotation - 15) < 0.001, img.rotation
        helper._update_drag(bpy.context, *point, ctrl=True, shift=True)
        assert abs(img.rotation - 13) < 0.001, img.rotation
        point2 = (100 * math.cos(math.radians(23)), 100 * math.sin(math.radians(23)))
        helper._update_drag(bpy.context, *point2, ctrl=True, shift=True)
        assert abs(img.rotation - 14) < 0.001, img.rotation

        img.rotation = 0
        helper.start_drag(bpy.context, img, 'SCALE_U', (50, 50))
        helper._update_drag(bpy.context, 63, 63, ctrl=True)
        assert abs(img.scale_master - 1.3) < 0.001, img.scale_master

        other = settings.images.add()
        other.item_type = 'IMAGE'
        other.image_data = bpy.data.images.new('Modifier test 2', 80, 70)
        other.location = (240, 40)
        other.is_selected = True
        for mode in ('MOVE', 'SCALE_U', 'ROTATE'):
            before = [(tuple(item.location), tuple(item.scale_xy),
                       item.scale_master, item.rotation)
                      for item in (img, other)]
            if mode == 'MOVE':
                start, finish = (0, 0), (30, 25)
            else:
                helper.start_drag(bpy.context, img, mode, (0, 0))
                pivot = helper.selection_pivot
                helper._cancel_drag(bpy.context)
                start = (pivot[0] + 100, pivot[1])
                finish = ((pivot[0] + 130, pivot[1] + 30)
                          if mode == 'SCALE_U' else
                          (pivot[0], pivot[1] + 100))
            helper.start_drag(bpy.context, img, mode, start)
            helper._update_drag(bpy.context, *finish)
            assert any(tuple(item.location) != snapshot[0]
                       or item.scale_master != snapshot[2]
                       or item.rotation != snapshot[3]
                       for item, snapshot in zip((img, other), before)), mode
            helper._cancel_drag(bpy.context)
            after = [(tuple(item.location), tuple(item.scale_xy),
                      item.scale_master, item.rotation)
                     for item in (img, other)]
            assert after == before, (mode, after, before)

        state = SimpleNamespace(alt_is_held=False, shift_is_held=False, ctrl_is_held=False)
        event = SimpleNamespace(type='LEFT_ALT', value='PRESS', alt=False, shift=False, ctrl=False)
        _sync_modifiers(state, event)
        assert state.alt_is_held
        event.value = 'RELEASE'
        event.alt = True
        _sync_modifiers(state, event)
        assert not state.alt_is_held

        from k_tools_kanvas import keymap
        from k_tools_kanvas.utils.gpu import gpu_common
        original_get_prefs = gpu_common.get_prefs
        gpu_common.get_prefs = lambda: SimpleNamespace()
        try:
            keymap.rebuild()
            bindings = {(item.properties.action, item.type, item.shift, item.alt)
                        for _, item in keymap._items if item.idname == 'kanvas.interact'}
            for action, key in (('MOVE', 'G'), ('ROTATE', 'R'), ('SCALE', 'S')):
                assert (action, key, False, False) in bindings, (action, key)
            for action, key in (('RESET_MOVE', 'G'), ('RESET_ROTATE', 'R'),
                                ('RESET_SCALE', 'S')):
                assert (action, key, False, True) in bindings, (action, key)
            assert ('DUPLICATE', 'D', True, False) in bindings
            assert any(item.properties.action == 'MODIFIER' and item.type == 'LEFT_ALT'
                       and item.value == 'PRESS' for _, item in keymap._items)
            assert any(item.properties.action == 'MODIFIER' and item.type == 'LEFT_ALT'
                       and item.value == 'RELEASE' for _, item in keymap._items)
        finally:
            keymap.unregister()
            gpu_common.get_prefs = original_get_prefs
        assert _apply_rotation_delta(13, ctrl=True) == 15
        assert _apply_rotation_delta(13, ctrl=True, shift=True) == 13
        print('TRANSFORM MODIFIERS PASS')
finally:
    addon.unregister()
