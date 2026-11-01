"""Export painted color regions as mask PNGs and an ID map."""

import os
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.markup_export import export_dimensions, export_markup_masks

addon.register()
try:
    tree = bpy.data.node_groups.new('Export', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'exp', 'My Photo!'
    item.image_data = bpy.data.images.new('src', 200, 100)

    def add_region(name, color, box, inverse=False):
        region = item.markup_regions.add()
        region.region_id, region.name, region.color = name + '-id', name, color
        region.inverse = inverse
        polygon = region.polygons.add()
        polygon.sequence = 1
        low, high = box
        for uv in ((low[0], low[1]), (high[0], low[1]), (high[0], high[1]), (low[0], high[1])):
            polygon.vertices.add().uv = uv
        region.next_sequence = 2
        return region

    add_region('Roof', (1.0, 0.0, 0.0), ((0.0, 0.5), (0.5, 1.0)))            # top-left, bottom-up UV
    add_region('Roof', (0.0, 1.0, 0.0), ((0.5, 0.0), (1.0, 0.5)))            # same name -> unique file
    add_region('Sky', (0.0, 0.0, 1.0), ((0.0, 0.0), (0.5, 0.5)), inverse=True)
    item.markup_regions.add().name = 'Empty'                                  # no paint: not exported

    assert export_dimensions(item.image_data, 'SOURCE') == (200, 100)
    assert export_dimensions(item.image_data, 'MASK') == (200, 100)
    big = bpy.data.images.new('big', 8000, 4000)
    assert export_dimensions(big, 'SOURCE') == (4096, 2048), 'exports are capped'

    with tempfile.TemporaryDirectory() as folder:
        paths = export_markup_masks(item, os.path.join(folder, 'out'), 'SOURCE', id_map=True)
        names = sorted(os.path.basename(p) for p in paths)
        assert names == ['My_Photo_Roof.png', 'My_Photo_Roof_2.png', 'My_Photo_Sky.png', 'My_Photo_ids.png'], names

        def load(name):
            image = bpy.data.images.load(os.path.join(folder, 'out', name))
            image.colorspace_settings.name = 'Non-Color'
            width, height = image.size
            data = np.empty(width * height * 4, np.float32)
            image.pixels.foreach_get(data)
            return data.reshape(height, width, 4), image

        roof, _ = load('My_Photo_Roof.png')
        assert roof.shape[:2] == (100, 200)
        # Rows start at the bottom: UV v 0.5..1 is the upper half, u 0..0.5 the left half.
        assert roof[75, 50, 0] > 0.99 and roof[25, 50, 0] < 0.01 and roof[75, 150, 0] < 0.01
        assert roof[75, 50, 3] > 0.99, 'masks are opaque'
        sky, _ = load('My_Photo_Sky.png')
        assert sky[25, 50, 0] < 0.01 and sky[75, 150, 0] > 0.99, 'Inverse is applied'
        ids, _ = load('My_Photo_ids.png')
        # Later regions are drawn over earlier ones: the inverted Sky covers both Roofs.
        assert ids[75, 50, :3].round(1).tolist() == [0.0, 0.0, 1.0] and ids[75, 50, 3] > 0.99
        assert ids[25, 150, :3].round(1).tolist() == [0.0, 0.0, 1.0]
        # The one area no region paints stays empty (transparent black).
        assert ids[25, 50, :3].round(1).tolist() == [0.0, 0.0, 0.0] and ids[25, 50, 3] < 0.01
        print('EXPORT FILES OK')

        none = export_markup_masks(item, os.path.join(folder, 'again'), 'MASK', id_map=False)
        assert len(none) == 3 and not any(p.endswith('_ids.png') for p in none)

    leftovers = [i.name for i in bpy.data.images if i.name.startswith('.kanvas_export')]
    assert not leftovers, 'temporary images must be removed'
    assert hasattr(bpy.ops.kanvas, 'export_markup_masks')
    print('MARKUP EXPORT OK')
finally:
    addon.unregister()
