"""Line tab: the line around the shape."""

from .common import gap


def draw(layout, context, settings, item):
    row = layout.row(align=True)
    check = row.row(align=True)
    check.enabled = item.shape_show_fill  # never leave a shape without fill and outline
    check.prop(item, 'shape_show_outline', text='Outline', toggle=True)
    gap(layout)
    body = layout.column(align=True)
    body.enabled = item.shape_show_outline
    row = body.row(align=True)
    row.prop(item, 'shape_line_color', text='')
    row.prop(item, 'shape_line_width', text='Width')
    body.row(align=True).prop(item, 'shape_line_style', expand=True)
    gap(layout)
    body = layout.column(align=True)
    body.enabled = item.shape_show_outline
    body.prop(item, 'shape_line_join', text='Join')
    ends = body.row(align=True)
    ends.enabled = not item.shape_closed or item.shape_line_style == 'DASHED'
    ends.prop(item, 'shape_line_cap', text='Ends')
    align = body.row(align=True)
    align.enabled = item.shape_closed
    align.prop(item, 'shape_line_align', text='Align')
