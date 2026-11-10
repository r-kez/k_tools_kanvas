"""Live reference images on a real GPU: Send to 3D View (Live on, the default) makes an
image empty holding a transparent generated placeholder of the picture's proportions,
and Kanvas draws the picture on its plane with the board's exact colors; a board edit
shows without any update; a new mask resizes the placeholder; depth Default hides it
behind a cube in front, In Front draws over it, Background draws behind a cube that is
behind it; Only Axis Aligned hides it at an angle; Save as Image File and Make Live
switch it.

    blender --factory-startup -P scratch/gui_live_reference_3d.py
Prints GUILIVE RESULT OK or FAIL. Needs a window (not -b).
"""

import math
import os
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Euler, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []
state = {}


def check(condition, message):
    if not condition:
        errors.append(message)


def red(pixel):
    return pixel[0] > 0.85 and pixel[1] < 0.12 and pixel[2] < 0.12


def blue(pixel):
    return pixel[2] > 0.85 and pixel[0] < 0.12 and pixel[1] < 0.12


def setup():
    import numpy as np
    addon.register()
    window = bpy.context.window_manager.windows[0]
    areas = sorted(window.screen.areas, key=lambda a: a.width * a.height, reverse=True)
    view3d = next(a for a in areas if a.type == 'VIEW_3D')
    kanvas = next(a for a in areas if a != view3d and a.width * a.height > 40000)
    kanvas.type = 'NODE_EDITOR'
    kanvas.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI live', 'KanvasNodeTree')
    kanvas.spaces.active.node_tree = tree
    settings = tree.kanvas_settings
    image = bpy.data.images.new('halves', 400, 200, alpha=True)
    pixels = np.zeros((200, 400, 4), dtype=np.float32)
    pixels[:, :200] = (1, 0, 0, 1)
    pixels[:, 200:] = (0, 0, 1, 1)
    pixels[:40, :] = (128 / 255, 128 / 255, 128 / 255, 1)   # a mid grey strip at the bottom
    image.pixels.foreach_set(pixels.ravel())
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = image
    item.rotation = 25.0          # its turn on the board is left out
    polygon = item.mask_polygons.add()
    for uv in ((0.0, 0.0), (0.75, 0.0), (0.75, 1.0), (0.0, 1.0)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    item.mask_enabled = True
    item.is_selected = True
    settings.active_image_index = 0
    scene = bpy.context.scene
    for obj in list(scene.objects):
        obj.hide_viewport = True
    scene.cursor.location = (0.0, 0.0, 0.0)
    region = next(r for r in kanvas.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, area=kanvas, region=region,
                                   space_data=kanvas.spaces.active):
        result = bpy.ops.kanvas.add_3d_reference('EXEC_DEFAULT', size=2.0)
    check(result == {'FINISHED'}, f'added {result}')
    entry = scene.kanvas_references[0]
    obj = entry.object
    check(entry.live and obj.data.get('kanvas_placeholder'), 'a live reference with a placeholder')
    check(obj.data.source == 'GENERATED' and obj.data.packed_file is None
          and not obj.data.is_dirty, 'the placeholder is generated, not saved pixels')
    check(tuple(obj.data.size) == (1024, 683), f'placeholder proportions {tuple(obj.data.size)}')
    check(tuple(obj.data.generated_color) == (0.0, 0.0, 0.0, 0.0), 'transparent placeholder')
    check(not bpy.ops.kanvas.update_3d_reference.poll(), 'no Update for a live reference')
    # Front orthographic view; the splash screen covers the middle of the window.
    space = view3d.spaces.active
    space.overlay.show_floor = False
    space.overlay.show_axis_x = space.overlay.show_axis_y = False
    region_3d = space.region_3d
    region_3d.view_perspective = 'ORTHO'
    region_3d.view_rotation = Euler((math.radians(90), 0, 0)).to_quaternion()
    region_3d.view_location = (2.2, 0.0, 0.0)    # the plane left of the splash screen
    region_3d.view_distance = 7.0
    state.update(window=window, view3d=view3d, tree=tree, kanvas=kanvas)


def capture(name):
    import numpy as np
    window, view3d = state['window'], state['view3d']
    path = os.path.join(tempfile.gettempdir(), f'kanvas_live_{name}.png')
    with bpy.context.temp_override(window=window, area=view3d):
        bpy.ops.screen.screenshot_area(filepath=path)
    shot = bpy.data.images.load(path, check_existing=False)
    width, height = shot.size
    pixels = np.array(shot.pixels[:], dtype=np.float32).reshape(height, width, 4)
    bpy.data.images.remove(shot)
    region = next(r for r in view3d.regions if r.type == 'WINDOW')
    x0, y0 = region.x - view3d.x, region.y - view3d.y
    return pixels[y0:y0 + region.height, x0:x0 + region.width], region


def at(pixels, region, point):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    space = state['view3d'].spaces.active
    xy = location_3d_to_region_2d(region, space.region_3d, Vector(point))
    return pixels[int(xy.y), int(xy.x)]


# The plane: 2 m wide (x -1..1), 1.333 m high (z -0.667..0.667), at y = 0.
RED_POINT = (-0.4, 0.0, -0.2)       # 30% across: red
BLUE_POINT = (0.7, 0.0, -0.2)       # 85% across: blue


def step_colors():
    pixels, region = capture('colors')
    check(red(at(pixels, region, RED_POINT)), f'exact red {at(pixels, region, RED_POINT)}')
    check(blue(at(pixels, region, BLUE_POINT)), f'exact blue {at(pixels, region, BLUE_POINT)}')
    grey = at(pixels, region, (-0.4, 0.0, -0.6))       # in the bottom strip
    check(abs(grey[0] - 128 / 255) < 0.03, f'mid grey as on the board, not washed {grey}')
    background = at(pixels, region, (1.5, 0.0, -0.4))
    check(not red(background) and not blue(background), f'nothing past the crop {background}')
    # A cube in front of the red part.
    bpy.ops.mesh.primitive_cube_add(size=0.3, location=(-0.4, -1.0, -0.2))
    state['cube'] = bpy.context.active_object
    state['tree'].kanvas_settings.images[0].saturation = 0.0


def step_live_and_front():
    pixels, region = capture('live')
    pixel = at(pixels, region, BLUE_POINT)
    check(abs(pixel[0] - pixel[2]) < 0.05, f'grey after the board edit, no update {pixel}')
    state['tree'].kanvas_settings.images[0].saturation = 1.0
    covered = at(pixels, region, RED_POINT)
    state['covered'] = covered
    entry = bpy.context.scene.kanvas_references[0]
    entry.object.empty_image_depth = 'FRONT'


def step_in_front():
    pixels, region = capture('front')
    check(not red(state['covered']), f'Default: the cube in front hides it {state["covered"]}')
    check(red(at(pixels, region, RED_POINT)), f'In Front: over the cube {at(pixels, region, RED_POINT)}')
    entry = bpy.context.scene.kanvas_references[0]
    entry.object.empty_image_depth = 'BACK'
    state['cube'].location = (-0.4, 1.0, -0.2)     # now behind the plane


def step_background():
    pixels, region = capture('back')
    check(not red(at(pixels, region, RED_POINT)),
          f'Background: behind the cube behind it {at(pixels, region, RED_POINT)}')
    check(blue(at(pixels, region, BLUE_POINT)), f'Background still shows {at(pixels, region, BLUE_POINT)}')
    entry = bpy.context.scene.kanvas_references[0]
    entry.object.empty_image_depth = 'DEFAULT'
    state['cube'].hide_viewport = True
    # A mask showing the whole image: the placeholder follows (from the timer).
    item = state['tree'].kanvas_settings.images[0]
    for vertex, uv in zip(item.mask_polygons[0].vertices,
                          ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
        vertex.uv = uv
    item.mask_revision += 1
    # At an angle: Only Axis Aligned hides it (off by default, as in Blender).
    bpy.context.scene.kanvas_references[0].object.show_empty_image_only_axis_aligned = True
    region_3d = state['view3d'].spaces.active.region_3d
    region_3d.view_rotation = Euler((math.radians(80), 0, math.radians(10))).to_quaternion()


def step_angle():
    pixels, region = capture('angle')
    pixel = at(pixels, region, BLUE_POINT)
    check(not blue(pixel) and not red(pixel), f'hidden at an angle {pixel}')
    obj = bpy.context.scene.kanvas_references[0].object
    check(tuple(obj.data.size) == (1024, 512), f'placeholder follows the mask {tuple(obj.data.size)}')
    # Save as Image File, then Make Live again.
    bpy.context.scene.kanvas_reference_index = 0
    placeholder = obj.data.name
    result = bpy.ops.kanvas.bake_3d_reference()
    entry = bpy.context.scene.kanvas_references[0]
    check(result == {'FINISHED'} and not entry.live and entry.object.data.get('kanvas_reference')
          and placeholder not in bpy.data.images, f'saved as a file {result}')
    check(bpy.ops.kanvas.update_3d_reference.poll(), 'an image file can be updated')
    baked = entry.object.data.name
    result = bpy.ops.kanvas.make_3d_reference_live()
    entry = bpy.context.scene.kanvas_references[0]
    check(result == {'FINISHED'} and entry.live and entry.object.data.get('kanvas_placeholder')
          and baked not in bpy.data.images, f'live again {result}')
    result = bpy.ops.kanvas.remove_3d_reference()
    check(result == {'FINISHED'} and not any(i.get('kanvas_placeholder') for i in bpy.data.images),
          f'removed with its placeholder {result}')


STEPS = [setup, step_colors, step_live_and_front, step_in_front, step_background, step_angle]


def tick():
    try:
        STEPS.pop(0)()
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        if STEPS:
            return 0.7
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    print('GUILIVE RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
