"""Headless checks for nested Kanvas frame relationships and movement."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.ui import KANVAS_UL_image_list
from k_tools_kanvas.utils.gpu import (attach_items_to_frame, frame_descendants,
    frame_has_images,
    get_frame, get_item_by_id, sync_kanvas_frames, update_frame_bounds,
    visible_frames_in_draw_order)

addon.register()
try:
    tree = bpy.data.node_groups.new('Nested frames test', 'KanvasNodeTree')
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        settings = get_settings(bpy.context)
        bpy.context.tool_settings.use_snap_node = False
        data = bpy.data.images.new('nested-test', 40, 40)
        for name, loc in [('Outer', (0, 200)), ('Middle', (30, 140)),
                          ('Inner', (60, 80)), ('Other', (500, 200))]:
            item = settings.images.add()
            item.item_type = 'FRAME'
            item.frame_node_name = name
            item.name = name
            item.location = loc
            item.frame_width = 140
            item.frame_height = 100
            item.auto_resize = False
        image = settings.images.add()
        image.name = 'Picture'
        image.image_data = data
        image.location = (100, 20)
        sync_kanvas_frames(tree, settings)
        assert attach_items_to_frame(tree, settings, [get_frame(settings, 'Middle')], 'Outer')
        assert attach_items_to_frame(tree, settings, [get_frame(settings, 'Inner')], 'Middle')
        assert attach_items_to_frame(tree, settings, [image], 'Inner')
        sync_kanvas_frames(tree, settings)
        assert [item.name for item in settings.images] == [
            'Outer', 'Middle', 'Inner', 'Picture', 'Other']
        assert [item.name for item in frame_descendants(settings, 'Outer')] == [
            'Middle', 'Inner', 'Picture']

        outer = get_frame(settings, 'Outer')
        middle = get_frame(settings, 'Middle')
        inner = get_frame(settings, 'Inner')
        image = next(item for item in settings.images if item.name == 'Picture')
        assert all(frame_has_images(settings, frame.frame_node_name)
                   and frame.auto_resize for frame in (outer, middle, inner))
        assert not attach_items_to_frame(tree, settings, [outer], 'Inner')
        assert not attach_items_to_frame(tree, settings, [outer], 'Outer')
        assert outer.parent_frame == ''
        assert [frame.name for _, frame in visible_frames_in_draw_order(settings)][:3] == [
            'Outer', 'Middle', 'Inner']

        outer.list_collapsed = True
        flags, _ = KANVAS_UL_image_list.filter_items(
            SimpleNamespace(bitflag_filter_item=1), bpy.context, settings, 'images')
        assert flags == [1, 0, 0, 0, 1], flags
        outer.list_collapsed = False
        middle.list_collapsed = True
        flags, _ = KANVAS_UL_image_list.filter_items(
            SimpleNamespace(bitflag_filter_item=1), bpy.context, settings, 'images')
        assert flags == [1, 1, 0, 0, 1], flags
        middle.list_collapsed = False

        # An auto-sized parent follows the geometry of its nested child.
        outer.auto_resize = True
        middle.auto_resize = True
        inner.auto_resize = True
        update_frame_bounds(tree, settings, 'Inner')
        assert outer.location[0] < middle.location[0] < inner.location[0]
        outer_bounds = (tuple(outer.location), outer.frame_width, outer.frame_height)
        inner_bounds = (tuple(inner.location), inner.frame_width, inner.frame_height)
        image.scale_master = 2
        assert outer.frame_width > outer_bounds[1]
        image.scale_master = 1
        assert (tuple(outer.location), outer.frame_width, outer.frame_height) == outer_bounds
        assert (tuple(inner.location), inner.frame_width, inner.frame_height) == inner_bounds

        # A sibling keeps the outer frame anchored while its nested child moves.
        anchor = settings.images.add()
        anchor.name = 'Outer anchor'
        anchor.image_data = data
        anchor.location = (outer.location[0] + 45, outer.location[1] - 110)
        attach_items_to_frame(tree, settings, [anchor], 'Outer')
        for item in settings.images:
            item.is_selected = item.name == 'Inner'
        live_outer = (tuple(outer.location), outer.frame_width, outer.frame_height)
        live_middle = (tuple(middle.location), middle.frame_width, middle.frame_height)
        live_inner = tuple(inner.location)
        live_drag = KanvasInteractionHelpers()
        live_drag._start_frame_drag(bpy.context, inner, 'MOVE', live_inner)
        live_drag._update_drag(bpy.context, live_inner[0] + 180, live_inner[1] - 30)
        assert outer.frame_width > live_outer[1], 'Parent must resize before mouse release'
        assert tuple(middle.location) != live_middle[0]
        live_drag._cancel_drag(bpy.context)
        assert (tuple(outer.location), outer.frame_width, outer.frame_height) == live_outer
        assert (tuple(middle.location), middle.frame_width, middle.frame_height) == live_middle
        assert tuple(inner.location) == live_inner

        picture = next(item for item in settings.images if item.name == 'Picture')
        before = tuple(picture.location), tuple(inner.location), tuple(middle.location)
        outer.is_selected = True
        inner.is_selected = True
        helper = KanvasInteractionHelpers()
        helper._start_frame_drag(bpy.context, outer, 'MOVE', (0, 200))
        helper._update_drag(bpy.context, 20, 190)
        assert tuple(picture.location) == (before[0][0] + 20, before[0][1] - 10)
        assert tuple(inner.location) == (before[1][0] + 20, before[1][1] - 10)
        assert tuple(middle.location) == (before[2][0] + 20, before[2][1] - 10)
        helper._cancel_drag(bpy.context)
        assert tuple(picture.location) == before[0]
        assert tuple(inner.location) == before[1]

        for item in settings.images:
            item.is_selected = (item.name == 'Middle')
        assert bpy.ops.kanvas.detach_from_frame() == {'FINISHED'}
        assert get_frame(settings, 'Middle').parent_frame == ''
        assert get_frame(settings, 'Inner').parent_frame == 'Middle'
        assert bpy.ops.kanvas.attach_to_frame(frame_name='Outer') == {'FINISHED'}
        assert get_frame(settings, 'Middle').parent_frame == 'Outer'

        for item in settings.images:
            item.is_selected = item.name in {'Middle', 'Other'}
        assert bpy.ops.kanvas.attach_to_frame(frame_name='Other') == {'FINISHED'}
        assert get_frame(settings, 'Middle').parent_frame == 'Other'
        for item in settings.images:
            item.is_selected = item.name == 'Middle'
        assert bpy.ops.kanvas.attach_to_frame(frame_name='Outer') == {'FINISHED'}

        # Dragging a subtree over another frame reparents only its root.
        middle = get_frame(settings, 'Middle')
        other = get_frame(settings, 'Other')
        other.auto_resize = False
        other.location = (700, 300)
        other.frame_width = 180
        other.frame_height = 160
        old_middle = tuple(middle.location)
        old_picture = tuple(next(item for item in settings.images if item.name == 'Picture').location)
        helper = KanvasInteractionHelpers()
        helper._start_frame_drag(bpy.context, middle, 'MOVE', old_middle)
        helper._update_drag(bpy.context, 760, 240)
        assert settings.drop_target_frame == 'Other', settings.drop_target_frame
        helper._stop_drag(bpy.context)
        assert get_frame(settings, 'Middle').parent_frame == 'Other'
        moved_picture = next(item for item in settings.images if item.name == 'Picture')
        assert tuple(moved_picture.location) != old_picture
        assert get_frame(settings, 'Inner').parent_frame == 'Middle'

        # Removing a middle frame releases its direct child, preserving its contents.
        for item in settings.images:
            item.is_selected = item.name == 'Middle'
        middle_index = next(i for i, item in enumerate(settings.images) if item.name == 'Middle')
        assert bpy.ops.kanvas.remove_image(index=middle_index) == {'FINISHED'}
        assert get_frame(settings, 'Middle') is None
        assert get_frame(settings, 'Inner').parent_frame == ''
        assert next(item for item in settings.images if item.name == 'Picture').parent_frame == 'Inner'

        # Wrapping an existing frame keeps the established subtree intact.
        inner = get_frame(settings, 'Inner')
        inner_location = tuple(inner.location)
        for item in settings.images:
            item.is_selected = item.name == 'Inner'
        assert bpy.ops.kanvas.create_frame() == {'FINISHED'}
        inner = get_frame(settings, 'Inner')
        wrapper = get_frame(settings, inner.parent_frame)
        assert wrapper and tuple(inner.location) == inner_location
        assert next(item for item in settings.images if item.name == 'Picture').parent_frame == 'Inner'

        # Existing Blender NodeFrame nesting converts without losing world positions.
        native_parent = tree.nodes.new('NodeFrame')
        native_parent.name = 'Native Parent'
        native_parent.location = (1000, 100)
        native_child = tree.nodes.new('NodeFrame')
        native_child.name = 'Native Child'
        native_child.parent = native_parent
        native_child.location = (50, -30)
        sync_kanvas_frames(tree, settings)
        assert get_frame(settings, 'Native Child').parent_frame == 'Native Parent'
        assert tuple(get_frame(settings, 'Native Child').location) == (1050, 70)

        for item in settings.images:
            item.is_selected = False
        names, ids, frame_ids = [], [], []
        for _ in range(3):
            assert bpy.ops.kanvas.create_frame() == {'FINISHED'}
            created = next(item for item in settings.images
                           if item.item_type == 'FRAME' and item.is_selected)
            names.append(created.name)
            ids.append(created.item_id)
            frame_ids.append(created.frame_node_name)
            created.is_selected = False
        assert names == ['Kanvas Frame.001', 'Kanvas Frame.002', 'Kanvas Frame.003'], names
        assert len(set(ids)) == 3 and all(ids)
        assert len(set(frame_ids)) == 3 and all(frame_ids)
        print('Nested frame checks passed')
finally:
    addon.unregister()
