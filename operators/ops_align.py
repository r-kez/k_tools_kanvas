"""Align and distribute selected Kanvas images and text cards."""

import bpy
from ..utils.kanvas_data import get_settings

from .kanvas_context import KanvasTreeOnly
from ..utils.item_geometry import item_bounds


ALIGN_MODES = (
    ('LEFT', 'Left', 'Align left edges'),
    ('CENTER_X', 'Horizontal Center', 'Align horizontal centers'),
    ('RIGHT', 'Right', 'Align right edges'),
    ('TOP', 'Top', 'Align top edges'),
    ('CENTER_Y', 'Vertical Center', 'Align vertical centers'),
    ('BOTTOM', 'Bottom', 'Align bottom edges'),
)

ALIGN_ICONS = {
    'LEFT': 'layout-align-left',
    'CENTER_X': 'layout-align-center',
    'RIGHT': 'layout-align-right',
    'TOP': 'layout-align-top',
    'CENTER_Y': 'layout-align-middle',
    'BOTTOM': 'layout-align-bottom',
}


def align_items(items, mode):
    footprints = [(item, item_bounds(item)) for item in items]
    footprints = [(item, bounds) for item, bounds in footprints if bounds is not None]
    if len(footprints) < 2:
        return 0
    left = min(bounds[0] for _, bounds in footprints)
    bottom = min(bounds[1] for _, bounds in footprints)
    right = max(bounds[2] for _, bounds in footprints)
    top = max(bounds[3] for _, bounds in footprints)
    target = {
        'LEFT': left,
        'CENTER_X': (left + right) * 0.5,
        'RIGHT': right,
        'TOP': top,
        'CENTER_Y': (bottom + top) * 0.5,
        'BOTTOM': bottom,
    }[mode]
    for item, bounds in footprints:
        own = {
            'LEFT': bounds[0],
            'CENTER_X': (bounds[0] + bounds[2]) * 0.5,
            'RIGHT': bounds[2],
            'TOP': bounds[3],
            'CENTER_Y': (bounds[1] + bounds[3]) * 0.5,
            'BOTTOM': bounds[1],
        }[mode]
        offset = target - own
        if mode in {'LEFT', 'CENTER_X', 'RIGHT'}:
            item.location[0] += offset
        else:
            item.location[1] += offset
    return len(footprints)


def distribute_items(items, axis):
    """Even edge gaps, expanding around the selection center when needed."""
    footprints = [(item, item_bounds(item)) for item in items]
    footprints = [(item, bounds) for item, bounds in footprints if bounds is not None]
    if len(footprints) < 3:
        return 0, 'Select at least three images or cards.'

    low, high, coordinate = (0, 2, 0) if axis == 'HORIZONTAL' else (1, 3, 1)
    first = min(footprints, key=lambda entry: entry[1][low])
    last = max(footprints, key=lambda entry: entry[1][high])
    middle = sorted((entry for entry in footprints if entry is not first and entry is not last),
                    key=lambda entry: (entry[1][low] + entry[1][high]) * 0.5)
    ordered = [first, *middle, last] if first is not last else footprints
    available = last[1][high] - first[1][low]
    occupied = sum(bounds[high] - bounds[low] for _, bounds in ordered)
    gap = (available - occupied) / (len(ordered) - 1)
    if gap < -1e-5 or first is last:
        # Preserve spatial order and open a useful gap even for fully stacked
        # items. Keep the original selection center and the other axis intact.
        ordered = sorted(footprints,
                         key=lambda entry: (entry[1][low] + entry[1][high]) * 0.5)
        gap = 20.0
        center = (first[1][low] + last[1][high]) * 0.5
        next_edge = center - (occupied + gap * (len(ordered) - 1)) * 0.5
        for item, bounds in ordered:
            item.location[coordinate] += next_edge - bounds[low]
            next_edge += bounds[high] - bounds[low] + gap
        return len(ordered) - 2, ''

    next_edge = first[1][high] + max(0.0, gap)
    for item, bounds in middle:
        item.location[coordinate] += next_edge - bounds[low]
        next_edge += bounds[high] - bounds[low] + gap
    return len(middle), ''


class KANVAS_OT_AlignItems(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.align_items'
    bl_label = 'Align Kanvas Items'
    bl_description = 'Align selected unlocked items along the chosen edge or center'
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(name='Align', items=ALIGN_MODES, default='CENTER_X')  # type: ignore

    @classmethod
    def description(cls, context, properties):
        return next((description for mode, _, description in ALIGN_MODES
                     if mode == properties.mode), "Align selected Kanvas items")

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return sum(1 for item in settings.images
                   if item.is_selected and item.show_in_editor and not item.is_locked
                   and item.item_type in {'IMAGE', 'TEXT'}
                   and item_bounds(item) is not None) >= 2

    def execute(self, context):
        items = [item for item in get_settings(context).images
                 if item.is_selected and item.show_in_editor and not item.is_locked
                 and item.item_type in {'IMAGE', 'TEXT'}]
        before = [tuple(item.location) for item in items]
        if align_items(items, self.mode) < 2:
            return {'CANCELLED'}
        if all(tuple(item.location) == old for item, old in zip(items, before)):
            return {'CANCELLED'}
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_DistributeItems(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.distribute_items'
    bl_label = 'Distribute Kanvas Items'
    bl_description = 'Space selected unlocked items evenly along the chosen axis'
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(  # type: ignore
        name='Direction',
        items=(('HORIZONTAL', 'Horizontal', 'Equal horizontal gaps'),
               ('VERTICAL', 'Vertical', 'Equal vertical gaps')),
        default='HORIZONTAL',
    )

    align_centers: bpy.props.BoolProperty(  # type: ignore
        name='Align Centers',
        description='Align centers into a row or column while distributing',
        default=True,
    )

    @classmethod
    def description(cls, context, properties):
        return ('Distribute selected images and cards with equal spaces '
                f'{properties.axis.lower()}ly')

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return sum(1 for item in settings.images
                   if item.is_selected and item.show_in_editor and not item.is_locked
                   and item.item_type in {'IMAGE', 'TEXT'}
                   and item_bounds(item) is not None) >= 3

    def execute(self, context):
        items = [item for item in get_settings(context).images
                 if item.is_selected and item.show_in_editor and not item.is_locked
                 and item.item_type in {'IMAGE', 'TEXT'}]
        before = [tuple(item.location) for item in items]
        moved, reason = distribute_items(items, self.axis)
        if reason:
            self.report({'WARNING'}, reason)
            return {'CANCELLED'}
        if self.align_centers:
            align_items(items, 'CENTER_Y' if self.axis == 'HORIZONTAL' else 'CENTER_X')
        if all(tuple(item.location) == old for item, old in zip(items, before)):
            return {'CANCELLED'}
        context.area.tag_redraw()
        self.report({'INFO'}, f'Distributed {moved + 2} items')
        return {'FINISHED'}
