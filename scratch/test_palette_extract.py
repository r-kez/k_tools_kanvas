"""Dominant colors of an image become color regions."""

import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_markup import extract_palette_regions
from k_tools_kanvas.utils.palette_extract import dominant_colors, hex_name

addon.register()
try:
    rng = np.random.default_rng(3)
    height, width = 120, 200
    red, green, blue = (0.85, 0.15, 0.15), (0.15, 0.7, 0.2), (0.15, 0.25, 0.9)
    rgb = np.zeros((height, width, 3), np.float32)
    rgb[:, :100] = red            # 50 %
    rgb[:60, 100:] = green        # 25 %
    rgb[60:, 100:] = blue         # 25 %
    rgb += rng.normal(0, 0.015, rgb.shape).astype(np.float32)
    rgb = rgb.clip(0, 1)

    colors = dominant_colors(rgb, 3)
    assert len(colors) == 3, colors
    (first, share_first), (second, _), (third, _) = colors
    assert abs(share_first - 0.5) < 0.05, 'the largest area comes first'
    assert max(abs(a - b) for a, b in zip(first, red)) < 0.05
    found = sorted([second, third])
    expected = sorted([green, blue])
    assert all(max(abs(a - b) for a, b in zip(c, e)) < 0.05 for c, e in zip(found, expected)), found
    print('DOMINANT COLORS OK', [hex_name(c) for c, _ in colors])

    flat = np.full((40, 40, 3), 0.5, np.float32)
    assert len(dominant_colors(flat, 6)) == 1, 'a flat image has a single color'
    assert hex_name((1.0, 0.0, 0.5)) == '#FF0080'

    # An image stored in Blender -> one region per color.
    tree = bpy.data.node_groups.new('Palette', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_type, item.item_id = 'IMAGE', 'pal'
    image = bpy.data.images.new('palette-test', width, height, alpha=True)
    rgba = np.ones((height, width, 4), np.float32)
    rgba[:, :, :3] = rgb[::-1]
    image.pixels.foreach_set(rgba.ravel())
    item.image_data = image
    regions = extract_palette_regions(item, 3)
    assert len(regions) == 3 and len(item.markup_regions) == 3
    assert all(region.name.startswith('#') and not region.dabs and not region.polygons for region in regions)
    top = tuple(regions[0].color)
    assert max(abs(a - b) for a, b in zip(top, red)) < 0.06, top
    assert item.markup_visible and hasattr(bpy.ops.kanvas, 'extract_palette')
    print('EXTRACT PALETTE OK')
finally:
    addon.unregister()
