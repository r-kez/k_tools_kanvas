"""Associate checklist cards with images and their color regions."""

import uuid

import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils.kanvas_data import get_settings
from ..utils.checklist_links import checklist_image_pair


from ..utils.color_palette import SEQUENCE as _TASK_COLORS, color_for_index


def active_checklist(settings):
    index = settings.active_image_index
    if 0 <= index < len(settings.images):
        card = settings.images[index]
        if card.item_type == 'TEXT' and card.text_checklist:
            return card
    return None


def selected_images(settings):
    return [item for item in settings.images
            if item.item_type == 'IMAGE' and item.is_selected
            and not item.is_locked and item.image_data]


def is_associated(image, card_id):
    return any(link.card_id == card_id for link in image.checklist_associations)


def _reorder_card_regions(image, card):
    """Follow task order while keeping unrelated colors in their list slots."""
    task_order = {line.line_id: index for index, line in enumerate(card.text_lines)}
    slots = [index for index, region in enumerate(image.markup_regions)
             if region.checklist_card_id == card.item_id
             and region.checklist_line_id in task_order]
    if len(slots) < 2:
        return False
    collection = image.markup_regions
    active_id = (collection[image.markup_active_index].region_id
                 if 0 <= image.markup_active_index < len(collection) else '')
    ordered = sorted((collection[index] for index in slots),
                     key=lambda region: task_order[region.checklist_line_id])
    desired = [region.region_id for region in collection]
    for slot, region in zip(slots, ordered):
        desired[slot] = region.region_id
    current = [region.region_id for region in collection]
    if current == desired:
        return False
    for target, region_id in enumerate(desired):
        if current[target] == region_id:
            continue
        source = current.index(region_id, target + 1)
        collection.move(source, target)
        current.insert(target, current.pop(source))
    if active_id:
        image.markup_active_index = current.index(active_id)
    return True


def adopt_image_regions(card, image):
    """On linking: the colors the image already has become tasks of the checklist, with
    their name and color, so the paint is not left out. A color named like an existing
    task joins that task (a task with no color of its own takes the paint's color).
    Colors already linked to a checklist, or detached from one, are left alone. Returns
    how many tasks were added."""
    names = {}
    for line in card.text_lines:
        names.setdefault(line.value, []).append(line)
    claimed = set()
    added = 0
    for region in image.markup_regions:
        if region.checklist_card_id or region.checklist_origin_card_id:
            continue
        same = [line for line in names.get(region.name, ()) if line.as_pointer() not in claimed]
        if len(names.get(region.name, ())) == 1 and same:
            line = same[0]
            claimed.add(line.as_pointer())
            if not line.is_property_set('color'):
                line.color = tuple(region.color)
            continue
        if not region.name:
            continue
        empty = next((line for line in card.text_lines
                      if not line.value and line.as_pointer() not in claimed), None)
        line = empty or card.text_lines.add()
        line.line_id = line.line_id or uuid.uuid4().hex
        line.value = region.name
        line.color = tuple(region.color)
        claimed.add(line.as_pointer())
        added += 1
    return added


def remove_task(settings, card, index):
    """Remove a checklist task and the color it paints on every linked image, with that
    paint. The arrows that pointed at the task keep their place on the card. A checklist
    keeps at least one line, so its last task is only emptied."""
    from ..utils.arrow_geometry import endpoint, set_endpoint
    lines = card.text_lines
    line_id = lines[index].line_id
    if line_id:
        for arrow in settings.arrows:
            for side in ('start', 'end'):
                if getattr(arrow, side + '_line_id') == line_id:
                    set_endpoint(arrow, side, endpoint(settings, arrow, side))
        for image in settings.images:
            if image.item_type != 'IMAGE':
                continue
            doomed = [i for i, region in enumerate(image.markup_regions)
                      if region.checklist_card_id == card.item_id
                      and region.checklist_line_id == line_id]
            for i in reversed(doomed):
                image.markup_regions.remove(i)
            if doomed:
                image.markup_active_index = max(
                    0, min(image.markup_active_index, len(image.markup_regions) - 1))
                image.markup_revision += 1
    if len(lines) == 1:
        lines[0].value = ''
        lines[0].line_id = ''
    else:
        lines.remove(index)


def sync_checklist_regions(settings, image):
    """Add missing task colors and refresh names without replacing paint."""
    cards = {item.item_id: item for item in settings.images
             if item.item_type == 'TEXT' and item.text_checklist}
    changed = False
    region_ids = set()
    for region in image.markup_regions:
        if not region.region_id or region.region_id in region_ids:
            region.region_id = uuid.uuid4().hex
            changed = True
        region_ids.add(region.region_id)
    for link in image.checklist_associations:
        card = cards.get(link.card_id)
        if card is None:
            continue
        name_counts = {}
        for line in card.text_lines:
            name_counts[line.value] = name_counts.get(line.value, 0) + 1
        for task_index, line in enumerate(card.text_lines):
            if not line.line_id:
                line.line_id = uuid.uuid4().hex
            if not line.is_property_set('color'):
                line.color = color_for_index(
                    task_index, [other.color for other in card.text_lines
                                 if other != line and other.is_property_set('color')])
            region = next((region for region in image.markup_regions
                           if region.checklist_card_id == card.item_id
                           and region.checklist_line_id == line.line_id), None)
            if region is None:
                region = next((region for region in image.markup_regions
                               if not region.checklist_card_id
                               and region.checklist_origin_card_id == card.item_id
                               and region.checklist_origin_line_id == line.line_id), None)
            if region is None and name_counts[line.value] == 1:
                # Recover colors detached by older builds, which cleared their IDs.
                candidates = [region for region in image.markup_regions
                              if not region.checklist_card_id
                              and not region.checklist_origin_card_id
                              and region.name == line.value]
                if len(candidates) == 1:
                    region = candidates[0]
            if region is None and not line.value:
                continue            # an emptied task paints nothing
            if region is None:
                region = image.markup_regions.add()
                region.region_id = uuid.uuid4().hex
                changed = True
            if region.checklist_card_id != card.item_id or region.checklist_line_id != line.line_id:
                region.checklist_card_id = card.item_id
                region.checklist_line_id = line.line_id
                changed = True
            if (region.checklist_origin_card_id != card.item_id
                    or region.checklist_origin_line_id != line.line_id):
                region.checklist_origin_card_id = card.item_id
                region.checklist_origin_line_id = line.line_id
            if any(abs(a - b) > 1e-5 for a, b in zip(region.color, line.color)):
                region.color = tuple(line.color)
                changed = True
            if region.name != line.value:
                region.name = line.value
                changed = True
        # A task removed in any way takes its color with it.
        task_ids = {line.line_id for line in card.text_lines}
        for i in reversed(range(len(image.markup_regions))):
            part = image.markup_regions[i]
            if part.checklist_card_id == card.item_id and part.checklist_line_id not in task_ids:
                image.markup_regions.remove(i)
                changed = True
        image.markup_active_index = max(
            0, min(image.markup_active_index, len(image.markup_regions) - 1))
        changed = _reorder_card_regions(image, card) or changed
    if changed:
        image.markup_revision += 1
    return changed


def sync_card_images(settings, card):
    for image in settings.images:
        if image.item_type == 'IMAGE' and is_associated(image, card.item_id):
            sync_checklist_regions(settings, image)


def associate_arrow_endpoints(settings, arrow):
    """Link only a completed arrow with two attached endpoints."""
    items = {item.item_id: item for item in settings.images if item.item_id}
    pair = checklist_image_pair(arrow, items)
    if pair is None:
        return False
    card, image = pair
    created = not is_associated(image, card.item_id)
    if created:
        adopt_image_regions(card, image)
        image.checklist_associations.add().card_id = card.item_id
    sync_checklist_regions(settings, image)
    return created


class KANVAS_OT_AssociateChecklist(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.associate_checklist'
    bl_label = 'Associate Checklist'
    bl_description = 'Link the active checklist to selected images and create one color per task'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return active_checklist(settings) is not None and bool(selected_images(settings))

    def execute(self, context):
        settings = get_settings(context)
        card = active_checklist(settings)
        if card is None:
            return {'CANCELLED'}
        count = adopted = 0
        for image in selected_images(settings):
            if not is_associated(image, card.item_id):
                adopted += adopt_image_regions(card, image)
                image.checklist_associations.add().card_id = card.item_id
                count += 1
            sync_checklist_regions(settings, image)
        context.area.tag_redraw()
        message = f'Checklist linked to {count} image(s)'
        if adopted:
            message += f'; {adopted} existing color(s) added as tasks'
        self.report({'INFO'}, message)
        return {'FINISHED'}


class KANVAS_OT_DissociateChecklist(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.dissociate_checklist'
    bl_label = 'Remove Checklist Link'
    bl_description = 'Unlink the active checklist from selected images; keep existing paint'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        card = active_checklist(settings)
        return card is not None and any(is_associated(image, card.item_id)
                                        for image in selected_images(settings))

    def execute(self, context):
        settings = get_settings(context)
        card = active_checklist(settings)
        if card is None:
            return {'CANCELLED'}
        for image in selected_images(settings):
            for index in range(len(image.checklist_associations) - 1, -1, -1):
                if image.checklist_associations[index].card_id == card.item_id:
                    image.checklist_associations.remove(index)
            for region in image.markup_regions:
                if region.checklist_card_id == card.item_id:
                    region.checklist_origin_card_id = region.checklist_card_id
                    region.checklist_origin_line_id = region.checklist_line_id
                    region.checklist_card_id = ''
                    region.checklist_line_id = ''
        context.area.tag_redraw()
        return {'FINISHED'}
