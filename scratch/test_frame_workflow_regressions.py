"""Focused Blender checks for selection and frame operations."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.utils.gpu import (find_frame_at_location, get_frame,
                                     sync_kanvas_frames, visible_frames_in_draw_order,
                                     ensure_item_ids, release_guard_active)


def item(settings, name):
    return next(entry for entry in settings.images if entry.name == name)


addon.register()
try:
    tree = bpy.data.node_groups.new('Frame workflow test', 'KanvasNodeTree')
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        settings = get_settings(bpy.context)
        image_data = bpy.data.images.new('frame-workflow-image', 40, 40)
        for name, x in [('A', -100), ('B', -50), ('C', 0)]:
            entry = settings.images.add()
            entry.name = name
            entry.image_data = image_data
            entry.location = (x, 0)

        for name, x, y in [('Back', -30, 80), ('Front', 0, 65)]:
            frame = settings.images.add()
            frame.item_type = 'FRAME'
            frame.name = name
            frame.frame_node_name = name
            frame.location = (x, y)
            frame.frame_width = 150
            frame.frame_height = 130
            frame.auto_resize = False

        for name in ('A', 'B'):
            item(settings, name).is_selected = True
        changed = bpy.ops.kanvas.attach_to_frame(frame_name='Back')
        assert changed == {'FINISHED'}, changed
        assert all(item(settings, n).parent_frame == 'Back' for n in ('A', 'B'))
        assert all(item(settings, n).is_selected for n in ('A', 'B'))

        changed = bpy.ops.kanvas.detach_from_frame()
        assert changed == {'FINISHED'}, changed
        assert all(item(settings, n).parent_frame == '' for n in ('A', 'B'))
        assert all(item(settings, n).is_selected for n in ('A', 'B'))
        released = item(settings, 'A')
        assert released.released_parent_frame == 'Back'
        assert release_guard_active(settings, released, (0, 0), margin=10)
        assert not release_guard_active(settings, released, (500, 500), margin=10)
        assert released.released_parent_frame == ''

        # One command also releases a selection spanning two different frames.
        item(settings, 'A').parent_frame = 'Back'
        item(settings, 'B').parent_frame = 'Front'
        assert bpy.ops.kanvas.detach_from_frame() == {'FINISHED'}
        assert all(item(settings, n).parent_frame == '' for n in ('A', 'B'))
        assert all(item(settings, n).is_selected for n in ('A', 'B'))

        # Reordering must not silently collapse a selection to the active item.
        for n in ('A', 'B'):
            item(settings, n).parent_frame = 'Back'
        settings.active_image_index = next(i for i, e in enumerate(settings.images) if e.name == 'A')
        item(settings, 'B').is_selected = True
        sync_kanvas_frames(tree, settings)
        assert all(item(settings, n).is_selected for n in ('A', 'B'))

        # Keep these frames empty for the fixed overlap hit test; frames with
        # images now use Auto Fit and therefore move to their content bounds.
        for n in ('A', 'B'):
            item(settings, n).parent_frame = ''
        for name, x, y in [('Back', -30, 80), ('Front', 0, 65)]:
            frame = item(settings, name)
            frame.auto_resize = False
            frame.location = (x, y)
            frame.frame_width = 150
            frame.frame_height = 130

        helper = KanvasInteractionHelpers()
        index, hit, part = helper._frame_hit(bpy.context, (10, 50))
        assert hit.name == 'Front' and part == 'MOVE', (index, hit.name, part)
        item(settings, 'Back').z_index = 2
        index, hit, part = helper._frame_hit(bpy.context, (10, 50))
        assert hit.name == 'Back', (index, hit.name, part)
        assert visible_frames_in_draw_order(settings)[-1][1].name == 'Back'

        # A tiny frame accepts a complete selected group through one drop point.
        small = get_frame(settings, 'Front')
        small.location = (500, 500)
        small.frame_width = 65
        small.frame_height = 65
        small.auto_resize = False
        assert find_frame_at_location(settings, (570, 480), margin=10) == small
        for n in ('A', 'B'):
            item(settings, n).parent_frame = ''
            item(settings, n).is_selected = True
        item(settings, 'A').location = (-100, 0)
        item(settings, 'B').location = (-300, 0)
        helper.keyboard_transform = False
        helper.start_drag(bpy.context, item(settings, 'A'), 'MOVE', (-100, 0))
        helper._update_drag(bpy.context, 510, 480)
        assert settings.drop_target_frame == 'Front'
        assert not (500 <= item(settings, 'B').location[0] <= 565)
        helper._stop_drag(bpy.context)
        assert all(item(settings, n).parent_frame == 'Front' for n in ('A', 'B'))
        assert all(item(settings, n).is_selected for n in ('A', 'B'))

        for n in ('A', 'B'):
            item(settings, n).parent_frame = ''
        item(settings, 'A').location = (-100, 0)
        item(settings, 'B').location = (-300, 0)
        helper.start_drag(bpy.context, item(settings, 'A'), 'MOVE', (-100, 0))
        helper._update_drag(bpy.context, 510, 480)
        helper._cancel_drag(bpy.context)
        assert settings.drop_target_frame == ''
        assert all(item(settings, n).parent_frame == '' for n in ('A', 'B'))
        assert tuple(item(settings, 'A').location) == (-100, 0)
        assert tuple(item(settings, 'B').location) == (-300, 0)

        # The collection may change slots while an image is being dragged.
        for entry in settings.images:
            entry.is_selected = entry.name == 'A'
        ensure_item_ids(settings)
        ids = [entry.item_id for entry in settings.images]
        assert len(ids) == len(set(ids)) and all(ids)
        helper.start_drag(bpy.context, item(settings, 'A'), 'MOVE', (-100, 0))
        index_a = next(i for i, entry in enumerate(settings.images) if entry.name == 'A')
        settings.images.move(index_a, len(settings.images) - 1)
        helper._update_drag(bpy.context, -80, 10)
        assert tuple(item(settings, 'A').location) == (-80, 10)
        assert tuple(item(settings, 'B').location) == (-300, 0)
        helper._cancel_drag(bpy.context)
        assert tuple(item(settings, 'A').location) == (-100, 0)

        # Two selected frames and their children move as a single group.
        bpy.context.tool_settings.use_snap_node = False
        settings.snap_grid = False
        back = item(settings, 'Back')
        front = item(settings, 'Front')
        back.auto_resize = False
        front.auto_resize = False
        item(settings, 'A').parent_frame = 'Back'
        item(settings, 'B').parent_frame = 'Front'
        for entry in settings.images:
            entry.is_selected = entry.item_type == 'FRAME'
        starts = {name: tuple(item(settings, name).location)
                  for name in ('Back', 'Front', 'A', 'B')}
        helper._start_frame_drag(bpy.context, back, 'MOVE', (0, 0))
        helper._update_drag(bpy.context, 30, -20)
        for name, original in starts.items():
            moved = tuple(item(settings, name).location)
            assert moved == (original[0] + 30, original[1] - 20), (name, moved)
        helper._cancel_drag(bpy.context)
        for name, original in starts.items():
            assert tuple(item(settings, name).location) == original

        print('Frame workflow regression checks passed')
finally:
    addon.unregister()
