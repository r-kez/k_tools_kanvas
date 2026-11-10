"""Perspective tab: straighten an image whose subject is a rectangle seen at an angle (a
wall, a sheet, a screen). Drag the four corners onto the rectangle, then straighten."""

from ...utils import perspective
from .common import gap


def draw(layout, context, settings, item):
    if not item.image_data:
        layout.label(text='No image', icon='ERROR')
        return
    if item.crop_enabled and not item.persp_enabled:
        layout.label(text='Reset Bounds first', icon='INFO')
        layout.label(text='A cropped image cannot be straightened')
        return

    column = layout.column(align=True)
    column.prop(item, 'persp_editing', text='Edit Corners', icon='MESH_GRID', toggle=True)
    if item.persp_editing:
        note = column.column(align=True)
        note.label(text='Drag the 4 corners onto', icon='INFO')
        note.label(text='the corners of a real rectangle')
    row = column.row(align=True)
    row.operator('kanvas.perspective_rotate', text='Turn Corners', icon='FILE_REFRESH')
    row.operator('kanvas.perspective_reset', text='Reset', icon='X')
    gap(layout)

    column = layout.column(align=True)
    column.operator('kanvas.perspective_straighten',
                    text='Show Original' if item.persp_enabled else 'Straighten',
                    icon='LOOP_BACK' if item.persp_enabled else 'MOD_LATTICE',
                    depress=item.persp_enabled)
    if perspective.build_for(item) is None:
        column.label(text='The corners do not make a rectangle', icon='ERROR')
    gap(layout)

    column = layout.column(align=True)
    column.label(text='Proportions')
    row = column.row(align=True)
    row.prop(item, 'persp_auto', text='Auto', toggle=True)
    if item.persp_auto:
        ratio = perspective.estimated_ratio(item)
        row.label(text='' if ratio is None else f'{ratio:.3f}  (width / height)')
    else:
        row.prop(item, 'persp_aspect', text='Width / Height')
