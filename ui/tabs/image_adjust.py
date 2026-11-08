"""Adjust tab: how the image looks. With several images selected, every change goes to
all of them."""

from .common import gap
from .image_batch import batch_owner


def draw(layout, context, settings, item):
    if not item.image_data:
        layout.label(text='No image', icon='ERROR')
        return
    owner, prefix, count = batch_owner(settings, item)
    column = layout.column(align=True)
    if prefix:
        column.label(text=f'Adjust {count} selected images', icon='IMAGE_DATA')
    column.prop(owner, prefix + 'opacity', text='Opacity', slider=True)
    gap(layout)
    column = layout.column(align=True)
    column.prop(owner, prefix + 'brightness', text='Brightness', slider=True)
    column.prop(owner, prefix + 'contrast', text='Contrast', slider=True)
    column.prop(owner, prefix + 'saturation', text='Saturation', slider=True)
    gap(layout)
    column = layout.column(align=True)
    row = column.row(align=True)
    row.prop(owner, prefix + 'color_tint', text='')
    row.prop(owner, prefix + 'use_color_correction', text='', icon='IMAGE')
    gap(layout)
    column = layout.column(align=True)
    column.label(text='Check Values')
    row = column.row(align=True)
    row.prop(owner, prefix + 'value_gray', text='Grayscale', toggle=True)
    row.prop(owner, prefix + 'value_levels', text='Posterize')
