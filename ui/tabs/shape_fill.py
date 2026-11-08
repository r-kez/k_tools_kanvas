"""Fill tab: the inside of the shape, one color or a gradient."""

from .common import gap, vector_row

# The color ramp gets more height than a plain row: its stops are dragged with the mouse.
RAMP_SCALE_Y = 1.4


def draw(layout, context, settings, item):
    row = layout.row(align=True)
    check = row.row(align=True)
    check.enabled = item.shape_show_outline  # never leave a shape without fill and outline
    check.prop(item, 'shape_show_fill', text='Fill', toggle=True)
    row.prop(item, 'shape_fill_opacity', text='Opacity', slider=True)
    body = layout.column()
    body.enabled = item.shape_show_fill
    if not item.shape_closed:
        gap(body)
        body.label(text='Open paths are drawn without fill', icon='INFO')
        return
    gap(body)
    body.row(align=True).prop(item, 'shape_fill_type', expand=True)
    gap(body)
    if item.shape_fill_type == 'SOLID':
        body.prop(item, 'shape_fill_color', text='Color')
    else:
        _draw_gradient(body, item)


def _draw_gradient(layout, item):
    """Color ramp, spread and points of a gradient fill."""
    texture = item.shape_gradient_texture
    if texture is not None and texture.color_ramp is not None:
        # Its own box, not an aligned column: aligned, the ramp is squeezed flat.
        box = layout.box()
        ramp = box.column()
        ramp.scale_y = RAMP_SCALE_Y
        ramp.template_color_ramp(texture, 'color_ramp', expand=True)
    else:
        layout.operator('kanvas.gradient_edit_colors', text='Edit Colors', icon='COLOR')
    gap(layout)
    layout.prop(item, 'shape_gradient_spread', text='Spread')
    gap(layout)
    points = layout.column(align=True)
    radial = item.shape_fill_type == 'RADIAL'
    vector_row(points, 'Center' if radial else 'Start', item, 'shape_gradient_start')
    vector_row(points, 'Edge' if radial else 'End', item, 'shape_gradient_end')
    row = layout.row(align=True)
    row.operator('kanvas.gradient_rotate', text='Turn 90°', icon='FILE_REFRESH')
    row.operator('kanvas.gradient_reset_points', text='Reset', icon='LOOP_BACK')
