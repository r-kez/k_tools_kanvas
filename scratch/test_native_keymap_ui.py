"""Check that Kanvas preferences expose Blender's effective editable keymap."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas import keymap


addon.register()
try:
    wm = bpy.context.window_manager
    bindings = list(keymap.iter_ui_bindings(wm))
    actions = {item.properties.action for _, _, _, item in bindings
               if item.idname == 'kanvas.interact'}
    assert {'MOVE', 'ROTATE', 'SCALE', 'RESET_MOVE', 'RESET_ROTATE',
            'RESET_SCALE', 'RENAME', 'MASK'} <= actions, actions
    mask = next(item for _, _, _, item in bindings
                if item.idname == 'kanvas.interact' and item.properties.action == 'MASK')
    assert mask.type == 'M' and not mask.shift and not mask.ctrl and not mask.alt
    move = next(item for _, _, _, item in bindings
                if item.idname == 'kanvas.interact' and item.properties.action == 'MOVE')
    assert move.type == 'G' and not move.alt
    move.type = 'H'
    wm.keyconfigs.update()
    changed = next(item for _, _, _, item in keymap.iter_ui_bindings(wm)
                   if item.idname == 'kanvas.interact' and item.properties.action == 'MOVE')
    assert changed.type == 'H'
    keymap.rebuild()
    restored = next(item for _, _, _, item in keymap.iter_ui_bindings(wm)
                    if item.idname == 'kanvas.interact' and item.properties.action == 'MOVE')
    assert restored.type == 'H', restored.type
    addon.unregister()
    addon.register()
    reloaded = next(item for _, _, _, item in keymap.iter_ui_bindings(wm)
                    if item.idname == 'kanvas.interact' and item.properties.action == 'MOVE')
    assert reloaded.type == 'H', reloaded.type
    print('NATIVE KEYMAP UI PASS')
finally:
    addon.unregister()
    assert not keymap._items
