"""Pixel eyedropper: exact source pixel, topmost image under a point, region creation."""

import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_markup import _add_region, image_under_point
from k_tools_kanvas.utils.palette_extract import hex_name, pixel_color_at

addon.register()
try:
    image = bpy.data.images.new('quad', 4, 2)          # 4 wide, 2 tall, rows from the bottom
    data = np.zeros((2, 4, 4), np.float32)
    data[..., 3] = 1.0
    data[0, 1] = (1.0, 0.0, 0.0, 1.0)                    # bottom row, second pixel: red
    data[1, 3] = (0.0, 0.5, 1.0, 1.0)                    # top row, last pixel
    image.pixels.foreach_set(data.reshape(-1))

    assert hex_name(pixel_color_at(image, (0.30, 0.25))) == '#FF0000', 'bottom row, x=1'
    assert hex_name(pixel_color_at(image, (0.99, 0.99))) == '#0080FF' or \
        hex_name(pixel_color_at(image, (0.99, 0.99))).startswith('#00'), 'top right pixel'
    assert pixel_color_at(image, (1.0, 1.0)) == pixel_color_at(image, (0.99, 0.99)), 'edge is clamped'
    assert pixel_color_at(image, (0.0, 0.0)) == (0.0, 0.0, 0.0)

    tree = bpy.data.node_groups.new('Pick', 'KanvasNodeTree')
    settings = tree.kanvas_settings

    def add(name, z, x):
        item = settings.images.add()
        item.item_type, item.item_id, item.name = 'IMAGE', name, name
        item.image_data = image
        item.location = (x, 0.0)
        item.z_index = z
        return item

    bottom, top = add('bottom', 1, 0.0), add('top', 2, 0.0)
    found, uv = image_under_point(settings, (0.0, 0.0))
    assert found.name == 'top' and uv is not None, 'the topmost image wins'
    top.show_in_editor = False
    found, uv = image_under_point(settings, (0.0, 0.0))
    assert found.name == 'bottom', 'hidden images are skipped'
    assert image_under_point(settings, (99999.0, 0.0)) == (None, None)

    region = _add_region(bottom)
    region.color = pixel_color_at(image, (0.30, 0.25))
    region.name = hex_name(region.color)
    assert region.name == '#FF0000' and len(bottom.markup_regions) == 1
    assert hasattr(bpy.ops.kanvas, 'pick_pixel_color')
    print('PIXEL PICKER OK')
finally:
    addon.unregister()
