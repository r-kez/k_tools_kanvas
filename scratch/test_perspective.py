"""Perspective correction, headless: the homography and its inverse, the estimate of the
rectangle proportions from a synthetic camera, the validity of the corners, and an image
item with its perspective corrected: its box is the rectangle, image and canvas points agree
both ways, flips mirror it, the corners land on the corners of the box, and crops and edits
switch it off."""
import math
import random
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    from k_tools_kanvas.utils import item_crop as c
    from k_tools_kanvas.utils import perspective as p
    from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv, image_uv_at
    from k_tools_kanvas.utils.item_geometry import item_bounds

    def close(a, b, tolerance=1e-4):
        return all(abs(x - y) < tolerance for x, y in zip(a, b))

    # --- Homographies -------------------------------------------------------------------
    quad = [(0.1, 0.1), (0.9, 0.2), (0.8, 0.9), (0.2, 0.7)]
    forward = p.square_to_quad(quad)
    for corner, point in zip(((0, 0), (1, 0), (1, 1), (0, 1)), quad):
        assert close(p.apply(forward, corner), point, 1e-9)
    back = p.invert(forward)
    for probe in ((0.3, 0.6), (0.9, 0.1), (0.5, 0.5)):
        assert close(p.apply(back, p.apply(forward, probe)), probe, 1e-9)
    assert p.invert((1, 2, 3, 2, 4, 6, 0, 0, 1)) is None, 'singular matrix'

    # --- Validity ---------------------------------------------------------------------------
    assert p.is_valid_quad(quad, 1000, 800)
    assert not p.is_valid_quad([(0.1, 0.1), (0.9, 0.9), (0.9, 0.1), (0.1, 0.9)], 1000, 800), 'crossed'
    assert not p.is_valid_quad([(0.1, 0.1), (0.5, 0.1), (0.9, 0.1), (0.5, 0.9)], 1000, 800), 'three in a line'
    assert not p.is_valid_quad([(0.5, 0.5)] * 4, 1000, 800), 'a point'
    assert p.is_valid_quad(quad[::-1], 1000, 800), 'either winding is fine'

    # --- The proportions come out of a synthetic camera ---------------------------------------
    def rotation(ax, ay):
        cx, sx, cy, sy = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay)
        rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
        ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
        return [[sum(ry[i][k] * rx[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

    random.seed(7)
    worst, tried = 0.0, 0
    for _ in range(100):
        ratio, focal = random.uniform(0.5, 2.5), random.uniform(500, 1500)
        r = rotation(random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6))
        t = (random.uniform(-0.2, 0.2), random.uniform(-0.2, 0.2), random.uniform(2.5, 4.0))
        points = []
        for x, y in ((-ratio / 2, -0.5), (ratio / 2, -0.5), (ratio / 2, 0.5), (-ratio / 2, 0.5)):
            cam = [r[i][0] * x + r[i][1] * y + t[i] for i in range(3)]
            points.append(((focal * cam[0] / cam[2] + 500) / 1000, (focal * cam[1] / cam[2] + 400) / 800))
        if not p.is_valid_quad(points, 1000, 800):
            continue
        tried += 1
        worst = max(worst, abs(p.estimate_ratio(points, 1000, 800) / ratio - 1))
    assert tried > 50 and worst < 1e-6, (tried, worst)
    # A straight-on rectangle has no perspective: its own proportions.
    flat = [(0.2, 0.25), (0.8, 0.25), (0.8, 0.75), (0.2, 0.75)]
    assert abs(p.estimate_ratio(flat, 1000, 800) - (600 / 400)) < 1e-6

    # --- An image item ------------------------------------------------------------------------
    tree = bpy.data.node_groups.new('Persp', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = bpy.data.images.new('photo', 1000, 800)
    item.location = (300.0, 100.0)
    item.rotation = 20.0
    item.scale_master = 0.5
    item.persp_corners = (0.1, 0.1, 0.9, 0.2, 0.8, 0.9, 0.2, 0.7)
    item.persp_auto = False
    item.persp_aspect = 1.5
    assert c.corrected(item) is None and c.box_size(item, 1000, 800) == (1000, 800)

    item.persp_enabled = True
    box = c.corrected(item)
    assert box is not None and abs(box.width / box.height - 1.5) < 1e-6
    assert c.box_size(item, 1000, 800) == (box.width, box.height)
    assert c.pivot_uv(item) == (0.5, 0.5) and c.shown_crop(item) == c.FULL
    centre = image_point_from_uv(item, p.apply(box.forward, (0.5, 0.5)))
    assert close(centre, item.location, 1e-3), 'the middle of the rectangle sits at the location'
    bounds = item_bounds(item)
    width, height = box.width * item.scale_master, box.height * item.scale_master
    angle = math.radians(item.rotation)
    half_x = (abs(math.cos(angle)) * width + abs(math.sin(angle)) * height) * 0.5
    half_y = (abs(math.sin(angle)) * width + abs(math.cos(angle)) * height) * 0.5
    assert close(bounds, (300 - half_x, 100 - half_y, 300 + half_x, 100 + half_y), 1e-3), bounds
    # Image points and canvas points agree both ways, for every flip.
    for flip_h, flip_v in ((False, False), (True, False), (False, True), (True, True)):
        item.flip_h, item.flip_v = flip_h, flip_v
        for fu, fv in ((0.1, 0.1), (0.9, 0.9), (0.5, 0.5), (0.2, 0.8), (0.0, 0.0), (1.0, 1.0)):
            uv = p.apply(box.forward, (fu, fv))
            point = image_point_from_uv(item, uv)
            back = image_uv_at(item, point)
            assert back is not None and math.dist(uv, back) < 1e-6, (flip_h, flip_v, fu, fv, back)
        outside = image_point_from_uv(item, p.apply(box.forward, (1.3, 0.5)))
        assert image_uv_at(item, outside) is None, 'outside the rectangle is outside the item'
    # A flip puts the same image point on the other side of the middle.
    item.flip_h, item.flip_v = False, False
    side_uv = p.apply(box.forward, (0.0, 0.5))
    left = image_point_from_uv(item, side_uv)
    item.flip_h = True
    right = image_point_from_uv(item, side_uv)
    assert math.dist(left, item.location) > 1.0 and close(
        ((left[0] + right[0]) * 0.5, (left[1] + right[1]) * 0.5), item.location, 1e-3)
    item.flip_h = False

    # --- Editing shows the photo as it is -----------------------------------------------------------
    item.mask_editing = True
    assert c.corrected(item) is None and c.box_size(item, 1000, 800) == (1000, 800)
    item.mask_editing = False
    wm = bpy.context.window_manager
    wm.kanvas_tabs.image = 'PERSPECTIVE'
    item.persp_editing = True
    assert p.editing(item) and c.corrected(item) is None
    wm.kanvas_tabs.image = 'MAIN'
    assert not p.editing(item) and c.corrected(item) is not None, 'closing the tab ends the edit'
    item.persp_editing = False

    # --- Auto proportions follow the corners; taking them over keeps the number -----------------
    item.persp_auto = True
    item.persp_corners = (0.2, 0.25, 0.8, 0.25, 0.8, 0.75, 0.2, 0.75)
    shape = c.corrected(item)
    assert abs(p.ratio_of(item) - 1.5) < 1e-6 and abs(shape.width / shape.height - 1.5) < 1e-6
    item.persp_auto = False
    assert abs(item.persp_aspect - 1.5) < 1e-6, 'the estimate becomes the number'

    # --- Bad corners show the plain image ---------------------------------------------------------------
    item.persp_corners = (0.1, 0.1, 0.9, 0.9, 0.9, 0.1, 0.1, 0.9)
    assert c.corrected(item) is None and c.box_size(item, 1000, 800) == (1000, 800)
    item.persp_corners = (0.2, 0.25, 0.8, 0.25, 0.8, 0.75, 0.2, 0.75)

    # --- Crop and perspective exclude each other -----------------------------------------------------
    assert not c.set_crop(item, (0.1, 0.1, 0.5, 0.5)) and not item.crop_enabled
    item.persp_enabled = False
    assert c.set_crop(item, (0.1, 0.1, 0.5, 0.5))
    item.persp_enabled = True
    assert c.corrected(item) is None, 'a cropped item is not straightened'
    c.set_crop(item, None)
    assert c.corrected(item) is not None
    # --- The picture of a straightened item is its rectangle ----------------------------------------
    from types import SimpleNamespace
    from k_tools_kanvas.utils import item_picture as ip
    from k_tools_kanvas.utils import overlay_3d
    assert p.set_straightened(item, True)
    shape = c.corrected(item)
    size = ip.picture_size(item)
    assert size is not None and abs(size[0] - shape.width) <= 2 and abs(size[1] - shape.height) <= 2, size
    assert ip.picture_uv_rect(item, True) == (0.0, 0.0, 1.0, 1.0)
    corners, uvs, bounds = ip.picture_quad(item)
    assert close((bounds[2] - bounds[0], bounds[3] - bounds[1]), (shape.width, shape.height), 1e-3)
    entry = SimpleNamespace(crop_to_mask=True, keep_stretch=False, flip_h=False)
    uv_rect, aspect, quad = overlay_3d.shown_part(item, entry)
    assert abs(aspect - shape.width / shape.height) < 1e-6 and quad is None, aspect

    # --- A straightened item moves nothing when it is switched on and off -----------------------------
    item.persp_enabled = False
    item.location = (300.0, 100.0)
    item.rotation, item.scale_master = 33.0, 0.7
    point = image_point_from_uv(item, p.apply(p.build_for(item).forward, (0.5, 0.5)))
    assert p.set_straightened(item, True)
    assert close(item.location, point, 1e-3), 'the middle of the rectangle stays where it was in the photo'
    assert p.set_straightened(item, False)
    assert close(image_point_from_uv(item, p.apply(p.build_for(item).forward, (0.5, 0.5))), point, 1e-3),         'and it stays there when the photo comes back'

    # --- Marks measure the straightened rectangle -------------------------------------------------------
    from k_tools_kanvas.utils import measure as mm
    item.persp_enabled = False
    assert p.set_straightened(item, True)
    shape = c.corrected(item)
    across = mm.add_mark(item, 'LINE', p.apply(shape.forward, (0.0, 0.5)), p.apply(shape.forward, (1.0, 0.5)))
    assert abs(mm.mark_pixels(item, across) - shape.width) < 1e-3, 'a line across is as long as the rectangle is wide'
    box_mark = mm.add_mark(item, 'RECT', (0.3, 0.3), (0.6, 0.6))
    wide, high = mm.mark_pixels(item, item.measures[1])
    assert wide > 0 and high > 0
    # Marks and canvas agree through the correction.
    start = mm.mark_canvas_points(item, item.measures[0])
    assert close(mm.canvas_to_uv(item, start[0]), item.measures[0].p0, 1e-5)
    item.measures.clear()
    p.set_straightened(item, False)

    # --- The tab draws ------------------------------------------------------------------------------------
    class Layout:
        def __getattr__(self, name):
            def call(*args, **kwargs):
                return Layout()
            return call

    from k_tools_kanvas.ui.tabs import image_perspective
    image_perspective.draw(Layout(), bpy.context, settings, item)
    item.persp_editing = True
    item.persp_enabled = True
    image_perspective.draw(Layout(), bpy.context, settings, item)
    # --- Show Whole Image: the whole photo straightened, the rectangle in place ---------------------------
    item.persp_enabled = False
    item.persp_auto = False
    item.persp_aspect = 1.5
    item.location = (300.0, 100.0)
    item.rotation, item.scale_master = 20.0, 0.5
    item.persp_corners = (0.1, 0.1, 0.9, 0.2, 0.8, 0.9, 0.2, 0.7)
    assert p.set_straightened(item, True)
    rect_box = c.corrected(item)
    middle = image_point_from_uv(item, p.apply(rect_box.forward, (0.5, 0.5)))
    rect_size = c.box_size(item, 1000, 800)
    assert p.set_whole(item, True) and item.persp_whole
    whole = c.corrected(item)
    u0, v0, u1, v1 = whole.bounds
    assert u0 <= 0 and v0 <= 0 and u1 >= 1 and v1 >= 1 and (u1 - u0) * (v1 - v0) > 1.2, whole.bounds
    size = c.box_size(item, 1000, 800)
    assert size[0] > rect_size[0] and size[1] > rect_size[1]
    assert close(image_point_from_uv(item, p.apply(whole.forward, (0.5, 0.5))), middle, 1e-3),         'the rectangle stays where it was'
    assert c.pivot_uv(item) == whole.pivot
    # The corners of the photo are inside the box (edges included), the outside is not.
    for photo_corner in ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)):
        assert image_uv_at(item, image_point_from_uv(item, photo_corner)) is not None, photo_corner
    far = image_point_from_uv(item, p.apply(whole.forward, (u1 + 0.5, v1 + 0.5)))
    assert image_uv_at(item, far) is None
    for flip_h, flip_v in ((False, False), (True, False), (False, True), (True, True)):
        item.flip_h, item.flip_v = flip_h, flip_v
        for uv in ((0.1, 0.1), (0.9, 0.9), (0.5, 0.5), (0.02, 0.97)):
            point = image_point_from_uv(item, uv)
            back = image_uv_at(item, point)
            assert back is not None and math.dist(uv, back) < 1e-5, (flip_h, flip_v, uv, back)
            assert close(mm.canvas_to_uv(item, point), uv, 1e-5)
    item.flip_h = item.flip_v = False
    assert ip.picture_uv_rect(item, True) == whole.bounds
    shown = ip.picture_size(item)
    assert abs(shown[0] - size[0]) <= 2 and abs(shown[1] - size[1]) <= 2
    assert p.set_whole(item, False) and c.box_size(item, 1000, 800) == rect_size
    assert close(image_point_from_uv(item, p.apply(c.corrected(item).forward, (0.5, 0.5))), middle, 1e-3)
    # A corner past the horizon is held within reach.
    far_quad = (0.1, 0.1, 0.9, 0.1, 0.55, 0.9, 0.45, 0.9)
    item.persp_corners = far_quad
    item.persp_whole = True
    bounds = c.corrected(item).bounds
    assert all(-p.WHOLE_REACH - 1e-9 <= v <= 1 + p.WHOLE_REACH + 1e-9 for v in bounds), bounds
    item.persp_whole = False

    # --- Straightening keeps the proportions it estimated; Estimate asks again ------------------------------
    item.persp_enabled = False
    item.persp_corners = (0.2, 0.25, 0.8, 0.25, 0.8, 0.75, 0.2, 0.75)
    item.persp_auto = True
    assert p.set_straightened(item, True)
    assert not item.persp_auto and abs(item.persp_aspect - 1.5) < 1e-6
    item.persp_corners = (0.2, 0.25, 0.8, 0.25, 0.8, 0.9, 0.2, 0.9)
    assert abs(item.persp_aspect - 1.5) < 1e-6, 'moving a corner leaves the proportions'
    p.fix_proportions(item)
    assert abs(item.persp_aspect - 600 / 520) < 1e-6
    p.set_straightened(item, False)

    # --- The tab bar breaks into two lines ----------------------------------------------------------------------
    from k_tools_kanvas.ui.tabs import draw_tab_bar
    rows = []

    class Row:
        def prop_enum(self, data, name, value, text='', icon=''):
            rows[-1].append(value)

        def prop(self, *args, **kwargs):
            rows[-1].append('all')

    class Column:
        def __init__(self):
            self.scale_y = 1.0

        def row(self, align=False):
            rows.append([])
            return Row()

    class TabLayout:
        def column(self, align=False):
            return Column()

        def row(self, align=False):
            rows.append([])
            return Row()

    draw_tab_bar(TabLayout(), bpy.context, 'image')
    assert [len(r) for r in rows] == [3, 3] and rows[0][0] == 'MAIN' and rows[1][-1] == 'PERSPECTIVE', rows
    rows.clear()
    draw_tab_bar(TabLayout(), bpy.context, 'shape')
    assert rows == [['all']], 'four tabs stay on one line'
    print('test_perspective: OK')
finally:
    addon.unregister()
