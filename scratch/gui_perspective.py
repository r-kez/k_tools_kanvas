"""Perspective correction on a real GPU: the board draws the straightened rectangle (a plain
photo with a gradient is read by the shader through the homography and every sample matches
the same point of the plain picture), the outside of the rectangle is clear, flips mirror it,
and the mask and color markup (stored in the UV of the photo) follow the correction.

    blender --factory-startup -P scratch/gui_perspective.py
Prints GUIPERSPECTIVE RESULT OK or FAIL. Needs a window (not -b).
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
    from k_tools_kanvas.utils import board_render as br
    from k_tools_kanvas.utils import item_picture as ip
    from k_tools_kanvas.utils import item_crop as c
    from k_tools_kanvas.utils import perspective as p
    from k_tools_kanvas.utils.item_geometry import item_bounds
    addon.register()
    window = bpy.context.window_manager.windows[0]
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI perspective', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    settings = tree.kanvas_settings

    # 200 x 200: red grows to the right, green upward, so every sample says where it came from.
    image = bpy.data.images.new('photo', 200, 200, alpha=True)
    pixels = np.zeros((200, 200, 4), dtype=np.float32)
    pixels[..., 0] = (np.arange(200)[None, :] + 0.5) / 200
    pixels[..., 1] = (np.arange(200)[:, None] + 0.5) / 200
    pixels[..., 3] = 1
    image.pixels.foreach_set(pixels.ravel())
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = image
    item.use_color_correction = False
    item.is_selected = True
    settings.active_image_index = 0

    def photo():
        return settings.images[0]

    def board():
        rect = item_bounds(photo())
        return rect, br.render(settings, rect, 1.0, only=br.selection_contents(settings))

    def sample(picture, rect, point):
        x = int(point[0] - rect[0])
        y = int(rect[3] - point[1])
        return tuple(int(v) for v in picture[min(max(y, 0), picture.shape[0] - 1),
                                              min(max(x, 0), picture.shape[1] - 1)])

    plain_rect, plain = board()
    check(plain.shape[:2] == (200, 200), f'plain {plain.shape}')

    photo().persp_corners = (0.15, 0.2, 0.85, 0.1, 0.75, 0.9, 0.25, 0.8)
    photo().persp_auto = False
    photo().persp_aspect = 1.0
    check(p.set_straightened(photo(), True), 'straightened')
    box = c.corrected(photo())
    rect, corrected = board()
    check(abs(corrected.shape[1] - box.width) <= 1 and abs(corrected.shape[0] - box.height) <= 1,
          f'picture is the rectangle {corrected.shape} {box.width:.1f} {box.height:.1f}')
    centre = ((rect[0] + rect[2]) * 0.5, (rect[1] + rect[3]) * 0.5)
    worst = 0
    for fu, fv in ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9), (0.5, 0.5), (0.3, 0.7), (0.7, 0.3)):
        got = sample(corrected, rect, (rect[0] + fu * (rect[2] - rect[0]),
                                       rect[1] + fv * (rect[3] - rect[1])))
        u, v = p.apply(box.forward, (fu, fv))
        want = sample(plain, plain_rect, (plain_rect[0] + u * 200, plain_rect[1] + v * 200))   # the same point of the plain picture
        worst = max(worst, abs(got[0] - want[0]), abs(got[1] - want[1]))
        check(got[3] > 250, f'covered at {fu, fv}: {got}')
    check(worst < 6, f'the shader reads the homography (worst {worst:.1f})')

    # A flip mirrors the straightened picture.
    photo().flip_h = True
    rect, flipped = board()
    left = sample(flipped, rect, (rect[0] + 0.1 * (rect[2] - rect[0]), centre[1]))
    photo().flip_h = False
    rect, normal = board()
    right = sample(normal, rect, (rect[0] + 0.9 * (rect[2] - rect[0]), centre[1]))
    check(abs(left[0] - right[0]) < 12 and abs(left[1] - right[1]) < 12,
          f'flipped left {left} is the right of the normal {right}')

    # The mask is in the photo UV: hiding the left part of the photo hides it in the rectangle.
    polygon = photo().mask_polygons.add()
    for uv in ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    photo().mask_enabled = True
    rect, masked = board()
    inside_left = sample(masked, rect, (rect[0] + 0.15 * (rect[2] - rect[0]),
                                        rect[1] + 0.5 * (rect[3] - rect[1])))
    inside_right = sample(masked, rect, (rect[0] + 0.85 * (rect[2] - rect[0]),
                                         rect[1] + 0.5 * (rect[3] - rect[1])))
    check(inside_left[3] < 10 and inside_right[3] > 240, f'mask follows {inside_left} {inside_right}')

    # The picture of the item (Export Image, 3D references) is the straightened rectangle.
    photo().mask_enabled = False
    picture = ip.render_item(settings, photo())
    check(abs(picture.shape[1] - box.width) <= 1 and abs(picture.shape[0] - box.height) <= 1,
          f'item picture {picture.shape}')
    got = tuple(int(v) for v in picture[int(0.5 * picture.shape[0]), int(0.2 * picture.shape[1])])
    u, v = p.apply(box.forward, (0.2, 0.5))
    want = sample(plain, plain_rect, (plain_rect[0] + u * 200, plain_rect[1] + v * 200))
    check(abs(got[0] - want[0]) < 8 and abs(got[1] - want[1]) < 8, f'picture sample {got} {want}')
    photo().mask_enabled = True

    # Editing the corners of a straightened image and leaving the edit: the picture is the
    # rectangle of the new corners, not a stretched one.
    photo().mask_enabled = False
    photo().persp_auto = True
    wm = bpy.context.window_manager
    wm.kanvas_tabs.image = 'PERSPECTIVE'
    photo().persp_editing = True
    check(c.corrected(photo()) is None, 'the photo shows while editing')
    photo().persp_corners = (0.2, 0.15, 0.8, 0.2, 0.75, 0.85, 0.22, 0.8)
    photo().persp_editing = False
    box = c.corrected(photo())
    rect, after = board()
    print('DBG box', box.width, box.height, 'picture', after.shape, 'ratio', p.ratio_of(photo()), 'bounds', rect, 'scale', tuple(photo().scale_xy), photo().scale_master)
    check(abs(after.shape[1] - box.width) <= 2 and abs(after.shape[0] - box.height) <= 2,
          f'picture {after.shape} is the new rectangle {box.width:.1f} x {box.height:.1f}')
    worst = 0
    for fu, fv in ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9), (0.5, 0.5)):
        got = sample(after, rect, (rect[0] + fu * (rect[2] - rect[0]), rect[1] + fv * (rect[3] - rect[1])))
        u, v = p.apply(box.forward, (fu, fv))
        want = sample(plain, plain_rect, (plain_rect[0] + u * 200, plain_rect[1] + v * 200))
        worst = max(worst, abs(got[0] - want[0]), abs(got[1] - want[1]))
    check(worst < 6, f'the new corners are read right (worst {worst})')
    wm.kanvas_tabs.image = 'MAIN'

    # Show Whole Image: all of the photo straightened, clear where there is no photo.
    photo().persp_auto = False
    photo().persp_aspect = 1.0
    photo().persp_corners = (0.15, 0.2, 0.85, 0.1, 0.75, 0.9, 0.25, 0.8)
    p.set_whole(photo(), True)
    whole = c.corrected(photo())
    rect, everything = board()
    w, h = c.box_size(photo(), 200, 200)
    check(abs(everything.shape[1] - w) <= 2 and abs(everything.shape[0] - h) <= 2,
          f'whole picture {everything.shape} {w:.1f} x {h:.1f}')
    u0, v0, u1, v1 = whole.bounds

    def at_plane(picture, fu, fv):
        return sample(picture, rect, (rect[0] + (fu - u0) / (u1 - u0) * (rect[2] - rect[0]),
                                      rect[1] + (fv - v0) / (v1 - v0) * (rect[3] - rect[1])))

    worst = 0
    for fu, fv in ((0.2, 0.2), (0.8, 0.8), (0.5, 0.5)):
        got = at_plane(everything, fu, fv)
        u, v = p.apply(whole.forward, (fu, fv))
        want = sample(plain, plain_rect, (plain_rect[0] + u * 200, plain_rect[1] + v * 200))
        worst = max(worst, abs(got[0] - want[0]), abs(got[1] - want[1]))
    check(worst < 6, f'the whole picture reads the same homography (worst {worst})')
    clear = [at_plane(everything, fu, fv)[3] for fu, fv in ((u0 + 0.01, v1 - 0.01), (u1 - 0.01, v0 + 0.01),
                                                            (u0 + 0.01, v0 + 0.01), (u1 - 0.01, v1 - 0.01))]
    check(min(clear) < 10, f'a corner of the box is clear beyond the photo {clear}')
    p.set_whole(photo(), False)

    # Show Original gives the photo back where it was.
    photo().mask_enabled = False
    check(p.set_straightened(photo(), False), 'back to the photo')
    rect, again = board()
    check(again.shape == plain.shape and abs(again.astype(int) - plain.astype(int)).max() < 3,
          'the original is the same picture')


def finish():
    print('GUIPERSPECTIVE RESULT', 'OK' if not errors else 'FAIL')
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
