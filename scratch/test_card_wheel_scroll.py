"""Mouse wheel scrolls long text cards: selected-only, hover, off, and Move mode."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators import ops_modal
from k_tools_kanvas.utils.gpu import gpu_text

addon.register()
try:
    class View:
        def view_to_region(self, x, y, clip=False):
            return x + 600, y + 400
        def region_to_view(self, x, y):
            return x - 600, y - 400

    tree = bpy.data.node_groups.new('Wheel', 'KanvasNodeTree')
    settings = tree.kanvas_settings

    def card(name, lines, x):
        item = settings.images.add()
        item.item_type, item.name, item.item_id = 'TEXT', name, name
        item.location, item.text_width, item.text_height, item.text_font_size = (x, 100), 300, 160, 18
        for index in range(lines):
            item.text_lines.add().value = f'line {index}'
        return item

    long_card, short_card = card('long', 60, -400), card('short', 1, 100)
    region = SimpleNamespace(view2d=View(), width=1600, height=900)
    area = SimpleNamespace(tag_redraw=lambda: None)
    context = SimpleNamespace(region=region, area=area)

    # ---- the card-level helper ------------------------------------------
    assert gpu_text.wheel_scroll_card(short_card, region, -1) is False, 'a card that fits has nothing to scroll'
    assert long_card.text_scroll == 0
    assert gpu_text.wheel_scroll_card(long_card, region, -1) is True
    first = long_card.text_scroll
    assert first > 0, 'wheel down scrolls the text down'
    gpu_text.wheel_scroll_card(long_card, region, 1)
    assert 0 <= long_card.text_scroll < first, 'wheel up scrolls back'
    long_card.text_scroll = 0.0
    assert gpu_text.wheel_scroll_card(long_card, region, 1) is True, 'still consumed at the top'
    assert long_card.text_scroll == 0.0
    for _ in range(200):
        gpu_text.wheel_scroll_card(long_card, region, -1)
    end = long_card.text_scroll
    assert gpu_text.wheel_scroll_card(long_card, region, -1) is True and long_card.text_scroll == end
    print(f'HELPER OK (end of scroll at {end:.0f})')
    long_card.text_scroll = 0.0

    # ---- the operator decision, per preference -------------------------------
    def wheel(mode, *, selected, over, canvas_mode='EDIT', wheel_type='WHEELDOWNMOUSE'):
        ops_modal.get_prefs = lambda: SimpleNamespace(card_wheel_scroll=mode)
        settings.canvas_mode = canvas_mode
        long_card.is_selected = selected
        long_card.text_scroll = 0.0
        x, y = (-300 + 600, 150 + 400) if over == 'long' else (800, 800)   # region pixels
        event = SimpleNamespace(type=wheel_type, mouse_region_x=x, mouse_region_y=y)
        result = ops_modal.KANVAS_OT_Interact._wheel_scroll_card(SimpleNamespace(), context, event, settings)
        return result, long_card.text_scroll

    assert wheel('SELECTED', selected=True, over='long') == ({'CANCELLED'}, wheel('SELECTED', selected=True, over='long')[1])
    assert wheel('SELECTED', selected=True, over='long')[1] > 0
    assert wheel('SELECTED', selected=False, over='long') == ({'PASS_THROUGH'}, 0.0), 'unselected card must not capture the wheel'
    assert wheel('SELECTED', selected=True, over='nothing') == ({'PASS_THROUGH'}, 0.0), 'off the card the wheel zooms'
    assert wheel('HOVER', selected=False, over='long')[0] == {'CANCELLED'}
    assert wheel('HOVER', selected=False, over='long')[1] > 0
    assert wheel('OFF', selected=True, over='long') == ({'PASS_THROUGH'}, 0.0)
    assert wheel('SELECTED', selected=False, over='long', canvas_mode='MOVE')[0] == {'CANCELLED'}, 'Move mode scrolls on hover'
    up, scroll = wheel('HOVER', selected=True, over='long', wheel_type='WHEELUPMOUSE')
    assert up == {'CANCELLED'} and scroll == 0.0, 'wheel up at the top stays put but is still consumed'

    long_card.is_locked = True
    assert wheel('HOVER', selected=True, over='long')[0] == {'PASS_THROUGH'}, 'locked cards are left alone'
    long_card.is_locked = False

    # A short card under the pointer never traps the wheel.
    ops_modal.get_prefs = lambda: SimpleNamespace(card_wheel_scroll='HOVER')
    short_card.is_selected = True
    event = SimpleNamespace(type='WHEELDOWNMOUSE', mouse_region_x=100 + 600 + 20, mouse_region_y=100 + 400 - 20)
    assert ops_modal.KANVAS_OT_Interact._wheel_scroll_card(SimpleNamespace(), context, event, settings) == {'PASS_THROUGH'}

    # The plain wheel is bound, next to the modifier ones.
    from k_tools_kanvas import keymap
    keymap.rebuild()
    wheel_items = [(item.type, item.ctrl, item.shift, item.alt) for _, item in keymap._items
                   if item.idname == 'kanvas.interact' and item.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}]
    plain = [entry for entry in wheel_items if not any(entry[1:])]
    assert len(plain) == 2 and len(wheel_items) == 8, wheel_items
    print('CARD WHEEL SCROLL OK')
finally:
    addon.unregister()
