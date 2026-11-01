"""Check color switching and creation data used by modal shortcuts."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_markup import (
    _add_region, _cycle_region, _color_step, _palette_buttons, _palette_action_at,
    _repeat_swatch_click,
)


addon.register()
try:
    tree = bpy.data.node_groups.new('Color shortcuts', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_id = 'color-shortcuts-image'
    item.item_type = 'IMAGE'
    item.image_data = bpy.data.images.new('Color shortcuts source', 32, 32)
    assert not _cycle_region(item, 1)
    _add_region(item)
    _add_region(item)
    item.markup_active_index = 0
    item.markup_editing = True
    assert _cycle_region(item, 1) and item.markup_active_index == 1
    assert _cycle_region(item, 1) and item.markup_active_index == 0
    assert _cycle_region(item, -1) and item.markup_active_index == 1
    _add_region(item)
    assert len(item.markup_regions) == 3 and item.markup_active_index == 2
    assert item.markup_editing
    for key, character, shift, direction in (
        ('COMMA', '<', True, -1), ('PERIOD', '>', True, 1),
        ('COMMA', ',', False, -1), ('PERIOD', '.', False, 1),
        ('GRLESS', '<', False, -1), ('GRLESS', '>', True, 1),
        ('LEFT_BRACKET', '[', False, -1),
    ):
        event = SimpleNamespace(type=key, unicode=character, shift=shift,
                                ctrl=False, alt=False, value='PRESS')
        assert _color_step(event) == direction
    region = SimpleNamespace(type='WINDOW', x=0, y=0, width=900, height=500)
    buttons = _palette_buttons(item, region)
    assert [action for action, _, _ in buttons] == [
        'SELECT', 'SELECT', 'SELECT', 'ADD']
    assert all(0 <= bounds[0] < bounds[2] <= region.width
               for _, _, bounds in buttons)
    for action, index, bounds in buttons:
        x, y = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
        assert _palette_action_at(buttons, x, y) == (action, index)
    assert _palette_action_at(buttons, 0, 0) is None
    assert _repeat_swatch_click((1, 10.0, 100, 100), 1, 104, 105, 10.3)
    assert not _repeat_swatch_click((1, 10.0, 100, 100), 2, 104, 105, 10.3)
    assert not _repeat_swatch_click((1, 10.0, 100, 100), 1, 104, 105, 10.6)
    side_panel = SimpleNamespace(type='UI', x=650, y=0, width=250, height=500)
    buttons_with_panel = _palette_buttons(item, region,
                                          SimpleNamespace(regions=(region, side_panel)))
    assert buttons_with_panel[-1][2][2] < side_panel.x
    print('COLOR MODE SHORTCUT DATA PASS')
finally:
    addon.unregister()
