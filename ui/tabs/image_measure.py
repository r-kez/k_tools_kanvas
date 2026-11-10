"""Measure tab: marks drawn on the image and the scale that gives them real sizes."""

from ...utils import measure as mm
from .common import gap


def draw(layout, context, settings, item):
    draw_scale(layout, item)
    gap(layout)
    draw_marks(layout, settings, item)


def draw_scale(layout, item):
    box = layout.column(align=True)
    box.label(text='Scale')
    mark = mm.scale_mark(item)
    per_pixel = mm.meters_per_pixel(item)
    if mark is None or per_pixel is None:
        note = box.column(align=True)
        note.label(text='No scale: marks read in pixels', icon='INFO')
        note.label(text='Mark something of known size')
    else:
        box.label(text=f'{mark.name}: {mm.scale_text(item)}', icon='PINNED')
        box = box.column(align=True)
        row = box.row(align=True)
        row.prop(mark, 'known_value', text='')
        row.prop(mark, 'known_unit', text='')
        if mark.kind == 'RECT':
            row = box.row(align=True)
            row.prop_enum(mark, 'known_side', 'HEIGHT')
            row.prop_enum(mark, 'known_side', 'WIDTH')
    layout.label(text='Draw the scale mark:' if mark is None else 'Draw it again:')
    row = layout.row(align=True)
    for kind, label, icon in (('LINE', 'Line', 'DRIVER_DISTANCE'),
                              ('RECT', 'Rectangle', 'MESH_PLANE')):
        tool = row.operator('kanvas.measure_tool', text=label, icon=icon)
        tool.kind, tool.purpose = kind, 'SCALE'
    if item.measure_scale_id:
        layout.operator('kanvas.clear_measure_scale', icon='X')


def draw_marks(layout, settings, item):
    head = layout.row(align=True)
    head.label(text='Marks')
    sub = head.row()
    sub.alignment = 'RIGHT'
    sub.prop(settings, 'measure_unit', text='')
    row = layout.row()
    row.template_list('KANVAS_UL_measures', '', item, 'measures', item,
                      'measure_active_index', rows=4)
    buttons = row.column(align=True)
    buttons.operator('kanvas.remove_measure', text='', icon='REMOVE')
    buttons.operator('kanvas.clear_measures', text='', icon='TRASH')
    row = layout.row(align=True)
    for kind, label, icon in (('LINE', 'Line', 'ADD'), ('RECT', 'Rectangle', 'ADD')):
        tool = row.operator('kanvas.measure_tool', text=label, icon=icon)
        tool.kind, tool.purpose = kind, 'MARK'
    if len(item.measures):
        active = item.measures[min(item.measure_active_index, len(item.measures) - 1)]
        if active.measure_id != item.measure_scale_id:
            layout.operator('kanvas.set_measure_scale', text='Use Active Mark as Scale',
                            icon='PINNED')
    gap(layout)
    layout.prop(item, 'measure_visible', text='Show Marks on Canvas', toggle=True,
                icon='HIDE_OFF' if item.measure_visible else 'HIDE_ON')
