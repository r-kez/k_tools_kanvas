"""The one-channel mask texture draws right on a real GPU, and Mask Resolution keeps
its edge sharp: a 2000 x 1000 image with its left half revealed, drawn at full size,
has a soft edge several pixels wide at 512 and about one pixel at 'IMAGE'.

    blender --factory-startup -P scratch/gui_mask_resolution.py
Prints GUIMASK RESULT OK or FAIL. Needs a window (not -b).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def run():
    import numpy as np
    from k_tools_kanvas.utils import board_render as br
    from k_tools_kanvas.utils.gpu import gpu_common, gpu_mask
    addon.register()
    prefs = SimpleNamespace(mask_resolution='512')
    # Only the mask size reads the stand-in preference; the rest of the drawing keeps
    # whatever preferences exist.
    original = gpu_mask.display_side

    def display_side(image):
        saved = gpu_common.get_prefs
        gpu_common.get_prefs = lambda: prefs
        try:
            return original(image)
        finally:
            gpu_common.get_prefs = saved
    gpu_mask.display_side = display_side
    tree = bpy.data.node_groups.new('GUI mask', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    image = bpy.data.images.new('white', 2000, 1000)
    image.pixels.foreach_set(np.ones(2000 * 1000 * 4, dtype=np.float32))
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = image
    item.location = (1000.0, 500.0)
    polygon = item.mask_polygons.add()
    for uv in ((0.0, 0.0), (0.5003, 0.0), (0.5003, 1.0), (0.0, 1.0)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    item.mask_enabled = True
    rect = (0.0, 0.0, 2000.0, 1000.0)

    def edge_width():
        gpu_mask.clear_mask_cache()
        picture = br.render(settings, rect, 1.0)
        row = picture[500, :, 3].astype(int)
        check(row[100] > 250, f'left half shows ({row[100]})')
        check(row[1900] < 5, f'right half is hidden ({row[1900]})')
        return int(((row > 10) & (row < 245)).sum())

    prefs.mask_resolution = '512'
    soft = edge_width()
    prefs.mask_resolution = 'IMAGE'
    sharp = edge_width()
    check(sharp <= 2, f'edge at full resolution is {sharp} px wide')
    check(soft >= 3 and soft > sharp, f'edge at 512 is {soft} px wide (full: {sharp})')
    key = (tree.as_pointer(), 'photo')
    cached = gpu_mask._mask_cache.get(key)
    check(cached is not None and cached['pixels'].shape == (1000, 2000),
          f'full-size mask texture {None if cached is None else cached["pixels"].shape}')
    print(f'GUIMASK edge 512: {soft} px, Image: {sharp} px')

    # Color markup (now an 8-bit texture) still paints its color.
    item.mask_enabled = False
    region = item.markup_regions.add()
    region.region_id, region.name = 'red', 'Red'
    region.color, region.opacity, region.visible = (1.0, 0.0, 0.0), 1.0, True
    painted = region.polygons.add()
    for uv in ((0.6, 0.2), (0.9, 0.2), (0.9, 0.8), (0.6, 0.8)):
        painted.vertices.add().uv = uv
    painted.sequence = 1
    item.markup_visible = True
    picture = br.render(settings, rect, 1.0)
    red = picture[500, 1500]
    check(red[0] > 200 and red[1] < 60 and red[2] < 60, f'markup color {tuple(red)}')
    check(tuple(picture[500, 300][:3]) == (255, 255, 255), 'the rest of the image untouched')


def tick():
    try:
        run()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    print('GUIMASK RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(tick, first_interval=1.0)
