"""Check title migration and the optional visible header in Blender 5.3."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_text import _card_header, _top_band_height


addon.register()
try:
    tree = bpy.data.node_groups.new('Title migration', 'KanvasNodeTree')
    settings = tree.kanvas_settings

    old_title = settings.images.add()
    old_title.item_type = 'TEXT'
    old_title.name = 'Old list name'
    old_title.text_header = 'Visible legacy title'
    assert not old_title.is_property_set('text_show_header')

    old_plain = settings.images.add()
    old_plain.item_type = 'TEXT'
    old_plain.name = 'Plain card'
    assert not old_plain.is_property_set('text_show_header')

    new_card = settings.images.add()
    new_card.item_type = 'TEXT'
    new_card.name = 'New title'
    new_card.text_show_header = True
    assert new_card.is_property_set('text_show_header')

    addon._migrate_text_card_titles(settings)
    assert old_title.name == 'Visible legacy title'
    assert old_title.text_header == ''
    assert old_title.text_show_header
    assert _card_header(old_title) == 'Visible legacy title'
    assert not old_plain.text_show_header
    assert _card_header(old_plain) == ''
    assert _card_header(new_card) == 'New title'

    new_card.name = 'Renamed'
    assert _card_header(new_card) == 'Renamed'
    new_card.text_show_header = False
    assert _top_band_height(new_card, 18) == 0
    new_card.text_show_header = True
    assert _top_band_height(new_card, 18) > 0
    addon._migrate_text_card_titles(settings)
    assert old_title.name == 'Visible legacy title'
    print('TEXT CARD TITLES PASS')
finally:
    addon.unregister()
