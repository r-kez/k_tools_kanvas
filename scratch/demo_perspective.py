"""Makes screenshots of the perspective correction for a look: a synthetic photo of a
checkered sheet seen at an angle, first with its corners being edited, then straightened.

    blender --factory-startup -P scratch/demo_perspective.py -- <folder for the pictures>
Needs a window (not -b)."""
import os
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

OUT = Path(sys.argv[sys.argv.index('--') + 1]) if '--' in sys.argv else Path(tempfile.gettempdir())
state = {}


def photo():
    return state['tree'].kanvas_settings.images[0]


def override():
    return bpy.context.temp_override(window=state['window'], area=state['kanvas'],
                                     region=state['region'], space_data=state['space'])


def camera_quad(ratio, width, height, focal=900.0):
    """Where a sheet of the given proportions lands in a photo taken by a real (pinhole)
    camera looking at it from the side and from above."""
    import math
    ax, ay = math.radians(35), math.radians(-30)
    cx, sx, cy, sy = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay)
    rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    r = [[sum(ry[i][k] * rx[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    quad = []
    for x, y in ((-ratio / 2, -0.5), (ratio / 2, -0.5), (ratio / 2, 0.5), (-ratio / 2, 0.5)):
        cam = [r[i][0] * x + r[i][1] * y + [0.1, 0.0, 2.2][i] for i in range(3)]
        quad.append(((focal * cam[0] / cam[2] + width / 2) / width,
                     (focal * cam[1] / cam[2] + height / 2) / height))
    return quad


def make_photo():
    import numpy as np
    from k_tools_kanvas.utils import perspective as p
    width, height = 800, 600
    quad = camera_quad(297 / 210, width, height)
    forward = p.square_to_quad(quad)
    inverse = p.invert(forward)
    ys, xs = np.mgrid[0:height, 0:width]
    u, v = (xs + 0.5) / width, (ys + 0.5) / height
    a, b, c, d, e, f, g, h, i = inverse
    w = g * u + h * v + i
    ru, rv = (a * u + b * v + c) / w, (d * u + e * v + f) / w
    inside = (ru >= 0) & (ru <= 1) & (rv >= 0) & (rv <= 1)
    pixels = np.zeros((height, width, 4), dtype=np.float32)
    # The background: a warm wall gradient. The sheet: 14 x 10 squares and a thick border.
    pixels[..., 0] = 0.55 + 0.25 * u
    pixels[..., 1] = 0.45 + 0.20 * v
    pixels[..., 2] = 0.35
    pixels[..., 3] = 1
    cells = ((ru * 14).astype(int) + (rv * 10).astype(int)) % 2
    sheet = np.where(cells[..., None] == 0, np.array([0.95, 0.95, 0.9]), np.array([0.2, 0.35, 0.6]))
    border = (ru < 0.03) | (ru > 0.97) | (rv < 0.04) | (rv > 0.96)
    sheet = np.where(border[..., None], np.array([0.85, 0.15, 0.15]), sheet)
    top_row = rv > 0.9
    sheet = np.where((top_row & ~border)[..., None], np.array([0.15, 0.7, 0.3]), sheet)
    pixels[..., :3] = np.where(inside[..., None], sheet, pixels[..., :3])
    image = bpy.data.images.new('photo', width, height, alpha=True)
    image.pixels.foreach_set(pixels.ravel())
    return image, quad


def shot(name):
    path = str(OUT / f'perspective_{name}.png')
    with bpy.context.temp_override(window=state['window'], area=state['kanvas']):
        bpy.ops.screen.screenshot_area(filepath=path)
    print('SHOT', path)


def setup():
    addon.register()
    window = bpy.context.window_manager.windows[0]
    areas = sorted(window.screen.areas, key=lambda a: a.width * a.height, reverse=True)
    kanvas = areas[0]
    kanvas.type = 'NODE_EDITOR'
    kanvas.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Demo', 'KanvasNodeTree')
    space = kanvas.spaces.active
    space.node_tree = tree
    region = next(r for r in kanvas.regions if r.type == 'WINDOW')
    state.update(window=window, kanvas=kanvas, tree=tree, space=space, region=region)
    image, quad = make_photo()
    item = tree.kanvas_settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = image
    item.is_selected = True
    tree.kanvas_settings.active_image_index = 0
    item.persp_corners = [c for point in quad for c in point]
    item.persp_auto = True
    with override():
        bpy.ops.kanvas.focus_selection()
    bpy.context.window_manager.kanvas_tabs.image = 'PERSPECTIVE'
    item.persp_editing = True
    for region in kanvas.regions:
        if region.type == 'UI':
            pass


def step_editing():
    shot('1_editing')
    from k_tools_kanvas.utils import perspective as p
    print('ESTIMATE', p.estimated_ratio(photo()), 'expected 1.414')


def step_straighten():
    from k_tools_kanvas.utils import perspective as p
    p.set_straightened(photo(), True)
    with override():
        bpy.ops.kanvas.focus_selection()


def step_straight():
    shot('2_straightened')


STEPS = [setup, step_editing, step_straighten, step_straight]


def tick():
    try:
        STEPS.pop(0)()
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        if STEPS:
            return 1.2
    except Exception:
        import traceback
        traceback.print_exc()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
