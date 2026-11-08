"""Checks, in a real window, that the Kanvas Pen (Shift+P) and Polygon (Ctrl+P) items
come before Blender's own Node Editor items for the same keys.

    blender --factory-startup -P scratch/gui_pen_keymap_order.py
Prints KEYORDER RESULT OK or FAIL. The effective keymaps exist only with a window open.
"""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon


def report():
    addon.register()
    from k_tools_kanvas import keymap
    keymap.rebuild()
    bpy.context.window_manager.keyconfigs.update()
    km = bpy.context.window_manager.keyconfigs.user.keymaps.get('Node Editor')
    problems = []
    for label, modifier, mode in (('Shift+P', 'shift', 'PEN'), ('Ctrl+P', 'ctrl', 'POLYGON')):
        items = [(index, item) for index, item in enumerate(km.keymap_items)
                 if item.type == 'P' and item.value == 'PRESS' and getattr(item, modifier)
                 and not any(getattr(item, other) for other in ('shift', 'ctrl', 'alt')
                             if other != modifier) and item.active]
        ours = next((index for index, item in items if item.idname == 'kanvas.draw_polygon'
                     and item.properties.mode == mode), None)
        others = [(index, item.idname) for index, item in items
                  if item.idname != 'kanvas.draw_polygon']
        first_other = min((index for index, _ in others), default=None)
        ok = ours is not None and (first_other is None or ours < first_other)
        print(f'KEYORDER {label}: ours at {ours}, others {others} -> {"OK" if ok else "WRONG"}',
              flush=True)
        if not ok:
            problems.append(label)
    for key, shift, direction in (('PAGE_UP', False, 'UP'), ('PAGE_DOWN', False, 'DOWN'),
                                  ('PAGE_UP', True, 'TOP'), ('PAGE_DOWN', True, 'BOTTOM')):
        matches = [(index, item.idname) for index, item in enumerate(km.keymap_items)
                   if item.type == key and item.value == 'PRESS' and item.shift == shift
                   and not item.ctrl and not item.alt and item.active]
        ours = next((index for index, item in enumerate(km.keymap_items)
                     if item.idname == 'kanvas.move_in_stack'
                     and item.type == key and item.shift == shift
                     and item.properties.direction == direction), None)
        first_other = min((index for index, name in matches if name != 'kanvas.move_in_stack'),
                          default=None)
        ok = ours is not None and (first_other is None or ours < first_other)
        print(f'KEYORDER {key} shift={shift}: ours at {ours}, others {matches} -> '
              f'{"OK" if ok else "WRONG"}', flush=True)
        if not ok:
            problems.append(key)
    e_items = [(index, item.idname, getattr(item.properties, 'action', ''))
               for index, item in enumerate(km.keymap_items)
               if item.type == 'E' and item.value == 'PRESS' and not (item.shift or item.ctrl or item.alt)
               and item.active]
    ours = next((index for index, name, action in e_items
                 if name == 'kanvas.interact' and action == 'VERTEX_EDIT'), None)
    others = [entry for entry in e_items if entry[1] != 'kanvas.interact']
    ok = ours is not None and all(ours < index for index, _, _ in others)
    print(f'KEYORDER E: ours at {ours}, others {others} -> {"OK" if ok else "WRONG"}', flush=True)
    if not ok:
        problems.append('E')
    print('KEYORDER RESULT', 'OK' if not problems else 'FAIL ' + str(problems), flush=True)
    addon.unregister()
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(report, first_interval=1.0)
