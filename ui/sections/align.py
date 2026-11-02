def alignable_count(settings):
    return sum(1 for item in settings.images
               if item.is_selected and item.show_in_editor and not item.is_locked
               and item.item_type in {'IMAGE', 'TEXT', 'SHAPE'})


def draw_align(layout, settings):
    from ...operators.ops_align import ALIGN_ICONS
    from ...utils.icons import get_icon

    row = layout.row(align=True)
    for mode in ('LEFT', 'CENTER_X', 'RIGHT', 'TOP', 'CENTER_Y', 'BOTTOM'):
        row.operator('kanvas.align_items', text="",
                     icon_value=get_icon(ALIGN_ICONS[mode])).mode = mode
    if alignable_count(settings) >= 3:
        row = layout.row(align=True)
        row.operator('kanvas.distribute_items',
                     text='Distribute Horizontally').axis = 'HORIZONTAL'
        row.operator('kanvas.distribute_items',
                     text='Distribute Vertically').axis = 'VERTICAL'
