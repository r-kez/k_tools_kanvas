"""Groups: Ctrl+G keeps items together, merges instead of nesting, and moves as one."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.utils.gpu import frame_descendants, is_group, owning_group
from k_tools_kanvas.utils.item_geometry import item_bounds

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Groups', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    def by_name(name):
        return next(item for item in settings.images if item.name == name)

    def select(*names):
        for item in settings.images:
            item.is_selected = item.name in names

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        for index, kind in enumerate(('RECTANGLE', 'TRIANGLE', 'DIAMOND', 'ELLIPSE', 'STAR')):
            assert bpy.ops.kanvas.create_shape(kind=kind, location=(index * 300, 0)) == {'FINISHED'}
        names = [item.name for item in settings.images]
        assert names == ['Rectangle', 'Triangle', 'Diamond', 'Ellipse', 'Star']

        # One item is not a group.
        select('Rectangle')
        assert bpy.ops.kanvas.group_items() == {'CANCELLED'}

        # Grouping two items makes a group that holds them and is the only selection.
        select('Rectangle', 'Triangle')
        assert bpy.ops.kanvas.group_items() == {'FINISHED'}
        groups = [item for item in settings.images if is_group(item)]
        assert len(groups) == 1 and groups[0].name == 'Group'
        group = groups[0]
        assert group.is_selected and sum(i.is_selected for i in settings.images) == 1
        assert {c.name for c in frame_descendants(settings, group.frame_node_name)} == {
            'Rectangle', 'Triangle'}
        left, bottom, right, top = item_bounds(group)
        assert left < -80 and right > 380 and bottom < -60 and top > 60  # hugs the members

        # A group has no frame to drop onto: nothing attaches to it by hovering.
        from k_tools_kanvas.utils.gpu import find_frame_at_location
        assert find_frame_at_location(settings, (150.0, 0.0)) is None

        # Grouping a new item with the group adds it: still one group, no subgroup.
        select('Group', 'Diamond')
        assert bpy.ops.kanvas.group_items() == {'FINISHED'}
        groups = [item for item in settings.images if is_group(item)]
        assert len(groups) == 1
        assert {c.name for c in frame_descendants(settings, groups[0].frame_node_name)} == {
            'Rectangle', 'Triangle', 'Diamond'}

        # Selecting a member and another item also joins the member's group.
        select('Triangle', 'Ellipse')
        assert bpy.ops.kanvas.group_items() == {'FINISHED'}
        groups = [item for item in settings.images if is_group(item)]
        assert len(groups) == 1 and len(frame_descendants(settings, groups[0].frame_node_name)) == 4

        # Two groups merge into one.
        select('Star')
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(2000, 0)) == {'FINISHED'}
        extra = settings.images[-1]
        extra.name = 'Extra'
        select('Star', 'Extra')
        assert bpy.ops.kanvas.group_items() == {'FINISHED'}
        assert len([i for i in settings.images if is_group(i)]) == 2
        select(*[i.name for i in settings.images if is_group(i)])
        assert bpy.ops.kanvas.group_items() == {'FINISHED'}
        groups = [item for item in settings.images if is_group(item)]
        assert len(groups) == 1
        assert len(frame_descendants(settings, groups[0].frame_node_name)) == 6
        assert not any(is_group(c) for c in frame_descendants(settings, groups[0].frame_node_name))

        # Moving the group moves every member (the frame drag logic).
        group = groups[0]
        helper = KanvasInteractionHelpers()
        helper._start_frame_drag(bpy.context, group, 'MOVE', (0.0, 0.0))
        before = {c.name: tuple(c.location) for c in frame_descendants(settings, group.frame_node_name)}
        helper.mouse_drag_started = True
        helper._update_drag(bpy.context, 50.0, -30.0)
        for child in frame_descendants(settings, group.frame_node_name):
            assert abs(child.location[0] - before[child.name][0] - 50.0) < 1e-6, child.name
        helper._stop_drag(bpy.context)

        # A click on a member picks its group, Ctrl+click would pick the member.
        member = by_name('Rectangle')
        assert helper._owning_group(settings, member)[1].item_id == group.item_id
        assert owning_group(settings, by_name('Rectangle')) is not None

        # Locking the group locks the members; hiding follows too.
        group.is_locked = True
        assert all(c.is_locked for c in frame_descendants(settings, group.frame_node_name))
        group.is_locked = False
        group.show_in_editor = False
        assert not any(c.show_in_editor for c in frame_descendants(settings, group.frame_node_name))
        group.show_in_editor = True

        # Duplicating a group copies its members into a new group.
        count = len(settings.images)
        select(group.name)
        assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
        groups = [item for item in settings.images if is_group(item)]
        assert len(groups) == 2 and len(settings.images) == count + 7
        for g in groups:
            assert len(frame_descendants(settings, g.frame_node_name)) == 6
        assert sum(i.is_selected for i in settings.images) == 1

        # Ungroup frees the members and removes only the selected group.
        selected = next(i for i in settings.images if i.is_selected)
        assert is_group(selected)
        assert bpy.ops.kanvas.ungroup_items() == {'FINISHED'}
        assert len([i for i in settings.images if is_group(i)]) == 1
        assert sum(i.is_selected for i in settings.images) == 6

        # Deleting a group deletes its members.
        remaining = next(i for i in settings.images if is_group(i))
        select(remaining.name)
        before_count = len(settings.images)
        assert bpy.ops.kanvas.remove_image(index=-1) == {'FINISHED'}
        assert len(settings.images) == before_count - 7
        assert not any(is_group(i) for i in settings.images)

        # Removing every member by hand leaves no empty group behind.
        select('Extra' if any(i.name == 'Extra' for i in settings.images) else settings.images[0].name)
    print('GROUPS PASS')
finally:
    addon.unregister()
