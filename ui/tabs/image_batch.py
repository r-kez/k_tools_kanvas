"""Image settings that apply to every selected image when several are selected."""


def batch_owner(settings, item):
    """(owner, prefix, count): with several images selected the panel edits the
    `batch_` properties of the board, which pass the change to all of them."""
    count = sum(1 for other in settings.images
                if other.item_type == 'IMAGE' and other.is_selected)
    if count > 1 and item.is_selected:
        return settings, 'batch_', count
    return item, '', count


def draw_flips(layout, settings, item):
    from ...utils.icons import get_icon
    owner, prefix, _count = batch_owner(settings, item)
    row = layout.row(align=True)
    row.prop(owner, prefix + 'flip_h', text='Flip H', toggle=True,
             icon_value=get_icon('icon-flip-horizontal'))
    row.prop(owner, prefix + 'flip_v', text='Flip V', toggle=True,
             icon_value=get_icon('icon-flip-vertical'))
