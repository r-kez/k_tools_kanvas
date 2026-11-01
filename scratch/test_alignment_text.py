"""Small Blender background smoke test for Kanvas alignment and text cards."""

import sys
from pathlib import Path

import bpy
import gpu

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.utils.item_geometry import item_bounds
from k_tools_kanvas.utils.gpu import get_item_by_id, is_sync_needed, sync_kanvas_frames
from k_tools_kanvas.utils.gpu.gpu_text import draw_text_card, draw_text_label
from k_tools_kanvas.utils.gpu.gpu_text import hit_test_text_resize
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers


addon.register()
area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
area.type = 'NODE_EDITOR'
area.ui_type = 'KanvasNodeTree'
tree = bpy.data.node_groups.new('Kanvas Test', 'KanvasNodeTree')
area.spaces.active.node_tree = tree
region = next(region for region in area.regions if region.type == 'WINDOW')
settings = tree.kanvas_settings

with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
    for name, position, size in [('A', (-150, 20), (100, 80)), ('B', (190, 160), (60, 40))]:
        image = bpy.data.images.new(name, width=size[0], height=size[1])
        item = settings.images.add()
        item.image_data = image
        item.location = position
        item.is_selected = True
    assert bpy.ops.kanvas.align_items(mode='CENTER_X') == {'FINISHED'}
    a, b = settings.images[0], settings.images[1]
    assert abs((item_bounds(a)[0] + item_bounds(a)[2]) - (item_bounds(b)[0] + item_bounds(b)[2])) < 0.001
    assert bpy.ops.kanvas.align_items(mode='BOTTOM') == {'FINISHED'}
    assert abs(item_bounds(a)[1] - item_bounds(b)[1]) < 0.001

    middle = settings.images.add()
    middle.item_type = 'IMAGE'
    middle.image_data = bpy.data.images.new('Distribution', 30, 50)
    middle.is_selected = True
    a.location = (-250, 0)
    b.location = (250, 20)
    middle.location = (0, 10)
    left_anchor, right_anchor = tuple(a.location), tuple(b.location)
    assert bpy.ops.kanvas.distribute_items(axis='HORIZONTAL') == {'FINISHED'}
    gap_left = item_bounds(middle)[0] - item_bounds(a)[2]
    gap_right = item_bounds(b)[0] - item_bounds(middle)[2]
    assert abs(gap_left - gap_right) < 0.001
    assert tuple(a.location) == left_anchor and tuple(b.location) == right_anchor
    a.location[1], b.location[1], middle.location[1] = -250, 250, 0
    assert bpy.ops.kanvas.distribute_items(axis='VERTICAL') == {'FINISHED'}
    gap_bottom = item_bounds(middle)[1] - item_bounds(a)[3]
    gap_top = item_bounds(b)[1] - item_bounds(middle)[3]
    assert abs(gap_bottom - gap_top) < 0.001
    a.location[0], b.location[0], middle.location[0] = -10, 30, 0
    before = [tuple(item.location) for item in (a, b, middle)]
    assert bpy.ops.kanvas.distribute_items(axis='HORIZONTAL') == {'CANCELLED'}
    assert [tuple(item.location) for item in (a, b, middle)] == before
    settings.images.remove(2)

    assert bpy.ops.kanvas.create_text(location=(70, 70)) == {'FINISHED'}
    card = settings.images[settings.active_image_index]
    card_id = card.item_id
    assert card.item_type == 'TEXT' and len(card.text_lines) == 1
    assert bpy.ops.kanvas.add_text_line() == {'FINISHED'}
    card.text_lines[0].value = 'A long paragraph that must wrap within this card automatically.'
    card.text_lines[1].value = 'Second line'
    assert card.text_body == 'A long paragraph that must wrap within this card automatically.\nSecond line'
    card.text_body = 'First paragraph\nSecond paragraph'
    assert [line.value for line in card.text_lines] == ['First paragraph', 'Second paragraph']
    left, bottom, right, top = item_bounds(card)
    assert hit_test_text_resize(card, (right - 1, bottom + 1), 1.0)
    helper = KanvasInteractionHelpers()
    helper._start_text_resize(card, (right, bottom))
    helper._update_drag(bpy.context, right + 80, bottom - 45)
    assert card.text_scale == 1.0
    assert abs(card.text_width - 400) < 0.001
    assert abs(card.text_height - 225) < 0.001
    assert abs(item_bounds(card)[0] - left) < 0.001
    assert abs(item_bounds(card)[3] - top) < 0.001
    helper._cancel_drag(bpy.context)
    assert card.text_width == 320 and card.text_height == 180
    assert abs(card.text_scale - 1.0) < 0.001 and item_bounds(card) == (left, bottom, right, top)
    assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
    duplicate = settings.images[settings.active_image_index]
    duplicate_id = duplicate.item_id
    assert duplicate.item_type == 'TEXT'
    assert [line.value for line in duplicate.text_lines] == [line.value for line in card.text_lines]
    duplicate.text_scale = 1.5
    assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
    assert abs(settings.images[settings.active_image_index].text_scale - 1.5) < 0.001
    settings.images.remove(settings.active_image_index)
    settings.active_image_index = next(i for i, entry in enumerate(settings.images)
                                       if entry.item_id == duplicate_id)
    duplicate = get_item_by_id(settings, duplicate_id)
    card = get_item_by_id(settings, card_id)
    assert bpy.ops.kanvas.remove_text_line(index=1) == {'FINISHED'}
    assert len(duplicate.text_lines) == 1 and len(card.text_lines) == 2
    duplicate.is_selected = True
    a.is_selected = True
    assert bpy.ops.kanvas.align_items(mode='LEFT') == {'FINISHED'}
    assert abs(item_bounds(a)[0] - item_bounds(duplicate)[0]) < 0.001
    sync_kanvas_frames(tree, settings)
    assert not is_sync_needed(tree, settings)

    if hasattr(gpu, 'init'):
        gpu.init()
        offscreen = gpu.types.GPUOffScreen(512, 512)
        try:
            with offscreen.bind():
                gpu.state.viewport_set(0, 0, 512, 512)
                draw_text_card(card)
                draw_text_label(card, region)
        finally:
            offscreen.free()

addon.unregister()
print('alignment/text smoke test passed')
