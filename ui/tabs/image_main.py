"""Image tab: the image file and where it comes from, its place, size and turn."""

import os

from .common import gap, vector_row, wide_row
from .image_batch import draw_flips


def draw(layout, context, settings, item):
    column = layout.column(align=True)
    row = column.row(align=True)
    row.prop(item, 'image_data', text='')
    row.operator('kanvas.refresh_image', icon='FILE_REFRESH', text='')
    row.operator('kanvas.replace_image', icon='FILEBROWSER', text='')
    row.operator('kanvas.clear_image_gpu_cache', icon='TRASH', text='')
    from ...operators.ops_image import image_origin
    source_kind, source = image_origin(item.image_data)
    if source:
        row = column.row(align=True)
        row.label(text='Source: ' + (source if source_kind == 'URL'
                                     else os.path.basename(source)))
        if source_kind != 'PUR':
            row.operator('kanvas.open_image_source', text='Open')
    if not item.image_data:
        return
    gap(layout)
    column = layout.column(align=True)
    vector_row(column, 'Position', item, 'location')
    wide_row(column, 'Rotation', item, 'rotation_ui')
    wide_row(column, 'Scale', item, 'scale_master')
    vector_row(column, 'Stretch', item, 'scale_xy')
    vector_row(column, 'Shear', item, 'shear_xy')
    gap(layout)
    draw_flips(layout, settings, item)
    gap(layout)
    layout.operator('kanvas.add_3d_reference', icon='OUTLINER_OB_IMAGE',
                    text='Send to 3D View...')
