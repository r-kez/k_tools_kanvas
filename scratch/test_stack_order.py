"""The item list is the stacking order: top of the list in front. Images and shapes mix
in one stack (drawing and picking), frames and groups carry their content, items move
with Move in Stack (Page Up / Page Down, buttons, Alt+wheel), new items come in at the
top, and boards saved before keep their look."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas import _migrate_stack_order
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.operators.ops_stack import move_in_stack
from k_tools_kanvas.utils.gpu import sync_kanvas_frames
from k_tools_kanvas.utils.item_geometry import layer_draw_indices, stack_order


def names(settings, indices):
    return [settings.images[i].name for i in indices]


def by_name(settings, name):
    return next(item for item in settings.images if item.name == name)


def list_names(settings):
    return names(settings, stack_order(settings))


def select(settings, wanted):
    for item in settings.images:
        item.is_selected = item.name in wanted


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Stack', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        context = bpy.context
        picture = bpy.data.images.new('picture', 100, 100)
        image = settings.images.add()
        image.item_type, image.name, image.image_data = 'IMAGE', 'Photo', picture
        image.item_id, image.z_index, image.location = 'photo', 1, (0.0, 0.0)
        # A new shape comes in at the top: in front of the image.
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(0.0, 0.0),
                                           size=(60.0, 60.0)) == {'FINISHED'}
        shape = settings.images[-1]
        shape.name = 'Box'
        sync_kanvas_frames(tree, settings)
        assert list_names(settings) == ['Box', 'Photo']
        assert [item.name for item in settings.images] == ['Box', 'Photo'], 'list = stack'
        assert names(settings, layer_draw_indices(settings)) == ['Photo', 'Box'], 'back first'
        helper = KanvasInteractionHelpers()
        assert helper._find_image_at_pos(context, (0.0, 0.0))[1].name == 'Box'

        # Down one step: the shape goes behind the image, in drawing and in picking.
        select(settings, {'Box'})
        assert bpy.ops.kanvas.move_in_stack(direction='DOWN') == {'FINISHED'}
        assert [item.name for item in settings.images] == ['Photo', 'Box']
        assert names(settings, layer_draw_indices(settings)) == ['Box', 'Photo']
        assert helper._find_image_at_pos(context, (0.0, 0.0))[1].name == 'Photo'
        assert by_name(settings, 'Box').is_selected, 'the selection stays'
        assert bpy.ops.kanvas.move_in_stack(direction='DOWN') == {'CANCELLED'}, 'already last'
        assert bpy.ops.kanvas.move_in_stack(direction='UP') == {'FINISHED'}
        assert list_names(settings) == ['Box', 'Photo']

        # Several items: top, bottom and one step keep their order among themselves.
        for name in ('C', 'D', 'E'):
            item = settings.images.add()
            item.item_type, item.name, item.image_data = 'IMAGE', name, picture
            item.item_id, item.location = name, (500.0, 0.0)
            item.z_index = max(other.z_index for other in settings.images) + 1
        assert list_names(settings) == ['E', 'D', 'C', 'Box', 'Photo']
        select(settings, {'Box', 'Photo'})
        assert move_in_stack(settings, [by_name(settings, 'Box'), by_name(settings, 'Photo')], 'TOP')
        assert list_names(settings) == ['Box', 'Photo', 'E', 'D', 'C']
        assert move_in_stack(settings, [by_name(settings, 'Box'), by_name(settings, 'Photo')], 'DOWN')
        assert list_names(settings) == ['E', 'Box', 'Photo', 'D', 'C'], (list_names(settings), [(i.name, i.z_index) for i in settings.images])
        assert move_in_stack(settings, [by_name(settings, 'E')], 'BOTTOM')
        assert list_names(settings) == ['Box', 'Photo', 'D', 'C', 'E']

        # A group keeps the place of its front member, and moves with its content.
        select(settings, {'D', 'C'})
        assert bpy.ops.kanvas.group_items() == {'FINISHED'}
        group = next(item for item in settings.images if item.item_type == 'FRAME')
        group_name = group.name
        assert list_names(settings) == ['Box', 'Photo', group_name, 'D', 'C', 'E']
        assert [item.name for item in settings.images] == list_names(settings)
        assert move_in_stack(settings, [by_name(settings, group_name)], 'TOP')
        assert list_names(settings) == [group_name, 'D', 'C', 'Box', 'Photo', 'E']
        layers = names(settings, layer_draw_indices(settings))
        assert layers.index('D') > layers.index('Photo'), 'the group content is now in front'
        # Inside the group, items move among themselves only.
        assert move_in_stack(settings, [by_name(settings, 'C')], 'TOP')
        assert list_names(settings) == [group_name, 'C', 'D', 'Box', 'Photo', 'E']

        # The shortcuts: Page Up / Page Down, Shift for front / back.
        kc = context.window_manager.keyconfigs.addon
        items = [item for km in kc.keymaps for item in km.keymap_items
                 if item.idname == 'kanvas.move_in_stack']
        found = {(item.type, item.shift, item.properties.direction) for item in items}
        assert found >= {('PAGE_UP', False, 'UP'), ('PAGE_DOWN', False, 'DOWN'),
                         ('PAGE_UP', True, 'TOP'), ('PAGE_DOWN', True, 'BOTTOM')}, found

        # Boards saved before: frames had layer 0 and would sink with their content.
        old = settings.images.add()
        old.item_type, old.name, old.item_id = 'FRAME', 'Old frame', 'old'
        old.frame_node_name = 'old_frame'
        inside = settings.images.add()
        inside.item_type, inside.name, inside.image_data = 'IMAGE', 'Inside', picture
        inside.item_id, inside.parent_frame = 'inside', 'old_frame'
        inside.z_index = 1000
        old = by_name(settings, 'Old frame')
        old.z_index = 0
        settings.stack_version = 0
        assert list_names(settings)[-2:] == ['Old frame', 'Inside']
        _migrate_stack_order(settings)
        assert settings.stack_version == 1 and by_name(settings, 'Old frame').z_index == 1000
        assert list_names(settings)[:2] == ['Old frame', 'Inside']
        _migrate_stack_order(settings)   # only once
        assert by_name(settings, 'Old frame').z_index == 1000

    print('STACK ORDER PASS')
finally:
    addon.unregister()
