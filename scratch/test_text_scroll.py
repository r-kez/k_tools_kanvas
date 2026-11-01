"""Check text scrolling, inline checklist styles, and zoom-stable wrapping."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KANVAS_OT_Interact
from k_tools_kanvas.utils.gpu.gpu_text import (
    _cached_markdown_rows, _markdown_rows, _scroll_layout, _scrollbar_geometry,
    _table_cell_cursor, hit_test_checklist, hit_test_markdown_link,
    hit_test_text_scrollbar, scroll_text_card,
)


class View:
    def __init__(self, scale):
        self.scale = scale

    def view_to_region(self, x, y, clip=False):
        return x * self.scale + 400, y * self.scale + 400


def region(scale=1.0):
    return SimpleNamespace(view2d=View(scale), width=1200, height=1000)


addon.register()
try:
    keymap = bpy.context.window_manager.keyconfigs.addon.keymaps.get('Node Editor')
    assert not any(item.idname == 'kanvas.interact'
                   and item.properties.action in {'TEXT_SCROLL_WHEEL', 'TEXT_SCROLL_HOVER'}
                   for item in keymap.keymap_items)
    tree = bpy.data.node_groups.new('Text layout test', 'KanvasNodeTree')
    card = tree.kanvas_settings.images.add()
    card.item_type = 'TEXT'
    card.item_id = 'text-layout-test'
    card.name = 'Long Note'
    card.text_width = 300
    card.text_height = 120
    card.text_font_size = 18

    for index in range(20):
        card.text_lines.add().value = f'Line {index:02d} wraps consistently at every zoom level'
    counts = [len(_scroll_layout(card, region(scale))['rows'])
              for scale in (0.8, 1.0, 1.2)]
    assert counts[0] == counts[1] == counts[2]
    card.text_scroll = 100
    card.is_selected = True
    layout = _scroll_layout(card, region())
    assert layout['max_scroll'] > 100 and layout['scroll_screen'] == 100
    track, thumb = _scrollbar_geometry(layout, card)
    assert track[2] - track[0] == 10
    assert track[1] < thumb[1] < thumb[3] < track[3]
    assert hit_test_text_scrollbar(card, region(),
                                   ((thumb[0] + thumb[2]) / 2,
                                    (thumb[1] + thumb[3]) / 2))
    assert scroll_text_card(card, region(), 15)
    assert card.text_scroll == 115
    redraws = []
    gesture = SimpleNamespace(drag_target=card, scroll_grab_offset=0)
    drag_context = SimpleNamespace(region=region(),
                                   area=SimpleNamespace(tag_redraw=lambda: redraws.append(True)))
    KANVAS_OT_Interact._update_text_scroll(gesture, drag_context, track[1])
    assert abs(card.text_scroll - layout['max_scroll']) < 1e-4 and redraws
    card.is_selected = False
    narrow_track, _ = _scrollbar_geometry(_scroll_layout(card, region()), card)
    assert narrow_track[2] - narrow_track[0] == 5

    card.text_checklist = True
    card.text_scroll = 0
    card.text_lines.clear()
    card.text_lines.add().value = '**Bold** [link](https://example.com/check) *note*'
    card.text_lines.add().value = '`Code` and ordinary text'
    layout = _scroll_layout(card, region())
    first_runs = layout['rows'][0][0]
    assert ('Bold', 'bold', None) in first_runs
    assert any(url == 'https://example.com/check' for _, _, url in first_runs)
    x0 = layout['bounds'][0] + layout['padding']
    y = layout['top'] - layout['font_size'] + 5
    assert hit_test_checklist(card, region(), (x0 + 5, y)) == 0
    import blf
    blf.size(0, layout['font_size'])
    link_x = x0 + layout['font_size'] * 1.5
    for value, _, url in first_runs:
        if url:
            break
        link_x += blf.dimensions(0, value)[0]
    assert hit_test_markdown_link(card, region(), (link_x + 3, y)) == 'https://example.com/check'
    checklist_counts = [len(_scroll_layout(card, region(scale))['rows'])
                        for scale in (0.8, 1.0, 1.2)]
    assert checklist_counts[0] == checklist_counts[1] == checklist_counts[2]

    card.text_checklist = False
    card.text_markdown = True
    card.text_lines.clear()
    for source in ('| Name | Link |', '| --- | ---: |',
                   '| Row | [open](https://example.com/table) |'):
        card.text_lines.add().value = source
    _cached_markdown_rows.cache_clear()
    layouts = [_scroll_layout(card, region(scale)) for scale in (0.8, 1.0, 1.2)]
    assert _cached_markdown_rows.cache_info().misses == 1
    assert _cached_markdown_rows.cache_info().hits == 2
    assert all(len(current['rows']) == len(layouts[0]['rows']) for current in layouts)
    offsets = []
    for scale, current in zip((0.8, 1.0, 1.2), layouts):
        visible, _, _, _ = _markdown_rows(card, region(scale), current)
        offsets.append((current['bounds'][3] - visible[0][2]) / scale)
    assert max(offsets) - min(offsets) < 1e-5, offsets
    layout = layouts[1]
    row = next((runs, height, meta) for runs, height, meta in layout['rows']
               if meta['kind'] == 'table' and not meta['table_header'])
    link_x = _table_cell_cursor(row[2], 1, row[2]['table_cells'][1],
                                layout['bounds'][0] + layout['padding'],
                                layout['font_size']) + 3
    link_y = layout['top'] - layout['font_size'] * 1.3 - layout['font_size'] + 5
    assert hit_test_markdown_link(card, region(), (link_x, link_y)) == 'https://example.com/table'
    card.text_lines[0].value += ' updated'
    _scroll_layout(card, region())
    assert _cached_markdown_rows.cache_info().misses == 2
    print('TEXT LAYOUT PASS')
finally:
    addon.unregister()
