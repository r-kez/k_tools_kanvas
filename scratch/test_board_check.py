"""Board check finds broken references and repairs them without deleting content."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.board_check import find_problems, fix_problems

addon.register()
try:
    tree = bpy.data.node_groups.new('Check', 'KanvasNodeTree')
    settings = tree.kanvas_settings

    def add(kind, name, **props):
        item = settings.images.add()
        item.item_type, item.name, item.item_id = kind, name, name
        for key, value in props.items():
            setattr(item, key, value)
        return item

    assert find_problems(settings) == [], 'an empty board is healthy'

    frame = add('FRAME', 'frame', frame_node_name='frame-1')
    card = add('TEXT', 'tasks', text_checklist=True)
    card.text_lines.add().line_id = 'line-ok'
    picture = add('IMAGE', 'photo')
    picture.image_data = bpy.data.images.new('p', 4, 4)
    inside = add('TEXT', 'inside', parent_frame='frame-1')
    assert find_problems(settings) == [], 'a consistent board is healthy'

    # --- damage it ---------------------------------------------------------
    picture.checklist_associations.add().card_id = 'tasks'
    picture.checklist_associations.add().card_id = 'deleted-card'           # broken
    good = picture.markup_regions.add()
    good.region_id, good.checklist_card_id, good.checklist_line_id = 'good', 'tasks', 'line-ok'
    orphan_region = picture.markup_regions.add()
    orphan_region.region_id, orphan_region.name = 'orph', 'Old task'
    orphan_region.checklist_card_id, orphan_region.checklist_line_id = 'tasks', 'line-gone'   # broken
    orphan_region.checklist_origin_card_id = 'tasks'
    stray = add('TEXT', 'stray', parent_frame='frame-that-was-deleted')                         # broken
    arrow = settings.arrows.add()
    arrow.start, arrow.end = (10.0, 20.0), (300.0, 40.0)
    arrow.start_item_id, arrow.end_item_id = 'gone-item', 'photo'                               # one broken
    add('IMAGE', 'empty image')                                                                  # no image
    add('TEXT', 'twin')
    twin = add('TEXT', 'twin')                                                                   # same id
    twin.name = 'twin copy'

    kinds = sorted(problem.kind for problem in find_problems(settings))
    assert kinds == ['ARROW', 'FRAME', 'IDS', 'LINK', 'NO_IMAGE', 'REGION'], kinds
    print('PROBLEMS FOUND:', kinds)
    unfixable = [p.kind for p in find_problems(settings) if not p.fixable]
    assert unfixable == ['NO_IMAGE'], 'an item without an image cannot be repaired automatically'

    count_before = len(settings.images)
    changed = fix_problems(settings)
    assert changed >= 5, changed
    assert len(settings.images) == count_before, 'repairing never deletes items'

    # Collection items can go stale when the collection grows, so look everything up again.
    def find(name):
        return next(item for item in settings.images if item.name == name)

    assert find('stray').parent_frame == '' and find('inside').parent_frame == 'frame-1',         'only the broken frame link is cleared'
    photo = find('photo')
    assert [link.card_id for link in photo.checklist_associations] == ['tasks'], 'the good link stays'
    regions = {region.region_id: region for region in photo.markup_regions}
    assert regions['orph'].checklist_card_id == '' and regions['good'].checklist_card_id == 'tasks'
    assert regions['orph'].name == 'Old task', 'the region and its name are kept'
    arrow = settings.arrows[0]
    assert arrow.start_item_id == '' and arrow.end_item_id == 'photo', 'only the broken end is freed'
    assert tuple(arrow.start) == (10.0, 20.0), 'the freed end stays where it was'
    ids = [item.item_id for item in settings.images]
    assert len(ids) == len(set(ids)) and all(ids), 'identities are unique again'
    remaining = [p.kind for p in find_problems(settings)]
    assert remaining == ['NO_IMAGE'], remaining
    assert fix_problems(settings) == 0, 'a second repair finds nothing to do'
    assert hasattr(bpy.ops.kanvas, 'check_board')
    print('BOARD CHECK OK')
finally:
    addon.unregister()
