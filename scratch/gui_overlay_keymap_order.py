"""Checks, in a real window, which other keymap items want the overlay shortcuts' presses
(Alt + left, Alt + right, Alt + Shift + left, Alt + Home in the 3D View) and whether ours
come first in the 3D View keymap.

    blender --factory-startup -P scratch/gui_overlay_keymap_order.py
Prints OVERLAYKEYS lines. The effective keymaps exist only with a window open.
"""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

WANTED = (('WHEELUPMOUSE', False, True, 'OPACITY_UP'), ('LEFTMOUSE', False, True, 'MOVE'), ('RIGHTMOUSE', False, True, 'ROTATE'),
          ('LEFTMOUSE', True, True, 'SCALE'), ('HOME', False, True, 'RESET'))


def matches(item, key, shift, alt):
    ctrl = key.startswith('WHEEL')       # the opacity shortcut is Alt + Ctrl + wheel
    return (item.active and item.type == key and item.value in {'PRESS', 'ANY'}
            and item.shift == shift and item.alt == alt and item.ctrl == ctrl)


def report():
    addon.register()
    wm = bpy.context.window_manager
    wm.keyconfigs.update()
    user = wm.keyconfigs.user
    names = [km.name for km in user.keymaps if km.name.startswith('3D View')]
    bad = []
    for key, shift, alt, action in WANTED:
        for name in names:
            km = user.keymaps[name]
            hits = [(index, item.idname, getattr(item.properties, 'action', ''))
                    for index, item in enumerate(km.keymap_items) if matches(item, key, shift, alt)]
            if not hits:
                continue
            print(f'OVERLAYKEYS {action} in {name!r}: {hits}', flush=True)
            if name != '3D View':
                bad.append((action, name))
            else:
                ours = next((i for i, n, a in hits if n == 'kanvas.overlay_edit' and a == action),
                            None)
                first = min((i for i, n, _ in hits if n != 'kanvas.overlay_edit'), default=None)
                if ours is None or (first is not None and first < ours):
                    bad.append((action, 'order'))
    print('OVERLAYKEYS RESULT', 'OK' if not bad else f'CHECK {bad}', flush=True)
    addon.unregister()
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(report, first_interval=1.0)
