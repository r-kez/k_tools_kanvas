"""Check task anchors follow a checklist row and survive layout changes."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.utils.gpu import ensure_item_ids
from k_tools_kanvas.utils.arrow_geometry import (
    anchor_candidate, checklist_anchor_points, endpoint, set_endpoint,
)


addon.register()
try:
    settings = get_settings(bpy.context)
    card = settings.images.add()
    card.item_type = 'TEXT'
    card.text_checklist = True
    card.location = (0.0, 0.0)
    card.text_lines.add().value = 'First task'
    card.text_lines.add().value = 'Second task'
    ensure_item_ids(settings)

    anchors = checklist_anchor_points(card)
    assert len(anchors) == 4
    second = anchors[2]
    candidate = anchor_candidate(settings, second[2], 1.0)
    assert candidate[0] == card.item_id and candidate[3] == second[0]

    arrow = settings.arrows.add()
    set_endpoint(arrow, 'start', candidate[2], candidate)
    assert arrow.start_line_id == card.text_lines[1].line_id
    before = endpoint(settings, arrow, 'start')
    card.text_font_size += 8
    after = endpoint(settings, arrow, 'start')
    assert after != before

    card.text_lines.remove(0)
    moved_up = endpoint(settings, arrow, 'start')
    assert moved_up[1] > after[1]

    set_endpoint(arrow, 'start', moved_up)
    assert not arrow.start_line_id and not arrow.start_item_id
    print('checklist arrow anchor check passed')
finally:
    addon.unregister()
