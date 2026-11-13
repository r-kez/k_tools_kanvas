"""Pencil Drawing: draw on it, the pencil's color, width and smoothing, place and size."""

from .common import gap, pair_row, vector_row


def draw(layout, context, settings, item):
    box = layout.box()
    box.prop(item, 'pencil_editing', text='Draw on this drawing (E)', toggle=True,
             icon='GREASEPENCIL')
    count = len(item.shape_strokes)
    box.label(text=f'{count} stroke' + ('' if count == 1 else 's'))
    gap(layout)
    pencil = layout.column(align=True)
    pencil.prop(settings, 'pencil_color', text='Color')
    pencil.prop(settings, 'pencil_width', text='Width')
    pencil.prop(settings, 'pencil_smoothing', text='Smoothing')
    pencil.prop(settings, 'pencil_use_pressure', text='Pressure')
    pressure = pencil.column(align=True)
    pressure.active = settings.pencil_use_pressure
    pressure.prop(settings, 'pencil_pressure_min', text='Minimum Size')
    pressure.prop(settings, 'pencil_pressure_curve', text='Response')
    pencil.prop(settings, 'pencil_antialias', text='Antialiasing')
    pencil.prop(settings, 'pencil_eraser_size', text='Eraser Size (Alt)')
    pencil.prop(settings, 'pencil_attach', text='Stick to Image (Shift: loose)')
    gap(layout)
    from ...utils import pencil_anchor
    parent = pencil_anchor.parent_of(settings, item)
    stuck = layout.row(align=True)
    if parent is not None:
        stuck.label(text=f'Stuck to {parent.name}', icon='LINKED')
        stuck.operator('kanvas.pencil_detach', text='', icon='UNLINKED')
    else:
        stuck.operator('kanvas.pencil_attach', icon='LINKED')
    gap(layout)
    geometry = layout.column(align=True)
    vector_row(geometry, 'Position', item, 'location')
    pair_row(geometry, 'Size', item, ('shape_width', 'shape_height'))
    row = geometry.row(align=True)
    row.prop(item, 'rotation_ui', text='Rotation')
    row.prop(item, 'scale_master', text='Scale')
    gap(layout)
    layout.prop(item, 'opacity', text='Opacity', slider=True)
