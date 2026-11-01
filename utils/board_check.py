"""Find and repair broken references on a board.

References are stored by item id, so deleting or damaging an item can leave
links pointing at nothing. Checking never changes anything; fixing only removes
or clears the broken reference and never deletes content.
"""

from dataclasses import dataclass

from .arrow_geometry import endpoint, set_endpoint


@dataclass(frozen=True)
class Problem:
    kind: str
    message: str
    fixable: bool


def _cards(settings):
    return {item.item_id: item for item in settings.images
            if item.item_type == 'TEXT' and item.text_checklist}


def _broken_regions(settings):
    cards = _cards(settings)
    broken = []
    for image in settings.images:
        if image.item_type != 'IMAGE':
            continue
        for region in image.markup_regions:
            if not region.checklist_card_id:
                continue
            card = cards.get(region.checklist_card_id)
            if card is None or not any(line.line_id == region.checklist_line_id
                                       for line in card.text_lines):
                broken.append(region)
    return broken


def _broken_links(settings):
    cards = _cards(settings)
    return [(image, index) for image in settings.images if image.item_type == 'IMAGE'
            for index, link in enumerate(image.checklist_associations)
            if link.card_id not in cards]


def _dangling_ends(settings):
    known = {item.item_id for item in settings.images}
    return [(arrow, side) for arrow in settings.arrows for side in ('start', 'end')
            if getattr(arrow, side + '_item_id') and getattr(arrow, side + '_item_id') not in known]


def _orphans(settings):
    frames = {item.frame_node_name for item in settings.images if item.item_type == 'FRAME'}
    return [item for item in settings.images if item.parent_frame and item.parent_frame not in frames]


def _bad_identities(settings):
    seen, bad = set(), 0
    for item in settings.images:
        if not item.item_id or item.item_id in seen:
            bad += 1
        seen.add(item.item_id)
    return bad


def find_problems(settings):
    problems = []
    bad = _bad_identities(settings)
    if bad:
        problems.append(Problem('IDS', f'{bad} item(s) share an identity or have none', True))
    missing = [item for item in settings.images
               if item.item_type == 'IMAGE' and not item.image_data]
    if missing:
        names = ', '.join(item.name for item in missing[:3]) + ('...' if len(missing) > 3 else '')
        problems.append(Problem('NO_IMAGE', f'{len(missing)} image item(s) have no image ({names})', False))
    orphans = _orphans(settings)
    if orphans:
        problems.append(Problem('FRAME', f'{len(orphans)} item(s) belong to a frame that no longer exists', True))
    links = _broken_links(settings)
    if links:
        problems.append(Problem('LINK', f'{len(links)} image link(s) point to a checklist that no longer exists', True))
    regions = _broken_regions(settings)
    if regions:
        problems.append(Problem('REGION', f'{len(regions)} color region(s) follow a checklist task that no longer exists', True))
    ends = _dangling_ends(settings)
    if ends:
        problems.append(Problem('ARROW', f'{len(ends)} arrow end(s) are attached to an item that no longer exists', True))
    return problems


def fix_problems(settings):
    """Repair everything fixable; returns the number of references changed."""
    changed = 0
    if _bad_identities(settings):
        from .gpu import ensure_item_ids
        ensure_item_ids(settings)
        changed += 1
    for item in _orphans(settings):
        item.parent_frame = ''
        changed += 1
    # Remove from the end so earlier indexes stay valid.
    for image, index in sorted(_broken_links(settings), key=lambda pair: -pair[1]):
        image.checklist_associations.remove(index)
        changed += 1
    for region in _broken_regions(settings):
        region.checklist_card_id = ''
        region.checklist_line_id = ''
        region.checklist_origin_card_id = ''
        region.checklist_origin_line_id = ''
        changed += 1
    for arrow, side in _dangling_ends(settings):
        set_endpoint(arrow, side, endpoint(settings, arrow, side))
        changed += 1
    return changed
