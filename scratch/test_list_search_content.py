"""The item list search also finds text inside cards and color region names."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.ui.image_list import KANVAS_UL_image_list
from k_tools_kanvas.utils.item_search import item_matches

addon.register()
try:
    tree = bpy.data.node_groups.new('Search', 'KanvasNodeTree')
    settings = tree.kanvas_settings

    frame = settings.images.add()
    frame.item_type, frame.name, frame.frame_node_name, frame.item_id = 'FRAME', 'Ideas', 'frame-1', 'f'
    note = settings.images.add()
    note.item_type, note.name, note.item_id, note.parent_frame = 'TEXT', 'Shopping', 'n', 'frame-1'
    note.text_lines.add().value = 'Buy Concrete texture pack'
    checklist = settings.images.add()
    checklist.item_type, checklist.name, checklist.item_id = 'TEXT', 'Tasks', 'c'
    checklist.text_checklist = True
    checklist.text_lines.add().value = 'Model the lighthouse'
    picture = settings.images.add()
    picture.item_type, picture.name, picture.item_id = 'IMAGE', 'photo', 'p'
    picture.image_data = bpy.data.images.new('s', 4, 4)
    region = picture.markup_regions.add()
    region.region_id, region.name = 'r', 'Rusty roof'
    plain = settings.images.add()
    plain.item_type, plain.name, plain.item_id = 'IMAGE', 'other', 'o'
    plain.image_data = bpy.data.images.new('s2', 4, 4)

    assert item_matches(note, 'shopping') and item_matches(note, 'concrete'), 'card name and text'
    assert item_matches(checklist, 'lighthouse'), 'checklist task text'
    assert item_matches(picture, 'rusty'), 'color region name'
    assert item_matches(picture, 'photo'), 'item name still matches'
    assert not item_matches(plain, 'rusty') and not item_matches(frame, 'concrete')
    assert item_matches(frame, 'ideas') and item_matches(frame, '')

    def visible(query):
        settings.list_search = query
        stand_in = SimpleNamespace(bitflag_filter_item=1 << 30)
        flags, _order = KANVAS_UL_image_list.filter_items(stand_in, None, settings, 'images')
        return [item.name for item, flag in zip(settings.images, flags) if flag]

    assert 'Shopping' in visible('concrete'), 'text inside a card is found'
    assert 'Ideas' in visible('concrete'), 'its frame stays visible so the card has context'
    assert visible('lighthouse') == ['Tasks']
    assert visible('rusty') == ['photo']
    assert visible('nothing like this') == []
    assert len(visible('')) == 5
    print('LIST SEARCH CONTENT OK')
finally:
    addon.unregister()
