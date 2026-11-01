"""Smoke test for text cards parented to Kanvas frames."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.utils.gpu import (
    auto_parent_images_to_frames, get_frame, is_sync_needed, sync_kanvas_frames,
    update_frame_bounds,
)
from k_tools_kanvas.utils.item_geometry import item_bounds

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Text frame test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_frame(cursor=(0, 0)) == {'FINISHED'}
        frame_id = next(item.frame_node_name for item in settings.images if item.item_type == 'FRAME')
        assert bpy.ops.kanvas.create_text(location=(100, -100)) == {'FINISHED'}
        card = next(item for item in settings.images if item.item_type == 'TEXT')
        frame = get_frame(settings, frame_id)
        assert card.parent_frame == frame_id
        assert not is_sync_needed(tree, settings)
        bounds = item_bounds(card)
        assert frame.location[0] <= bounds[0]
        assert frame.location[0] + frame.frame_width >= bounds[2]

        old_frame_width = frame.frame_width
        card.text_scale = 2.0
        assert frame.frame_width > old_frame_width

        start = tuple(card.location)
        helper = KanvasInteractionHelpers()
        helper._start_frame_drag(bpy.context, frame, 'MOVE', tuple(frame.location))
        helper._update_drag(bpy.context, frame.location[0] + 50, frame.location[1] - 30)
        assert tuple(card.location) == (start[0] + 50, start[1] - 30)
        helper._cancel_drag(bpy.context)
        assert tuple(card.location) == start

        # The corner changes dimensions independently, and cancel restores
        # both the card and its auto-fitted frame.
        before_card = (tuple(card.location), card.text_width,
                       card.text_height, card.text_scale)
        before_frame = (tuple(frame.location), frame.frame_width, frame.frame_height)
        _, bottom, right, _ = item_bounds(card)
        helper._start_text_resize(card, (right, bottom))
        helper._update_drag(bpy.context, right + 80, bottom)
        assert card.text_width == before_card[1] + 80 / before_card[3]
        assert card.text_height == before_card[2]
        assert card.text_scale == before_card[3]
        assert frame.frame_width > before_frame[1]
        helper._cancel_drag(bpy.context)
        assert (tuple(card.location), card.text_width,
                card.text_height, card.text_scale) == before_card
        assert (tuple(frame.location), frame.frame_width, frame.frame_height) == before_frame

        _, bottom, right, _ = item_bounds(card)
        helper._start_text_resize(card, (right, bottom))
        helper._update_drag(bpy.context, right, bottom - 50)
        assert card.text_width == before_card[1]
        assert card.text_height == before_card[2] + 50 / before_card[3]
        helper._stop_drag(bpy.context)
        assert card.text_height > before_card[2]

        frame.show_in_editor = False
        assert not card.show_in_editor
        frame.show_in_editor = True
        assert card.show_in_editor

        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_type == 'TEXT')
        card.is_selected = True
        assert bpy.ops.kanvas.detach_from_frame() == {'FINISHED'}
        card = next(item for item in settings.images if item.item_type == 'TEXT')
        assert not card.parent_frame
        card.location = tuple(frame.location)
        assert frame_id in auto_parent_images_to_frames(tree, settings, targets=[card])
        assert card.parent_frame == frame_id
        update_frame_bounds(tree, settings, frame_id)
        sync_kanvas_frames(tree, settings)
        assert not is_sync_needed(tree, settings)

        assert bpy.ops.kanvas.remove_image(index=settings.active_image_index) == {'FINISHED'}
        assert not any(item.item_type == 'TEXT' for item in settings.images)
    print('text/frame smoke test passed')
finally:
    addon.unregister()
