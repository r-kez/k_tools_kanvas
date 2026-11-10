"""Measuring on images: marks in image coordinates, the scale one of them gives, and
what it makes of the other marks (pixels without a scale, then real units), the same
point of the canvas and of the image both ways under rotation, shear, stretch and
flips, the real size a picture gets in the 3D View, and copies of an item."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    from k_tools_kanvas.utils import measure as m
    from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv

    tree = bpy.data.node_groups.new('Measure', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Car'
    item.image_data = bpy.data.images.new('car', 400, 200)

    # --- Without a scale: pixels ----------------------------------------------------------
    line = m.add_mark(item, 'LINE', (0.25, 0.5), (0.75, 0.5))
    line_id = line.measure_id
    assert line.name == 'Line 1' and item.measure_active_index == 0
    assert m.mark_pixels(item, item.measures[0]) == 200.0
    assert m.meters_per_pixel(item) is None and not m.is_calibrated(item)
    assert m.mark_text(item, item.measures[0], 'CM') == '200 px', m.mark_text(item, item.measures[0], 'CM')
    rect = m.add_mark(item, 'RECT', (0.1, 0.2), (0.3, 0.6))
    rect_id = rect.measure_id
    assert rect.name == 'Rectangle 1' and len(item.measures) == 2
    assert all(abs(a - b) < 1e-3 for a, b in zip(m.mark_pixels(item, item.measures[1]), (80.0, 80.0)))
    assert m.mark_text(item, item.measures[1], 'CM') == '80 × 80 px'
    assert m.scale_text(item) is None

    # --- A scale: the line is 1 meter long -------------------------------------------------
    assert not m.set_scale(item, line_id, 0.0, 'M'), 'a zero size is no scale'
    assert not m.set_scale(item, 'gone', 1.0, 'M'), 'a mark that is gone is no scale'
    assert m.set_scale(item, line_id, 1.0, 'M')
    assert item.measure_scale_id == line_id and m.scale_mark(item).name == 'Line 1'
    assert abs(m.meters_per_pixel(item) - 0.005) < 1e-12
    assert m.mark_text(item, item.measures[0], 'CM') == '100 cm'
    assert m.mark_text(item, item.measures[0], 'M') == '1 m'
    assert m.mark_text(item, item.measures[0], 'MM') == '1000 mm'
    assert m.mark_text(item, item.measures[0], 'IN') == '39.37 in'
    assert m.mark_text(item, item.measures[0], 'FT') == '3.28 ft'
    assert m.mark_text(item, item.measures[1], 'CM') == '40 × 40 cm'
    assert m.scale_text(item) == '1 px = 0.005 m', m.scale_text(item)

    # --- A rectangle as the scale: its height is 66 cm -------------------------------------
    assert m.set_scale(item, rect_id, 66.0, 'CM', 'HEIGHT')
    assert item.measure_scale_id == rect_id
    assert abs(m.meters_per_pixel(item) - 0.66 / 80.0) < 1e-6   # points are 32-bit floats
    assert m.set_scale(item, rect_id, 40.0, 'CM', 'WIDTH')
    assert abs(m.meters_per_pixel(item) - 0.4 / 80.0) < 1e-6, 'by the width'
    assert m.mark_text(item, item.measures[0], 'CM') == '100 cm'
    m.clear_scale(item)
    assert m.valid_side('RECT', 'LENGTH') == 'HEIGHT' and m.valid_side('LINE', 'WIDTH') == 'LENGTH'
    assert m.set_scale(item, rect_id, 66.0, 'CM', 'LENGTH') and item.measures[1].known_side == 'HEIGHT'
    m.clear_scale(item)
    assert not m.is_calibrated(item) and m.mark_text(item, item.measures[0], 'CM') == '200 px'
    assert m.set_scale(item, line_id, 1.0, 'M')

    # --- Text: units and rounding ------------------------------------------------------------
    assert m.format_length(0.66, 'CM') == '66 cm' and m.format_length(0.0123, 'MM') == '12.3 mm'
    assert m.format_length(2.5, 'M') == '2.5 m' and m.format_length(1234.5, 'MM') == '1234500 mm'
    assert m.format_pixels(412.0) == '412 px' and m.format_pixels(3.26) == '3.3 px'

    # --- Canvas and image coordinates, both ways, under any transform -----------------------
    item.location = (120.0, -40.0)
    item.rotation = 30.0
    item.scale_master = 0.5
    item.scale_xy = (2.0, 1.0)
    item.shear_xy = (0.15, -0.05)
    for flip_h, flip_v, sx in ((False, False, 2.0), (True, False, 2.0), (False, True, -2.0),
                               (True, True, -2.0)):
        item.flip_h, item.flip_v = flip_h, flip_v
        item.scale_xy = (sx, 1.0)
        for uv in ((0.0, 0.0), (1.0, 1.0), (0.3, 0.8), (0.9, 0.1), (0.5, 0.5)):
            point = image_point_from_uv(item, uv)
            back = m.canvas_to_uv(item, point)
            assert math.dist(uv, back) < 1e-9, (flip_h, flip_v, sx, uv, back)
    item.flip_h = item.flip_v = False
    item.scale_xy = (1.0, 1.0)
    item.rotation = 0.0
    item.shear_xy = (0.0, 0.0)
    item.scale_master = 1.0
    item.location = (0.0, 0.0)
    corners = m.mark_canvas_points(item, item.measures[1])
    assert len(corners) == 4 and len(m.mark_canvas_points(item, item.measures[0])) == 2
    middle = m.mark_label_point(item, item.measures[0])
    assert abs(middle[0]) < 1e-9 and abs(middle[1]) < 1e-9, middle   # the line crosses the center

    # --- Real size of a picture in the 3D View -------------------------------------------
    # 400 px wide, 0.005 m a pixel: 2 meters.
    assert abs(m.real_size_meters(item, 400.0) - 2.0) < 1e-12
    scene = bpy.context.scene
    assert m.scene_units(2.0, scene) == 2.0
    scene.unit_settings.scale_length = 0.01
    assert abs(m.scene_units(2.0, scene) - 200.0) < 1e-3, 'Unit Scale 0.01: a unit is a cm'
    scene.unit_settings.scale_length = 1.0
    m.clear_scale(item)
    assert m.real_size_meters(item, 400.0) is None and m.signature(item) is None
    m.set_scale(item, line_id, 1.0, 'M')
    first = m.signature(item)
    item.measures[0].known_value = 2.0
    assert m.signature(item) != first, 'a new real size changes the signature'

    # --- Copies of an item carry their marks and scale ---------------------------------------
    settings.active_image_index = 0
    for other in settings.images:
        other.is_selected = other.item_id == 'photo'
    area_context = bpy.context
    try:
        result = bpy.ops.kanvas.duplicate_image()
    except RuntimeError:
        result = None      # the operator needs a Kanvas editor: covered by the GUI test
    if result == {'FINISHED'}:
        copy = next(i for i in settings.images if i.item_id != 'photo')
        assert len(copy.measures) == 2 and copy.measure_scale_id == line_id
    print('test_measure: OK')
finally:
    addon.unregister()
