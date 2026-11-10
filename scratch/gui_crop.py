"""Fit Bounds to Mask on a real GPU: the cropped image is drawn exactly as before (the same
pixels at the same place), its selection outline hugs the crop and no longer the whole
image, the whole image shows faintly while the mask is edited (and the outline stays on the
crop), the exported picture of the board has no transparent margin, a live reference in the
3D View has the crop's proportions, and Reset Bounds brings the whole size back.

    blender --factory-startup -P scratch/gui_crop.py
Prints GUICROP RESULT OK or FAIL. Needs a window (not -b).
"""

import os
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []
state = {}


def check(condition, message):
    if not condition:
        errors.append(message)


def settings():
    return state['tree'].kanvas_settings


def photo():
    return next(i for i in settings().images if i.item_id == 'photo')


def override():
    return bpy.context.temp_override(window=state['window'], area=state['kanvas'],
                                     region=state['region'], space_data=state['space'])


def setup():
    import numpy as np
    addon.register()
    window = bpy.context.window_manager.windows[0]
    areas = sorted(window.screen.areas, key=lambda a: a.width * a.height, reverse=True)
    view3d = next(a for a in areas if a.type == 'VIEW_3D')
    kanvas = next(a for a in areas if a != view3d and a.width * a.height > 40000)
    kanvas.type = 'NODE_EDITOR'
    kanvas.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI crop', 'KanvasNodeTree')
    space = kanvas.spaces.active
    space.node_tree = tree
    region = next(r for r in kanvas.regions if r.type == 'WINDOW')
    state.update(window=window, kanvas=kanvas, view3d=view3d, tree=tree, space=space,
                 region=region)
    # 400 x 200: red on the left half, blue on the right, so a crop shows what it should.
    image = bpy.data.images.new('photo', 400, 200, alpha=True)
    pixels = np.zeros((200, 400, 4), dtype=np.float32)
    pixels[:, :200] = (1, 0, 0, 1)
    pixels[:, 200:] = (0, 0, 1, 1)
    image.pixels.foreach_set(pixels.ravel())
    item = settings().images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = image
    item.is_selected = True
    settings().active_image_index = 0
    polygon = item.mask_polygons.add()
    for uv in ((0.1, 0.3), (0.5, 0.3), (0.5, 0.9), (0.1, 0.9)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    item.mask_enabled = True
    with override():
        bpy.ops.kanvas.focus_selection()
    for obj in list(bpy.context.scene.objects):
        obj.hide_viewport = True


def shot(name):
    import numpy as np
    window, kanvas = state['window'], state['kanvas']
    path = os.path.join(tempfile.gettempdir(), f'kanvas_crop_{name}.png')
    with bpy.context.temp_override(window=window, area=kanvas):
        bpy.ops.screen.screenshot_area(filepath=path)
    image = bpy.data.images.load(path, check_existing=False)
    width, height = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(height, width, 4)
    bpy.data.images.remove(image)
    region = state['region']
    x0, y0 = region.x - kanvas.x, region.y - kanvas.y
    return pixels[y0:y0 + region.height, x0:x0 + region.width]


def bbox(mask):
    import numpy as np
    ys, xs = np.nonzero(mask)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if xs.size else None


def red(p):
    return (p[..., 0] > 0.9) & (p[..., 1] < 0.1) & (p[..., 2] < 0.1)


def cyan(p):
    return (p[..., 0] < 0.3) & (p[..., 1] > 0.7) & (p[..., 2] > 0.9)


def around(uv, radius=14):
    """Boolean mask of the region pixels within `radius` of an image point."""
    import numpy as np
    from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv
    point = image_point_from_uv(photo(), uv)
    x, y = state['region'].view2d.view_to_region(point[0], point[1], clip=False)
    ys, xs = np.mgrid[0:state['region'].height, 0:state['region'].width]
    return (abs(xs - x) < radius) & (abs(ys - y) < radius)


def background_near(pixels):
    """The canvas next to the image, beside the dotted grid: its mean color."""
    return pixels[around((-0.1, 0.5), 10)][..., :3].mean(axis=0)


def step_before():
    photo().is_selected = False       # without the outline, which covers the edge pixels
    from k_tools_kanvas.utils.item_geometry import item_bounds
    state['whole'] = item_bounds(photo())


def step_before_plain():
    pixels = shot('before')
    state['red_before'] = int(red(pixels).sum())
    state['red_box_before'] = bbox(red(pixels))
    check(state['red_before'] > 500, f'the masked image is drawn ({state["red_before"]} red pixels)')
    photo().is_selected = True


def step_before_selected():
    pixels = shot('before_selected')
    # Its outline is the whole image's: at the bottom left corner of the image.
    check(int((cyan(pixels) & around((0.0, 0.0))).sum()) > 5, 'the outline is on the whole image')
    with override():
        result = bpy.ops.kanvas.fit_bounds_to_mask()
    check(result == {'FINISHED'} and photo().crop_enabled, f'fitted {result}')
    rect = tuple(photo().crop_uv)
    check(all(abs(a - b) < 0.02 for a, b in zip(rect, (0.1, 0.3, 0.5, 0.9))), f'the crop is the mask {rect}')
    state['rect'] = rect


def step_cropped_selected():
    from k_tools_kanvas.utils.item_geometry import item_bounds
    pixels = shot('cropped_selected')
    check(int((cyan(pixels) & around((0.0, 0.0))).sum()) == 0, 'no outline on the old corner')
    rect = state['rect']
    check(int((cyan(pixels) & around((rect[0], rect[1]))).sum()) > 5, 'the outline is on the crop')
    check(int((cyan(pixels) & around((rect[2], rect[3]))).sum()) > 5, 'on every corner of the crop')
    box = item_bounds(photo())
    whole = state['whole']
    check((box[2] - box[0]) < 0.5 * (whole[2] - whole[0]) and (box[3] - box[1]) < 0.7 * (whole[3] - whole[1]),
          f'the box is the crop {box} inside {whole}')
    photo().is_selected = False


def step_cropped_plain():
    pixels = shot('cropped')
    red_now = int(red(pixels).sum())
    check(abs(red_now - state['red_before']) <= 0.01 * state['red_before'] + 10,
          f'the same picture before and after ({state["red_before"]} -> {red_now}), '
          f'red box {state["red_box_before"]} -> {bbox(red(pixels))}')
    check(bbox(red(pixels)) == state['red_box_before'], 'in the same place')
    photo().mask_editing = True       # the faint image of the editor, without the outline


def step_editing():
    import numpy as np
    pixels = shot('editing')
    faint = pixels[around((0.05, 0.5), 10)][..., :3].mean(axis=0)
    background = background_near(pixels)
    check(float(np.abs(faint - background).max()) > 0.03,
          f'the whole image shows while the mask is edited {faint} vs {background}')
    check(photo().crop_enabled, 'the crop is kept while editing')
    photo().mask_editing = False


def step_after_editing():
    import numpy as np
    from k_tools_kanvas.utils import board_render as br
    pixels = shot('after_editing')
    faint = pixels[around((0.05, 0.5), 10)][..., :3].mean(axis=0)
    background = background_near(pixels)
    check(float(np.abs(faint - background).max()) < 0.015,
          f'the crop hides the rest again {faint} vs {background}')
    # The exported board picture has no transparent margin around the visible image.
    rect = br.board_rect(settings(), 'ALL')
    picture = br.render(settings(), rect, 1.0)
    check(picture.shape == (120, 160, 4), f'the picture is the crop {picture.shape}')
    edges = (picture[0, :, 3], picture[-1, :, 3], picture[:, 0, 3], picture[:, -1, 3])
    check(all(int(edge.min()) > 250 for edge in edges), 'no transparent margin on any side')
    check(tuple(picture[60, 20][:3]) == (255, 0, 0), f'red where it should be {tuple(picture[60, 20])}')
    # Export Image > Image: the picture of the item is the crop too.
    from k_tools_kanvas.utils import item_picture as ip
    check(ip.picture_size(photo(), 1.0, False) == (160, 120), f'item picture {ip.picture_size(photo(), 1.0, False)}')
    # Send to 3D View, cropped to the mask as it is by default: the crop's proportions.
    scene = bpy.context.scene
    photo().is_selected = True
    with override():
        result = bpy.ops.kanvas.add_3d_reference('EXEC_DEFAULT', size=4.0)
    check(result == {'FINISHED'}, f'sent {result}')
    entry = scene.kanvas_references[0]
    check(tuple(entry.object.data.size) == (1024, 768), f'placeholder {tuple(entry.object.data.size)}')
    # Without Crop to Mask the reference shows the item's own crop.
    entry.crop_to_mask = False
    photo().is_selected = True


def step_reference_crop():
    entry = bpy.context.scene.kanvas_references[0]
    check(tuple(entry.object.data.size) == (1024, 768), f'the item crop is the base {tuple(entry.object.data.size)}')
    with override():
        result = bpy.ops.kanvas.reset_bounds()
    check(result == {'FINISHED'} and not photo().crop_enabled, f'reset {result}')
    photo().is_selected = False


def step_reset():
    pixels = shot('reset')
    red_now = int(red(pixels).sum())
    check(abs(red_now - state['red_before']) <= 0.01 * state['red_before'] + 10,
          f'reset gives the same picture ({state["red_before"]} -> {red_now})')
    entry = bpy.context.scene.kanvas_references[0]
    check(tuple(entry.object.data.size) == (1024, 512),
          f'the reference follows the whole image again: {tuple(entry.object.data.size)}')
    photo().is_selected = True


def step_reset_outline():
    pixels = shot('reset_selected')
    check(int((cyan(pixels) & around((0.0, 0.0))).sum()) > 5, 'the outline is on the whole image again')


STEPS = [setup, step_before, step_before_plain, step_before_selected, step_cropped_selected,
         step_cropped_plain, step_editing, step_after_editing, step_reference_crop, step_reset,
         step_reset_outline]


def tick():
    try:
        STEPS.pop(0)()
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        if STEPS:
            return 0.9
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    print('GUICROP RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
