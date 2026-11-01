"""Curated colors first, then distinct random ones; shuffle spreads all colors."""

import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.color_palette import (
    SEQUENCE, color_for_index, distinct_color, spread_colors)
from k_tools_kanvas.operators.ops_markup import _add_region

addon.register()
try:
    tree = bpy.data.node_groups.new('Colors', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_type = 'IMAGE'
    item.item_id = 'c'
    item.image_data = bpy.data.images.new('c', 8, 8)
    regions = [_add_region(item) for _ in range(14)]
    first = [tuple(round(c, 4) for c in r.color) for r in regions[:6]]
    assert first == [tuple(round(c, 4) for c in color) for color in SEQUENCE], first
    later = [tuple(r.color) for r in regions[6:]]
    assert len(set(later)) == len(later), 'random colors must not repeat'
    everything = [tuple(r.color) for r in regions]
    closest = min(math.dist(a, b) for i, a in enumerate(everything) for b in everything[i + 1:])
    assert closest > 0.08, f'two colors are nearly identical ({closest:.3f})'
    print(f'SEQUENCE THEN RANDOM OK (closest pair {closest:.2f})')

    colors = spread_colors(10)
    assert len(colors) == 10
    assert min(math.dist(a, b) for i, a in enumerate(colors) for b in colors[i + 1:]) > 0.12
    assert distinct_color([]) is not None
    assert color_for_index(2, []) == SEQUENCE[2]
    print('SPREAD OK')

    assert hasattr(bpy.ops.kanvas, 'randomize_markup_colors')
    assert (Path(addon.__file__).parent / 'assets' / 'icons' / 'arrows-shuffle.png').exists()
    print('SHUFFLE OPERATOR + ICON OK')
finally:
    addon.unregister()
