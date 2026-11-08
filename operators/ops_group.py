"""Group and ungroup Kanvas items (Ctrl+G, Ctrl+Shift+G).

A group is a frame item with `frame_is_group` set: it keeps its members together
without drawing a frame. Groups never nest. Grouping items that already belong to a
group adds them to it instead of creating a subgroup.
"""

import uuid

import bpy

from ..utils.gpu import (frame_descendants, get_frame, is_group, owning_group,
                         sync_kanvas_frames, update_frame_bounds)
from ..utils.kanvas_data import get_settings, unique_item_name
from .kanvas_context import KanvasTreeOnly
from .ops_frame import _selection_roots, kanvas_tree


def _select_only(settings, selected_ids, active_id):
    from ..properties import suspend_selection_updates
    with suspend_selection_updates():
        for item in settings.images:
            item.is_selected = item.item_id in selected_ids
        settings.active_image_index = next(
            (i for i, item in enumerate(settings.images) if item.item_id == active_id), -1)


def group_selection(context, settings):
    """Group the selected items. Returns the group's item_id, or '' when nothing was done."""
    tree = kanvas_tree(context)
    selected = [item for item in settings.images
                if item.is_selected and not item.is_locked and item.show_in_editor]
    groups, loose = [], []
    for item in selected:
        group = item if is_group(item) else owning_group(settings, item)
        if group is not None:
            if all(group.item_id != other.item_id for other in groups):
                groups.append(group)
        else:
            loose.append(item)
    loose = _selection_roots(settings, loose)
    # Groups never nest, not even through a frame that holds another group.
    loose = [item for item in loose
             if not (item.item_type == 'FRAME' and any(
                 is_group(child) for child in frame_descendants(settings, item.frame_node_name)))]
    if len(groups) + len(loose) < 2:
        return ''

    if groups:
        target = groups[0]
        target_name = target.frame_node_name
        old_parents = {group.parent_frame for group in groups[1:] if group.parent_frame}
        for other in groups[1:]:
            for child in settings.images:
                if child.parent_frame == other.frame_node_name:
                    child.parent_frame = target_name
        for other in groups[1:]:
            other.parent_frame = ''
        target_id = target.item_id
    else:
        parents = {item.parent_frame for item in loose}
        layer = max(item.z_index for item in loose)
        group = settings.images.add()
        group.z_index = layer
        group.item_id = uuid.uuid4().hex
        group.item_type = 'FRAME'
        group.frame_is_group = True
        group.frame_node_name = 'kanvas_' + uuid.uuid4().hex
        group.name = unique_item_name(settings, 'Group')
        group.auto_resize = True
        # Members that shared one frame keep it: the group joins that frame.
        group.parent_frame = parents.pop() if len(parents) == 1 else ''
        target_name = group.frame_node_name
        target_id = group.item_id
        old_parents = set()

    from ..properties import suspend_frame_geometry_updates
    with suspend_frame_geometry_updates():
        for item in loose:
            if item.parent_frame:
                old_parents.add(item.parent_frame)
            item.parent_frame = target_name
    target = next(item for item in settings.images if item.item_id == target_id)
    own_parent = target.parent_frame
    for name in old_parents - {target_name}:
        if get_frame(settings, name) is not None and name != own_parent:
            update_frame_bounds(tree, settings, name)
    update_frame_bounds(tree, settings, target_name)
    sync_kanvas_frames(tree, settings)
    _select_only(settings, {target_id}, target_id)
    return target_id


def ungroup_selection(context, settings):
    """Dissolve the selected groups (or the groups of selected members). Returns member IDs."""
    tree = kanvas_tree(context)
    groups = []
    for item in settings.images:
        if not item.is_selected or item.is_locked:
            continue
        group = item if is_group(item) else owning_group(settings, item)
        if group is not None and all(group.item_id != other.item_id for other in groups):
            groups.append(group)
    if not groups:
        return []
    group_ids = [group.item_id for group in groups]
    freed = []
    for group_id in group_ids:
        group = next((item for item in settings.images if item.item_id == group_id), None)
        if group is None:
            continue
        name, parent = group.frame_node_name, group.parent_frame
        for child in settings.images:
            if child.parent_frame == name:
                child.parent_frame = parent
                freed.append(child.item_id)
    for group_id in group_ids:
        index = next((i for i, item in enumerate(settings.images)
                      if item.item_id == group_id), -1)
        if index >= 0:
            settings.images.remove(index)
    if tree is not None:
        for frame in [item for item in settings.images if item.item_type == 'FRAME'
                      and not item.frame_is_group]:
            if any(child.item_id in freed and child.parent_frame == frame.frame_node_name
                   for child in settings.images):
                update_frame_bounds(tree, settings, frame.frame_node_name)
        sync_kanvas_frames(tree, settings)
    _select_only(settings, set(freed), freed[-1] if freed else '')
    return freed


class KANVAS_OT_GroupItems(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.group_items'
    bl_label = 'Group'
    bl_description = ('Keep the selected items together (Ctrl+G). Moving, locking and hiding the '
                      'group affects every member. Items that are already in a group join it')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = get_settings(context)
        if not group_selection(context, settings):
            self.report({'INFO'}, 'Select at least two items, or an item and a group')
            return {'CANCELLED'}
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_UngroupItems(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.ungroup_items'
    bl_label = 'Ungroup'
    bl_description = 'Dissolve the selected group and keep its members (Ctrl+Shift+G)'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = get_settings(context)
        if not ungroup_selection(context, settings):
            return {'CANCELLED'}
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}
