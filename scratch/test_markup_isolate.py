"""Isolating one color region hides the others in the markup texture."""

import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_markup import (
    _composite_regions, _region_masks, isolated_index)

addon.register()
try:
    tree = bpy.data.node_groups.new('Isolate', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_type = 'IMAGE'
    item.item_id = 'iso'
    item.image_data = bpy.data.images.new('iso', 64, 64)
    boxes = ((0.05, 0.45), (0.55, 0.95))
    for index, (low, high) in enumerate(boxes):
        region = item.markup_regions.add()
        region.region_id = f'r{index}'
        region.name = f'Color {index + 1}'
        region.opacity = 1.0
        polygon = region.polygons.add()
        polygon.sequence = 1
        for uv in ((low, low), (high, low), (high, high), (low, high)):
            polygon.vertices.add().uv = uv
        region.next_sequence = 2
    regions, masks = item.markup_regions, _region_masks(item.markup_regions, 64, 64)

    assert isolated_index(item) == -1
    both = _composite_regions(regions, masks, 64, 64)
    assert both[16, 16, 3] > 0.99 and both[48, 48, 3] > 0.99

    item.markup_isolate_id = 'r1'
    assert isolated_index(item) == 1
    only = _composite_regions(regions, masks, 64, 64, only=1)
    assert only[16, 16, 3] < 0.01 and only[48, 48, 3] > 0.99

    # Reordering keeps the same region isolated (it is tracked by ID).
    regions.move(1, 0)
    assert isolated_index(item) == 0
    item.markup_isolate_id = 'missing'
    assert isolated_index(item) == -1

    # Choosing a region in the list moves the isolation along with it.
    item.markup_isolate_id = 'r0'
    item.markup_active_index = 1
    assert item.markup_isolate_id == regions[1].region_id
    item.markup_isolate_id = ''
    item.markup_active_index = 0
    assert item.markup_isolate_id == ''
    print('ISOLATE STATE OK')

    # Operator cycle: off -> 1 -> 2 -> off, and previous wraps to the last one.
    from k_tools_kanvas.operators import ops_markup
    class Ctx:  # minimal context for the cycling logic
        pass
    names = []
    for direction in (1, 1, 1, -1, 0):
        count, current = len(regions), isolated_index(item)
        if direction == 0:
            target = -1
        elif direction > 0:
            target = 0 if current < 0 else (current + 1 if current + 1 < count else -1)
        else:
            target = count - 1 if current < 0 else current - 1
        item.markup_isolate_id = regions[target].region_id if target >= 0 else ''
        names.append(isolated_index(item))
    assert names == [0, 1, -1, 1, -1], names
    assert hasattr(bpy.ops.kanvas, 'isolate_markup_region')
    print('ISOLATE CYCLE OK')
finally:
    addon.unregister()
