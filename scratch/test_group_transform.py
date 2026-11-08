"""Rotating and scaling a group: every member turns or scales around the middle of the
group (there is no group transform of its own), cards move and scale but stay upright,
arrows follow, Esc puts everything back, and the group box fits the result."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_arrow import _create_arrow
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.utils.arrow_geometry import endpoint
from k_tools_kanvas.utils.item_geometry import item_bounds


def close(a, b, tol=0.05):
    return math.dist(a, b) < tol


def by_id(settings, item_id):
    return next(item for item in settings.images if item.item_id == item_id)


def turned(point, pivot, degrees):
    angle = math.radians(degrees)
    x, y = point[0] - pivot[0], point[1] - pivot[1]
    return (pivot[0] + x * math.cos(angle) - y * math.sin(angle),
            pivot[1] + x * math.sin(angle) + y * math.cos(angle))


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Group transform', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(0.0, 0.0),
                                           size=(100.0, 50.0)) == {'FINISHED'}
        left_id = settings.images[-1].item_id
        assert bpy.ops.kanvas.create_shape(kind='TRIANGLE', location=(300.0, 0.0),
                                           size=(60.0, 60.0)) == {'FINISHED'}
        right_id = settings.images[-1].item_id
        card = settings.images.add()
        card.item_type, card.item_id, card.name = 'TEXT', 'card', 'Note'
        card.location = (150.0, 200.0)
        card.text_width, card.text_height = 120.0, 60.0
        arrow = _create_arrow(settings, (0.0, 0.0))
        arrow.start_item_id, arrow.start_uv = right_id, (1.0, 0.5)
        arrow.end = (600.0, 400.0)
        for item in settings.images:
            item.is_selected = item.item_id in {left_id, right_id, 'card'}
        assert bpy.ops.kanvas.group_items() == {'FINISHED'}
        group = next(item for item in settings.images if item.item_type == 'FRAME')
        group_id = group.item_id
        assert group.is_selected and not any(by_id(settings, i).is_selected
                                             for i in (left_id, right_id, 'card'))

        helper = KanvasInteractionHelpers()
        members = helper._transform_items(settings, 'ROTATE')
        assert {item.item_id for item in members} == {left_id, right_id, 'card'}, \
            'rotating a group acts on its members, cards included'
        assert helper._transform_items(settings, 'MOVE') == [], 'moving drags the group box'
        group = by_id(settings, group_id)
        pivot = (group.location[0] + group.frame_width / 2,
                 group.location[1] - group.frame_height / 2)

        before = {i: tuple(by_id(settings, i).location) for i in (left_id, right_id, 'card')}
        tip = endpoint(settings, arrow, 'start')

        # --- Rotate 90 degrees ------------------------------------------------------------
        gesture = KanvasInteractionHelpers()
        gesture.keyboard_transform = True
        start = (pivot[0] + 100.0, pivot[1])
        gesture.start_drag(context, by_id(settings, left_id), 'ROTATE', start)
        assert close(gesture.selection_pivot, pivot), 'turns around the middle of the group'
        gesture._update_drag(context, pivot[0] + 70.0, pivot[1] + 70.0)
        gesture._update_drag(context, pivot[0], pivot[1] + 100.0)
        for item_id in (left_id, right_id):
            item = by_id(settings, item_id)
            assert close(tuple(item.location), turned(before[item_id], pivot, 90.0), 0.5), item_id
            assert abs(item.rotation - 90.0) < 0.5, item.rotation
        note = by_id(settings, 'card')
        assert close(tuple(note.location), turned(before['card'], pivot, 90.0), 0.5)
        assert note.rotation == 0.0, 'cards stay upright'
        assert close(endpoint(settings, arrow, 'start'), turned(tip, pivot, 90.0), 1.0), \
            'the arrow follows its shape'
        # Esc puts everything back.
        gesture._cancel_drag(context)
        for item_id, location in before.items():
            assert close(tuple(by_id(settings, item_id).location), location)
        assert by_id(settings, left_id).rotation == 0.0

        # --- Scale x2 ---------------------------------------------------------------------
        gesture = KanvasInteractionHelpers()
        gesture.keyboard_transform = True
        gesture.start_drag(context, by_id(settings, left_id), 'SCALE_U', start)
        gesture._update_drag(context, pivot[0] + 200.0, pivot[1])
        for item_id in (left_id, right_id, 'card'):
            item = by_id(settings, item_id)
            expected = (pivot[0] + (before[item_id][0] - pivot[0]) * 2.0,
                        pivot[1] + (before[item_id][1] - pivot[1]) * 2.0)
            assert close(tuple(item.location), expected, 0.5), item_id
        assert abs(by_id(settings, left_id).scale_master - 2.0) < 0.01
        assert abs(by_id(settings, 'card').text_scale - 2.0) < 0.01, 'cards scale by their size'
        gesture._stop_drag(context)
        # The group box fits the scaled content.
        group = by_id(settings, group_id)
        left, bottom, right, top = item_bounds(group)
        for item_id in (left_id, right_id, 'card'):
            l, b, r, t = item_bounds(by_id(settings, item_id))
            assert left <= l + 1e-3 and right >= r - 1e-3 and bottom <= b + 1e-3 and top >= t - 1e-3

        # Esc after scaling restores the card size too.
        gesture = KanvasInteractionHelpers()
        gesture.keyboard_transform = True
        gesture.start_drag(context, by_id(settings, left_id), 'SCALE_U', start)
        gesture._update_drag(context, pivot[0] + 50.0, pivot[1])
        gesture._cancel_drag(context)
        assert abs(by_id(settings, 'card').text_scale - 2.0) < 0.01

    print('GROUP TRANSFORM PASS')
finally:
    addon.unregister()
