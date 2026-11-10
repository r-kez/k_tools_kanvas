"""Kanvas overlays in the 3D View, on a real GPU: Send to 3D View as an Overlay lists a
live overlay; the 3D View shows the image cropped to its mask, at the computed place,
mirrored with Flip, see-through at half opacity, gone when hidden; an edit on the board
shows without any update; the rectangle maths (anchors, offset, camera fit, handle).

    blender --factory-startup -P scratch/gui_overlay_3d.py
Prints GUIOVERLAY RESULT OK or FAIL. Needs a window (not -b).
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


def red(pixel):
    return pixel[0] > 0.8 and pixel[1] < 0.15 and pixel[2] < 0.15


def blue(pixel):
    return pixel[2] > 0.8 and pixel[0] < 0.15 and pixel[1] < 0.15


def maths():
    from k_tools_kanvas.utils.overlay_3d import hit_part, overlay_rect
    check(overlay_rect(1000, 500, 2.0, 0.5, 'CENTER', (0, 0)) == (250.0, 125.0, 750.0, 375.0),
          'centered')
    check(overlay_rect(1000, 500, 2.0, 0.5, 'TOP_RIGHT', (-10, -20)) == (490.0, 230.0, 990.0, 480.0),
          'top right with offset')
    check(overlay_rect(1000, 500, 1.0, 0.2, 'BOTTOM_LEFT', (0, 0)) == (0.0, 0.0, 100.0, 100.0),
          'bottom left')
    check(overlay_rect(1000, 500, 1.0, 9.0, 'CENTER', (0, 0), frame=(100, 50, 500, 250))
          == (200.0, 50.0, 400.0, 250.0), 'fitted in a wide camera frame')
    rect = (100, 100, 300, 200)
    check(hit_part(rect, (300, 200)) == 'SCALE' and hit_part(rect, (150, 150)) == 'MOVE'
          and hit_part(rect, (50, 50)) is None, 'hit parts')


def setup():
    import numpy as np
    addon.register()
    maths()
    window = bpy.context.window_manager.windows[0]
    areas = sorted(window.screen.areas, key=lambda a: a.width * a.height, reverse=True)
    view3d = next(a for a in areas if a.type == 'VIEW_3D')
    kanvas = next(a for a in areas if a != view3d and a.width * a.height > 40000)
    kanvas.type = 'NODE_EDITOR'
    kanvas.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI overlay', 'KanvasNodeTree')
    kanvas.spaces.active.node_tree = tree
    settings = tree.kanvas_settings
    # 400 x 200, left half red, right half blue; the mask shows the left 3/4.
    image = bpy.data.images.new('halves', 400, 200, alpha=True)
    pixels = np.zeros((200, 400, 4), dtype=np.float32)
    pixels[:, :200] = (1, 0, 0, 1)
    pixels[:, 200:] = (0, 0, 1, 1)
    pixels[:20, :] = (128 / 255, 128 / 255, 128 / 255, 1)   # a mid grey strip at the bottom
    image.pixels.foreach_set(pixels.ravel())
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = image
    polygon = item.mask_polygons.add()
    for uv in ((0.0, 0.0), (0.75, 0.0), (0.75, 1.0), (0.0, 1.0)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    item.mask_enabled = True
    item.is_selected = True
    settings.active_image_index = 0
    region = next(r for r in kanvas.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, area=kanvas, region=region,
                                   space_data=kanvas.spaces.active):
        result = bpy.ops.kanvas.add_3d_reference('EXEC_DEFAULT', kind='OVERLAY',
                                                 overlay_opacity=1.0, overlay_size=0.5)
    scene = bpy.context.scene
    check(result == {'FINISHED'} and len(scene.kanvas_references) == 1
          and scene.kanvas_references[0].kind == 'OVERLAY', f'overlay added {result}')
    check(not bpy.ops.kanvas.update_3d_reference.poll(), 'no Update for a live overlay')
    # A plain dark background: hide the default objects and grid.
    for obj in scene.objects:
        obj.hide_viewport = True
    space = view3d.spaces.active
    space.overlay.show_overlays = False
    # The splash screen covers the middle of the window: keep to the corners.
    entry = scene.kanvas_references[0]
    entry.anchor, entry.offset = 'BOTTOM_LEFT', (40.0, 40.0)
    state.update(window=window, view3d=view3d, tree=tree)


def capture(name):
    """The 3D View's WINDOW region as an array (rows from the bottom), RGB 0..1."""
    import numpy as np
    window, view3d = state['window'], state['view3d']
    path = os.path.join(tempfile.gettempdir(), f'kanvas_overlay_{name}.png')
    with bpy.context.temp_override(window=window, area=view3d):
        bpy.ops.screen.screenshot_area(filepath=path)
    shot = bpy.data.images.load(path, check_existing=False)
    width, height = shot.size
    pixels = np.array(shot.pixels[:], dtype=np.float32).reshape(height, width, 4)
    bpy.data.images.remove(shot)
    region = next(r for r in view3d.regions if r.type == 'WINDOW')
    x0, y0 = region.x - view3d.x, region.y - view3d.y
    return pixels[y0:y0 + region.height, x0:x0 + region.width], region


def expected_rect(region):
    """Where the overlay is drawn, in region pixels, and a check that it is placed in the
    area: the toolbar's region overlap does not move it."""
    from k_tools_kanvas.utils.overlay_3d import entry_layout, overlay_rect
    view3d = state['view3d']
    entry = bpy.context.scene.kanvas_references[0]
    with bpy.context.temp_override(window=state['window'], area=view3d, region=region,
                                   space_data=view3d.spaces.active):
        rect = entry_layout(bpy.context, entry)[1]
    dx, dy = region.x - view3d.x, region.y - view3d.y
    in_area = overlay_rect(view3d.width, view3d.height, 300 / 200, entry.size, entry.anchor,
                           entry.offset)
    check(all(abs(a - (b - d)) < 1e-3 for a, b, d in zip(rect, in_area, (dx, dy, dx, dy))),
          f'placed in the area {rect} {in_area}')
    return rect


def at(pixels, rect, fx, fy):
    left, bottom, right, top = rect
    return pixels[int(bottom + (top - bottom) * fy), int(left + (right - left) * fx)]


def step_plain():
    pixels, region = capture('plain')
    rect = expected_rect(region)
    # The crop shows 300 x 200: 2/3 of the width red, 1/3 blue.
    check(red(at(pixels, rect, 0.3, 0.5)), f'left red {at(pixels, rect, 0.3, 0.5)}')
    check(blue(at(pixels, rect, 0.85, 0.5)), f'right blue {at(pixels, rect, 0.85, 0.5)}')
    grey = at(pixels, rect, 0.3, 0.04)
    check(abs(grey[0] - 128 / 255) < 0.03, f'mid grey as on the board, not washed {grey}')
    outside = pixels[int((rect[1] + rect[3]) / 2), max(0, int(rect[0]) - 20)]
    check(not red(outside) and not blue(outside), f'nothing left of the overlay {outside}')
    entry = bpy.context.scene.kanvas_references[0]
    entry.flip_h = True
    entry.anchor, entry.offset = 'TOP_LEFT', (30.0, -30.0)


def step_flipped():
    pixels, region = capture('flipped')
    rect = expected_rect(region)
    check(blue(at(pixels, rect, 0.15, 0.5)) and red(at(pixels, rect, 0.7, 0.5)),
          f'flipped and moved {at(pixels, rect, 0.15, 0.5)} {at(pixels, rect, 0.7, 0.5)}')
    entry = bpy.context.scene.kanvas_references[0]
    entry.flip_h = False
    entry.opacity = 0.5
    # A board edit, with no update: the image turns grey.
    item = state['tree'].kanvas_settings.images[0]
    item.saturation = 0.0


def step_live():
    pixels, region = capture('live')
    rect = expected_rect(region)
    pixel = at(pixels, rect, 0.3, 0.5)
    check(abs(pixel[0] - pixel[1]) < 0.08 and abs(pixel[1] - pixel[2]) < 0.08,
          f'grey after the board edit {pixel}')
    background = pixels[5, 5]
    check(abs(pixel[0] - background[0]) > 0.03, 'half opacity still shows')
    bpy.context.scene.kanvas_overlays_hidden = True


def step_hidden():
    pixels, region = capture('hidden')
    rect = expected_rect(region)
    pixel = at(pixels, rect, 0.3, 0.5)
    background = pixels[5, 5]
    check(abs(pixel[0] - background[0]) < 0.02 and abs(pixel[2] - background[2]) < 0.02,
          f'hidden {pixel} vs {background}')
    # Remove: the entry goes, nothing else to delete.
    bpy.context.scene.kanvas_overlays_hidden = False
    bpy.context.scene.kanvas_reference_index = 0
    result = bpy.ops.kanvas.remove_3d_reference()
    check(result == {'FINISHED'} and not bpy.context.scene.kanvas_references, f'removed {result}')


STEPS = [setup, step_plain, step_flipped, step_live, step_hidden]


def tick():
    try:
        STEPS.pop(0)()
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        if STEPS:
            return 0.6
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    print('GUIOVERLAY RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
