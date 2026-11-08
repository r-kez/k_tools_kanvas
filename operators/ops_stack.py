"""Move items up and down the stack: the item list, top of the list in front."""

import bpy

from ..utils.kanvas_data import get_settings
from .kanvas_context import KanvasTreeOnly

DIRECTIONS = (
    ('UP', 'Up', 'One step towards the front (up the list)'),
    ('DOWN', 'Down', 'One step towards the back (down the list)'),
    ('TOP', 'To Front', 'In front of everything at the same level (top of the list)'),
    ('BOTTOM', 'To Back', 'Behind everything at the same level (bottom of the list)'),
)


def move_in_stack(settings, items, direction):
    """Move items among their siblings (items with the same frame or group).

    A step passes one sibling that is not moving; several selected items keep their
    order among themselves. Returns True when the order changed.
    """
    from ..utils.item_geometry import siblings_of
    ids = {item.item_id for item in items}
    changed = False
    done = set()
    frames = {other.frame_node_name for other in settings.images if other.item_type == 'FRAME'}
    for item in items:
        parent = item.parent_frame if item.parent_frame in frames else ''
        if parent in done:
            continue   # each level moves once, with all its moving items together
        done.add(parent)
        siblings = siblings_of(settings, item)
        order = list(siblings)
        moving = [sibling for sibling in order if sibling.item_id in ids]
        still = [sibling for sibling in order if sibling.item_id not in ids]
        if direction == 'TOP':
            new = moving + still
        elif direction == 'BOTTOM':
            new = still + moving
        else:
            new = list(order)
            indices = range(1, len(new)) if direction == 'UP' else range(len(new) - 2, -1, -1)
            step = -1 if direction == 'UP' else 1
            for index in indices:
                if new[index].item_id in ids and new[index + step].item_id not in ids:
                    new[index], new[index + step] = new[index + step], new[index]
        if [s.item_id for s in new] == [s.item_id for s in order]:
            continue
        # Only the order among siblings matters: number them from the back.
        count = len(new)
        for rank, sibling in enumerate(new):
            if sibling.z_index != count - rank:
                sibling.z_index = count - rank
        changed = True
    return changed


def stack_targets(settings):
    """The selected, unlocked items; or the active item when nothing is selected."""
    targets = [item for item in settings.images if item.is_selected and not item.is_locked]
    if not targets and 0 <= settings.active_image_index < len(settings.images):
        active = settings.images[settings.active_image_index]
        if not active.is_locked:
            targets = [active]
    return targets


class KANVAS_OT_MoveInStack(KanvasTreeOnly, bpy.types.Operator):
    """Move the selected items towards the front or the back."""
    bl_idname = 'kanvas.move_in_stack'
    bl_label = 'Move in Stack'
    bl_description = ('Move the selected items up the list (to the front of the canvas) or down '
                      'it (to the back), among the items of the same frame or group')
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(  # type: ignore
        name='Direction',
        items=[(identifier, label, description) for identifier, label, description in DIRECTIONS],
        default='UP',
    )

    @classmethod
    def description(cls, context, properties):
        return next(description for identifier, _, description in DIRECTIONS
                    if identifier == properties.direction)

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return settings is not None and bool(stack_targets(settings))

    def execute(self, context):
        settings = get_settings(context)
        if not move_in_stack(settings, stack_targets(settings), self.direction):
            return {'CANCELLED'}
        from ..utils.gpu import sync_kanvas_frames
        tree = settings.id_data
        selected = {item.item_id for item in settings.images if item.is_selected}
        active_id = (settings.images[settings.active_image_index].item_id
                     if 0 <= settings.active_image_index < len(settings.images) else '')
        sync_kanvas_frames(tree, settings)   # the list follows the new order
        if active_id:
            settings.active_image_index = next(
                (i for i, item in enumerate(settings.images) if item.item_id == active_id), -1)
        for item in settings.images:
            if item.is_selected != (item.item_id in selected):
                item.is_selected = item.item_id in selected
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}
