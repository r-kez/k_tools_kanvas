"""Sampling and Black and White on a real GPU: a two pixel image enlarged is hard at the
edge between the pixels with Nearest and smooth with Linear (and back, on the same texture);
Black and White gives equal channels, brighter for a red than its plain luma.

    blender --factory-startup -P scratch/gui_sampling.py
Prints GUISAMPLING RESULT OK or FAIL. Needs a window (not -b).
"""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def run():
    import numpy as np
    from k_tools_kanvas.utils import item_picture as ip
    addon.register()
    window = bpy.context.window_manager.windows[0]
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI sampling', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    settings = tree.kanvas_settings
    image = bpy.data.images.new('two', 2, 1, alpha=True)
    image.pixels.foreach_set(np.array([1, 0, 0, 1, 0, 0, 1, 1], dtype=np.float32))
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'two', 'Two'
    item.image_data = image
    item.is_selected = True
    settings.active_image_index = 0

    def render():
        return ip.render_item(settings, settings.images[0], scale=20.0)

    linear = render()
    check(linear.shape[1] == 40, f'size {linear.shape}')
    near_edge = linear[0, 18]
    check(near_edge[0] < 245 and near_edge[2] > 10, f'linear blends the pixels {tuple(near_edge)}')
    settings.images[0].sampling = 'NEAREST'
    hard = render()
    check(tuple(hard[0, 18][:3]) == (255, 0, 0) and tuple(hard[0, 21][:3]) == (0, 0, 255),
          f'nearest keeps hard pixels {tuple(hard[0, 18])} {tuple(hard[0, 21])}')
    settings.images[0].sampling = 'LINEAR'
    again = render()
    check(again[0, 18][2] > 10, f'linear again on the same texture {tuple(again[0, 18])}')

    settings.images[0].value_gray = True
    gray = render()[0, 5]
    check(gray[0] == gray[1] == gray[2], f'equal channels {tuple(gray)}')
    check(gray[0] > 80, f'a red is weighed in linear light, not 54 {tuple(gray)}')


def finish():
    print('GUISAMPLING RESULT', 'OK' if not errors else 'FAIL')
    for message in errors:
        print('  -', message)
    bpy.ops.wm.quit_blender()


def start():
    try:
        run()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(f'exception {exc}')
    finish()
    return None


bpy.app.timers.register(start, first_interval=1.0)
