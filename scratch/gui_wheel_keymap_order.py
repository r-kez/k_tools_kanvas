"""Checks, in a real window, that the add-on's wheel items are matched before Blender's.

    blender --factory-startup -P scratch/gui_wheel_keymap_order.py
The effective ("user") keymaps are only populated with a window open.
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
    user = bpy.context.window_manager.keyconfigs.user

    def first_index(km, predicate):
        for index, item in enumerate(km.keymap_items):
            if predicate(item):
                return index
        return None

    problems = []
    checks = (
        # keymap, our wheel modifiers, Blender's item that would otherwise win
        ('View2D', lambda i: i.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not (i.ctrl or i.shift or i.alt),
         lambda i: i.idname in {'view2d.zoom_in', 'view2d.zoom_out', 'view2d.scroll_up', 'view2d.scroll_down'}, 'plain wheel'),
        ('View2D', lambda i: i.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and i.ctrl,
         lambda i: i.idname in {'view2d.scroll_left', 'view2d.scroll_right'} and i.ctrl, 'Ctrl+wheel'),
        ('View2D', lambda i: i.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and i.shift,
         lambda i: i.idname in {'view2d.scroll_up', 'view2d.scroll_down'} and i.shift, 'Shift+wheel'),
        ('Frames', lambda i: i.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and i.alt,
         lambda i: i.idname == 'screen.frame_offset' and i.alt, 'Alt+wheel'),
    )
    for name, ours, theirs, label in checks:
        km = user.keymaps.get(name)
        if km is None:
            problems.append(f'{label}: keymap {name} missing')
            print(f'KMORDER {label}: keymap {name} missing', flush=True)
            continue
        mine = first_index(km, lambda i: i.idname == 'kanvas.interact' and ours(i))
        blender = first_index(km, theirs)
        status = 'OK' if mine is not None and (blender is None or mine < blender) else 'WRONG'
        if status != 'OK':
            problems.append(label)
        print(f'KMORDER {label:11s} in {name:8s}: ours at index {mine}, Blender at index {blender} -> {status}', flush=True)

    node = user.keymaps.get('Node Editor')
    leftover = [i.type for i in node.keymap_items if i.idname == 'kanvas.interact' and 'WHEEL' in i.type] if node else []
    print(f'KMORDER wheel items left in Node Editor keymap: {len(leftover)}', flush=True)
    print('KMORDER RESULT', 'OK' if not problems and not leftover else 'FAIL ' + str(problems), flush=True)
    addon.unregister()
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(lambda: report() or None, first_interval=1.5)
