"""Measure cold and warm Markdown card layout in a Blender background build."""

import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_text import _cached_markdown_rows, _scroll_layout


class View:
    def view_to_region(self, x, y, clip=False):
        return x + 500, y + 500


addon.register()
try:
    tree = bpy.data.node_groups.new('Markdown layout benchmark', 'KanvasNodeTree')
    card = tree.kanvas_settings.images.add()
    card.item_type = 'TEXT'
    card.text_markdown = True
    card.text_width = 500
    card.text_height = 220
    card.text_font_size = 18
    for index in range(80):
        for source in ('| Name | Detail | Cost |', '| --- | :---: | ---: |',
                       f'| **Item {index}** | *Detailed notes* and [link](https://example.com/{index}) | ${index * 12} |'):
            card.text_lines.add().value = source
    region = SimpleNamespace(view2d=View(), width=1200, height=900)
    _cached_markdown_rows.cache_clear()
    start = time.perf_counter()
    _scroll_layout(card, region)
    cold = time.perf_counter() - start
    timings = []
    for _ in range(30):
        start = time.perf_counter()
        _scroll_layout(card, region)
        timings.append(time.perf_counter() - start)
    print(f'MARKDOWN LAYOUT cold={cold * 1000:.2f}ms '
          f'warm_median={statistics.median(timings) * 1000:.2f}ms '
          f'cache={_cached_markdown_rows.cache_info()}')
finally:
    addon.unregister()
