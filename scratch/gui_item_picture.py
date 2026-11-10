"""The picture of one image item, on a real GPU: upright and at the image's own size
whatever its place, rotation and scale on the board; flips kept; full opacity; cropped
to what the mask shows; nothing on the board changed. Export Image > Image writes it,
and the board export can crop masked images too.

    blender --factory-startup -P scratch/gui_item_picture.py
Prints GUIPICTURE RESULT OK or FAIL. Needs a window (not -b).
"""

import os
import struct
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def red(pixel):
    return pixel[0] > 200 and pixel[1] < 40 and pixel[2] < 40 and pixel[3] > 250


def blue(pixel):
    return pixel[2] > 200 and pixel[0] < 40 and pixel[1] < 40 and pixel[3] > 250


def run():
    import numpy as np
    from k_tools_kanvas.utils import board_render as br
    from k_tools_kanvas.utils import item_picture as ip
    addon.register()
    window = bpy.context.window_manager.windows[0]
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI picture', 'KanvasNodeTree')
    space = area.spaces.active
    space.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    # 400 x 200: the left half red, the right half blue.
    image = bpy.data.images.new('halves', 400, 200, alpha=True)
    pixels = np.zeros((200, 400, 4), dtype=np.float32)
    pixels[:, :200] = (1, 0, 0, 1)
    pixels[:, 200:] = (0, 0, 1, 1)
    image.pixels.foreach_set(pixels.ravel())
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = image
    item.location = (300.0, 100.0)
    item.rotation = 30.0
    item.scale_master = 0.5
    item.shear_xy = (0.1, 0.0)
    item.opacity = 0.5
    item.is_selected = True
    settings.active_image_index = 0

    def photo():
        return next(i for i in settings.images if i.item_id == 'photo')

    # --- Upright, own size, full opacity -------------------------------------------
    picture = ip.render_item(settings, photo())
    check(picture.shape == (200, 400, 4), f'size {picture.shape}')
    check(red(picture[100, 100]), f'left is red {tuple(picture[100, 100])}')
    check(blue(picture[100, 300]), f'right is blue {tuple(picture[100, 300])}')
    check(picture[5, 5, 3] > 250 and picture[195, 395, 3] > 250,
          f'corners covered {tuple(picture[5, 5])} {tuple(picture[195, 395])}')
    check(photo().opacity == 0.5 and photo().is_selected and tuple(photo().location) == (300, 100),
          'the item is unchanged')
    half = ip.render_item(settings, photo(), scale=0.5)
    check(half.shape == (100, 200, 4), f'half size {half.shape}')
    # Keep Stretch and Shear: twice as wide, no shear -> 800 x 200, still upright.
    photo().shear_xy = (0.0, 0.0)
    photo().scale_xy = (2.0, 1.0)
    wide = ip.render_item(settings, photo(), keep_stretch=True)
    check(wide.shape == (200, 800, 4), f'stretched size {wide.shape}')
    check(red(wide[100, 300]) and blue(wide[100, 500]), 'stretched halves')
    check(ip.picture_size(photo(), keep_stretch=True) == (800, 200), 'stretched picture_size')
    check(ip.render_item(settings, photo()).shape == (200, 400, 4), 'stretch left out by default')
    # A shear makes a slanted picture: wider, with clear corners.
    photo().scale_xy = (1.0, 1.0)
    photo().shear_xy = (0.5, 0.0)
    slanted = ip.render_item(settings, photo(), keep_stretch=True)
    check(slanted.shape == (200, 500, 4), f'sheared size {slanted.shape}')
    check(slanted[2, 2, 3] == 0 and slanted[197, 2, 3] > 250,
          f'slanted corners {slanted[2, 2, 3]} {slanted[197, 2, 3]}')
    photo().shear_xy = (0.1, 0.0)

    # --- Flips: flip_h mirrors; a negative stretch with flip_h does not ----------------
    photo().flip_h = True
    picture = ip.render_item(settings, photo())
    check(blue(picture[100, 100]) and red(picture[100, 300]), 'flip_h mirrors')
    photo().scale_xy = (-1.0, 1.0)
    picture = ip.render_item(settings, photo())
    check(red(picture[100, 100]) and blue(picture[100, 300]), 'flip and negative stretch cancel')
    photo().flip_h = False
    photo().scale_xy = (1.0, 1.0)

    # --- Crop to the mask: the lower left quarter of the red half ----------------------
    polygon = photo().mask_polygons.add()
    for uv in ((0.1, 0.2), (0.4, 0.2), (0.4, 0.6), (0.1, 0.6)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    photo().mask_enabled = True
    picture = ip.render_item(settings, photo())
    height, width = picture.shape[:2]
    check(120 <= width <= 126 and 80 <= height <= 86, f'cropped size {width} x {height}')
    check(red(picture[height // 2, width // 2]), f'cropped middle {tuple(picture[height // 2, width // 2])}')
    alpha = picture[..., 3]
    check(alpha[:, :1].max() > 0 and alpha[:, -1:].max() > 0
          and alpha[:1].max() > 0 and alpha[-1:].max() > 0, 'no empty border after the crop')
    whole = ip.render_item(settings, photo(), crop_to_mask=False)
    check(whole.shape == (200, 400, 4) and whole[100, 300, 3] == 0,
          f'uncropped keeps the hidden part transparent {whole.shape}')
    # The canvas rectangle of the selection shrinks with the crop.
    full_rect = br.board_rect(settings, 'SELECTION')
    crop_rect = br.board_rect(settings, 'SELECTION', crop_to_mask=True)
    check((crop_rect[2] - crop_rect[0]) < 0.5 * (full_rect[2] - full_rect[0]),
          f'board crop {crop_rect} inside {full_rect}')
    board = br.render(settings, crop_rect, 1.0, only=br.selection_contents(settings))
    # The board keeps the item's opacity (0.5), as on the canvas.
    check(120 <= board[..., 3].max() <= 135, f'the cropped board picture shows the image ({board[..., 3].max()})')

    # --- A mask that hides everything ---------------------------------------------------
    photo().mask_polygons.clear()
    try:
        ip.render_item(settings, photo())
        check(False, 'an empty mask should refuse')
    except ValueError:
        pass
    photo().mask_enabled = False

    # --- Export Image > Image -----------------------------------------------------------
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, 'photo.png')
    with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
        result = bpy.ops.kanvas.export_board_image(filepath=path, scope='IMAGE', margin=0)
    check(result == {'FINISHED'}, f'export {result}')
    with open(path, 'rb') as handle:
        header = handle.read(24)
    size = struct.unpack('>II', header[16:24])
    check(size == (400, 200), f'exported size {size}')
    print(f'GUIPICTURE cropped {width} x {height}')


def tick():
    try:
        run()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    print('GUIPICTURE RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(tick, first_interval=1.0)
