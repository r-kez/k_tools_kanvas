"""Check checklist progress and the checkbox hitbox with its optional top band."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_text import (
    _checklist_percentage, _top_band_height, hit_test_checklist,
)
from k_tools_kanvas.utils.item_geometry import item_bounds


addon.register()
try:
    tree = bpy.data.node_groups.new('Checklist progress test', 'KanvasNodeTree')
    card = tree.kanvas_settings.images.add()
    card.item_type = 'TEXT'
    card.text_show_header = False
    card.text_checklist = True
    card.location = (200, 200)
    first = card.text_lines.add()
    first.value = 'First task'
    first.done = True
    empty = card.text_lines.add()
    empty.value = '  '
    empty.done = True
    last = card.text_lines.add()
    last.value = 'Last task'
    assert _checklist_percentage(card) == 50
    assert card.text_show_progress

    view = SimpleNamespace(view_to_region=lambda x, y, clip=False: (x, y))
    region = SimpleNamespace(view2d=view)
    left, _, _, top = item_bounds(card)
    band = _top_band_height(card, card.text_font_size)
    baseline = top - 12 - band - card.text_font_size
    assert hit_test_checklist(card, region, (left + 20, baseline + 8)) == 0

    card.text_show_progress = False
    assert _top_band_height(card, card.text_font_size) == 0
    baseline = top - 12 - card.text_font_size
    assert hit_test_checklist(card, region, (left + 20, baseline + 8)) == 0
    first.done = False
    assert _checklist_percentage(card) == 0
    print('CHECKLIST PROGRESS PASS')
finally:
    addon.unregister()
