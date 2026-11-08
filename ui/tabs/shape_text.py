"""Text tab: the short label inside the shape."""

from .common import gap


def draw(layout, context, settings, item):
    layout.prop(item, 'shape_show_text', text='Show Text', toggle=True, icon='FONT_DATA')
    gap(layout)
    content = layout.column(align=True)
    content.enabled = item.shape_show_text
    content.prop(item, 'text_body', text='')  # one line: the text shrinks to fit the shape
    row = content.row(align=True)
    row.prop(item, 'text_font_size', text='Font')
    row.prop(item, 'text_color', text='')
