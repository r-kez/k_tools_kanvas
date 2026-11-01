"""Identify arrows attached between a checklist and an image."""


def checklist_image_pair(arrow, items_by_id):
    start = items_by_id.get(arrow.start_item_id)
    end = items_by_id.get(arrow.end_item_id)
    if start is None or end is None:
        return None
    if start.item_type == 'TEXT' and start.text_checklist and end.item_type == 'IMAGE':
        return start, end
    if end.item_type == 'TEXT' and end.text_checklist and start.item_type == 'IMAGE':
        return end, start
    return None


def attached_checklist_pairs(settings):
    items = {item.item_id: item for item in settings.images if item.item_id}
    return {tuple(item.item_id for item in pair)
            for arrow in settings.arrows
            if (pair := checklist_image_pair(arrow, items)) is not None}
