"""Inverse color regions paint everything except the marked area."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_markup import (
    rasterize_markup, region_active_mask, region_index_at_uv)

addon.register()
try:
    tree = bpy.data.node_groups.new('Inverse', 'KanvasNodeTree')
    image = bpy.data.images.new('inv', 64, 64)
    item = tree.kanvas_settings.images.add()
    item.item_type = 'IMAGE'
    item.item_id = 'inverse-test'
    item.image_data = image
    region = item.markup_regions.add()
    region.region_id = 'r1'
    region.color = (1.0, 0.0, 0.0)
    region.opacity = 1.0
    polygon = region.polygons.add()
    polygon.sequence = 1
    for uv in ((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)):
        polygon.vertices.add().uv = uv
    region.next_sequence = 2

    rgba = rasterize_markup(item.markup_regions, 64, 64)
    assert rgba[32, 32, 3] > 0.99 and rgba[2, 2, 3] < 0.01
    assert region_index_at_uv(item, (0.5, 0.5)) == 0
    assert region_index_at_uv(item, (0.05, 0.05), radius=0) is None

    region.inverse = True
    rgba = rasterize_markup(item.markup_regions, 64, 64)
    assert rgba[32, 32, 3] < 0.01, 'marked area must stay clear'
    assert rgba[2, 2, 3] > 0.99, 'rest of the image must be colored'
    assert region_index_at_uv(item, (0.05, 0.05), radius=0) == 0
    assert region_index_at_uv(item, (0.5, 0.5), radius=0) is None
    mask = region_active_mask(item, region)
    assert mask is region_active_mask(item, region), 'inverse mask must be cached'
    assert mask[2, 2] > 0.99 and mask[32, 32] < 0.01

    region.inverse = False
    assert region_active_mask(item, region)[32, 32] > 0.99
    print('MARKUP INVERSE OK')
finally:
    addon.unregister()
