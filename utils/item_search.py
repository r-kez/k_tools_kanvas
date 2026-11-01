"""Which board items match a search query (names and content)."""


def item_matches(item, query):
    """True when `query` (already lower-cased) is in the item's name or content.

    Text cards and checklists match on their lines; images match on the names of
    their color regions, which is the task text for regions linked to a checklist.
    """
    if not query:
        return True
    if query in item.name.casefold():
        return True
    kind = item.item_type
    if kind == 'TEXT':
        return any(query in line.value.casefold() for line in item.text_lines)
    if kind == 'IMAGE':
        return any(query in region.name.casefold() for region in item.markup_regions)
    return False
