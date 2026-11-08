"""Alt+G / Alt+R / Alt+S with a group selected: the group has no transform of its own,
so Alt+G moves the group and its members together (the group's middle lands on the
origin, the box still fits) and Alt+R / Alt+S reset each member where it stands.
A loose item still resets alone, and its parent frame refits."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import reset_item_transforms


def close(a, b, tol=0.05):
    return math.dist(a, b) < tol


def by_id(settings, item_id):
    return next(item for item in settings.images if item.item_id == item_id)


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Reset transforms', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(500.0, 300.0),
                                           size=(100.0, 50.0)) == {'FINISHED'}
        left_id = settings.images[-1].item_id
        assert bpy.ops.kanvas.create_shape(kind='TRIANGLE', location=(800.0, 300.0),
                                           size=(60.0, 60.0)) == {'FINISHED'}
        right_id = settings.images[-1].item_id
        by_id(settings, left_id).rotation = 30.0
        by_id(settings, right_id).scale_xy = (2.0, 2.0)
        for item in settings.images:
            item.is_selected = item.item_id in {left_id, right_id}
        assert bpy.ops.kanvas.group_items() == {'FINISHED'}
        group = next(item for item in settings.images if item.item_type == 'FRAME')
        group_id = group.item_id

        def offsets():
            g = by_id(settings, group_id)
            return {i: (by_id(settings, i).location[0] - g.location[0],
                        by_id(settings, i).location[1] - g.location[1])
                    for i in (left_id, right_id)}

        before = offsets()
        size = (group.frame_width, group.frame_height)

        # --- Alt+G -------------------------------------------------------------------------
        assert reset_item_transforms(context, settings, group, 'RESET_MOVE')
        group = by_id(settings, group_id)
        middle = (group.location[0] + group.frame_width / 2,
                  group.location[1] - group.frame_height / 2)
        assert close(middle, (0.0, 0.0)), middle
        after = offsets()
        assert all(close(before[i], after[i]) for i in before), (before, after)
        assert close(size, (group.frame_width, group.frame_height)), 'the box still fits'
        assert not reset_item_transforms(context, settings, group, 'RESET_MOVE'), \
            'nothing left to reset'

        # --- Alt+R / Alt+S reset the members where they stand -----------------------------
        spot = tuple(by_id(settings, left_id).location)
        assert reset_item_transforms(context, settings, group, 'RESET_ROTATE')
        assert by_id(settings, left_id).rotation == 0.0
        assert close(spot, tuple(by_id(settings, left_id).location))
        assert by_id(settings, group_id).rotation == 0.0
        assert reset_item_transforms(context, settings, group, 'RESET_SCALE')
        assert tuple(by_id(settings, right_id).scale_xy) == (1.0, 1.0)
        assert by_id(settings, group_id).is_selected, 'the group stays selected'

        # --- A loose item alone; its group refits ----------------------------------------
        for item in settings.images:
            item.is_selected = False
        left = by_id(settings, left_id)
        assert reset_item_transforms(context, settings, left, 'RESET_MOVE')
        assert close(tuple(by_id(settings, left_id).location), (0.0, 0.0))
        right_spot = tuple(by_id(settings, right_id).location)
        assert reset_item_transforms(context, settings, by_id(settings, right_id), 'RESET_MOVE')
        assert close(tuple(by_id(settings, right_id).location), (0.0, 0.0))
        assert not close(right_spot, (0.0, 0.0))

        # --- The context menu's Reset Transform follows the same rules -------------------
        group = by_id(settings, group_id)
        group.location = (group.location[0] + 700.0, group.location[1])
        for item_id in (left_id, right_id):
            item = by_id(settings, item_id)
            item.location = (item.location[0] + 700.0, item.location[1])
        before = offsets()
        for item in settings.images:
            item.is_selected = item.item_id == group_id
        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_id == group_id)
        assert bpy.ops.kanvas.reset_transform(transform_type='LOCATION') == {'FINISHED'}
        after = offsets()
        assert all(close(before[i], after[i]) for i in before), 'menu reset keeps members'

    print('test_reset_transforms: OK')
finally:
    addon.unregister()
