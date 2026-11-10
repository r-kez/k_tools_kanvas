"""Fit Bounds to Mask: an image item cropped to part of its image. The content does not move
when the crop is set or reset; the box (bounds, hit tests, handles) is the crop under any
rotation, shear, stretch and flip; image points and canvas points agree both ways inside
the crop; the whole image is shown while the mask is edited; Auto-fit follows the mask; the
picture, the marks and the copies of the item all see the crop."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    from k_tools_kanvas.utils import item_crop as c
    from k_tools_kanvas.utils import item_picture as ip
    from k_tools_kanvas.utils import measure as m
    from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv, image_uv_at
    from k_tools_kanvas.utils.item_geometry import item_bounds

    tree = bpy.data.node_groups.new('Crop', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = bpy.data.images.new('photo', 400, 200)
    item.location = (300.0, 100.0)
    item.rotation = 25.0
    item.scale_master = 0.5
    item.shear_xy = (0.1, -0.05)
    polygon = item.mask_polygons.add()
    for uv in ((0.2, 0.3), (0.6, 0.3), (0.6, 0.7), (0.2, 0.7)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    item.mask_enabled = True

    def close(a, b, tolerance=2e-3):
        return all(abs(x - y) < tolerance for x, y in zip(a, b))

    def aabb(points):
        return (min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points))

    # --- Nothing is cropped at first --------------------------------------------------------
    assert c.stored_crop(item) == c.FULL and c.shown_crop(item) == c.FULL
    assert c.box_size(item, 400, 200) == (400, 200) and c.pivot_uv(item) == (0.5, 0.5)
    whole = item_bounds(item)
    probe = (0.45, 0.55)
    placed = image_point_from_uv(item, probe)

    # --- Fit to the mask: the content stays where it is ----------------------------------------
    rect = ip.visible_uv_rect(item)
    assert rect is not None and close(rect, (0.2, 0.3, 0.6, 0.7), 0.02), rect
    assert c.set_crop(item, rect) and item.crop_enabled
    assert close(item.crop_uv, rect, 1e-6)
    assert close(image_point_from_uv(item, probe), placed), 'the picture did not move'
    assert math.dist(image_point_from_uv(item, c.pivot_uv(item)), item.location) < 1e-3, 'the pivot is the location'
    size = c.box_size(item, 400, 200)
    assert close(size, (400 * (rect[2] - rect[0]), 200 * (rect[3] - rect[1])), 1e-3)
    assert c.box_scale(item)[0] < item.scale_master and c.shown_crop(item) == c.stored_crop(item)

    # --- The box is the crop: bounds from the corners of the cropped rectangle -------------------
    expected = aabb([image_point_from_uv(item, uv) for uv in c.corners_uv(c.stored_crop(item))])
    assert close(item_bounds(item), expected, 5e-3), (item_bounds(item), expected)
    box = item_bounds(item)
    assert (box[2] - box[0]) < (whole[2] - whole[0]) * 0.6 and (box[3] - box[1]) < (whole[3] - whole[1]) * 0.6

    # --- Image and canvas points agree both ways inside the crop, for every flip -------------------
    for flip_h, flip_v, sx, sy in ((False, False, 1.0, 1.0), (True, False, 1.0, 1.0),
                                   (False, True, 1.0, 1.0), (True, True, 1.0, 1.0),
                                   (False, False, -1.0, 1.0), (True, False, -1.0, -1.0)):
        item.flip_h, item.flip_v = flip_h, flip_v
        item.scale_xy = (sx, sy)
        u0, v0, u1, v1 = c.stored_crop(item)
        for fu, fv in ((0.1, 0.1), (0.9, 0.9), (0.5, 0.5), (0.2, 0.8), (0.0, 0.0), (1.0, 1.0)):
            uv = (u0 + (u1 - u0) * fu, v0 + (v1 - v0) * fv)
            point = image_point_from_uv(item, uv)
            back = image_uv_at(item, point)
            assert back is not None and math.dist(uv, back) < 1e-5, (flip_h, flip_v, sx, uv, back)
            assert close(m.canvas_to_uv(item, point), uv, 1e-5), 'marks use the same mapping'
        outside = image_point_from_uv(item, (u1 + 0.1, v0 + 0.5 * (v1 - v0)))
        assert image_uv_at(item, outside) is None, 'outside the crop is outside the item'
        # The pivot is the middle of the crop in every case.
        assert math.dist(image_point_from_uv(item, c.pivot_uv(item)), item.location) < 1e-3
    item.flip_h = item.flip_v = False
    item.scale_xy = (1.0, 1.0)

    # --- The whole image is shown while the mask is edited, around the same pivot ------------------
    point_in_crop = image_point_from_uv(item, (0.4, 0.5))
    outside_uv = (0.05, 0.1)
    outside_point = image_point_from_uv(item, outside_uv)
    assert image_uv_at(item, outside_point) is None
    item.mask_editing = True
    assert c.shown_crop(item) == c.FULL and c.stored_crop(item) != c.FULL
    assert close(image_point_from_uv(item, (0.4, 0.5)), point_in_crop), 'nothing moved'
    assert image_uv_at(item, outside_point) is not None, 'strokes reach what the crop hides'
    assert close(item_bounds(item), box, 1e-6), 'the box stays the crop'
    from k_tools_kanvas.utils.gpu.gpu_visibility import image_intersects_view
    assert image_intersects_view(item, (-1e4, -1e4, 1e4, 1e4))
    item.mask_editing = False
    assert c.shown_crop(item) == c.stored_crop(item)

    # --- Reset: the whole size comes back and nothing moves ----------------------------------------
    assert c.set_crop(item, None) and not item.crop_enabled
    assert close(image_point_from_uv(item, probe), placed), 'reset did not move the picture'
    assert close(item.location, (300.0, 100.0), 5e-3), tuple(item.location)
    assert close(item_bounds(item), whole, 5e-3)

    # --- Rectangles too small, or the whole image, are not crops --------------------------------
    assert not c.set_crop(item, (0.3, 0.3, 0.30001, 0.5)) and not item.crop_enabled
    assert c.set_crop(item, (0.0, 0.0, 1.0, 1.0)) and not item.crop_enabled
    assert c.clamp_rect((-1.0, -1.0, 2.0, 2.0)) == (0.0, 0.0, 1.0, 1.0)

    # --- Pictures: the crop is the base, the mask narrows it ---------------------------------------------
    assert ip.picture_uv_rect(item, False) == c.FULL
    assert c.set_crop(item, (0.1, 0.1, 0.5, 0.9))
    assert ip.picture_uv_rect(item, False) == c.stored_crop(item)
    narrowed = ip.picture_uv_rect(item, True)
    assert close(narrowed, (0.2, 0.3, 0.5, 0.7), 0.02), narrowed         # mask 0.2-0.6, crop 0.1-0.5
    quad = ip.picture_quad(item, False)
    assert close((quad[2][2] - quad[2][0], quad[2][3] - quad[2][1]),
                 (0.4 * 400, 0.8 * 200), 1e-2), quad[2]
    c.set_crop(item, (0.7, 0.1, 0.9, 0.2))
    assert ip.picture_uv_rect(item, True) is None, 'a crop outside the mask shows nothing'
    c.set_crop(item, None)

    # --- Marks follow the item through a crop -----------------------------------------------------------
    mark = m.add_mark(item, 'LINE', (0.3, 0.4), (0.5, 0.4))
    before = m.mark_canvas_points(item, mark)
    assert c.set_crop(item, (0.2, 0.3, 0.6, 0.7))
    after = m.mark_canvas_points(item, item.measures[0])
    assert all(close(a, b) for a, b in zip(before, after)), 'a mark stays on the picture'
    assert abs(m.mark_pixels(item, item.measures[0]) - 80.0) < 1e-2
    c.set_crop(item, None)

    # --- Auto-fit follows the mask --------------------------------------------------------------------------
    item.crop_follow_mask = True
    item.mask_editing = True
    polygon = item.mask_polygons[0]
    for vertex, uv in zip(polygon.vertices, ((0.1, 0.1), (0.5, 0.1), (0.5, 0.5), (0.1, 0.5))):
        vertex.uv = uv
    item.mask_revision += 1
    item.mask_editing = False
    assert item.crop_enabled and close(item.crop_uv, (0.1, 0.1, 0.5, 0.5), 0.02), tuple(item.crop_uv)
    item.mask_enabled = False
    assert not item.crop_enabled, 'no mask, no crop'
    item.mask_enabled = True
    assert item.crop_enabled
    item.crop_follow_mask = False
    c.set_crop(item, None)

    # --- Copies carry the crop -------------------------------------------------------------------------------
    c.set_crop(item, (0.2, 0.3, 0.6, 0.7))
    state = (tuple(item.crop_uv), item.crop_enabled)
    settings.active_image_index = 0
    for other in settings.images:
        other.is_selected = other.item_id == 'photo'
    try:
        result = bpy.ops.kanvas.duplicate_image()
    except RuntimeError:
        result = None      # the operator needs a Kanvas editor: covered by the GUI test
    if result == {'FINISHED'}:
        copy = next(i for i in settings.images if i.item_id != 'photo')
        assert (tuple(copy.crop_uv), copy.crop_enabled) == state

    # --- A frame around the item fits the crop (items are looked up again after every add) -----
    from k_tools_kanvas.utils.gpu import update_frame_bounds

    def by_id(item_id):
        return next(i for i in settings.images if i.item_id == item_id)

    frame = settings.images.add()
    frame.item_type, frame.item_id, frame.frame_node_name = 'FRAME', 'around', 'around'
    frame.location, frame.frame_width, frame.frame_height = (0.0, 0.0), 300.0, 200.0
    framed = settings.images.add()
    framed.item_type, framed.item_id, framed.name = 'IMAGE', 'framed', 'Framed'
    framed.image_data = bpy.data.images.new('framed', 400, 200)
    by_id('framed').parent_frame = 'around'
    update_frame_bounds(tree, settings, 'around')
    wide = by_id('around').frame_width
    assert c.set_crop(by_id('framed'), (0.25, 0.25, 0.5, 0.75))
    narrow = by_id('around').frame_width
    assert narrow < 0.5 * wide, f'the frame fits the crop: {wide} -> {narrow}'
    assert c.set_crop(by_id('framed'), None)
    assert abs(by_id('around').frame_width - wide) < 1.0, 'and the whole image again'
    print('test_crop: OK')
finally:
    addon.unregister()
