"""Card tab: where the text card sits, its size and its colors."""

from .common import gap, pair_row, vector_row, wide_row


def draw(layout, context, settings, item):
    geometry = layout.column(align=True)
    vector_row(geometry, 'Position', item, 'location')
    pair_row(geometry, 'Size', item, ('text_width', 'text_height'))
    row = geometry.row(align=True)
    row.prop(item, 'text_scale', text='Scale')
    row.prop(item, 'text_font_size', text='Font')

    gap(layout)
    appearance = layout.column(align=True)
    wide_row(appearance, 'Text', item, 'text_color')
    wide_row(appearance, 'Background', item, 'text_background')
    wide_row(appearance, 'Opacity', item, 'text_opacity', slider=True)
