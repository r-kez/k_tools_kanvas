"""Fit the bounds of image items to what their masks show, and give them back.

An item whose mask hides most of its image still has the whole image as its box, so its
selection box, handles, snapping, alignment and frames reach into empty space. Fit
Bounds to Mask crops the item to the part its mask leaves visible (see `utils/item_crop`):
nothing of the image is lost, and the item stays where it was on the canvas.
"""

import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils import item_crop
from ..utils.kanvas_data import get_settings


def _images(context, with_mask):
    """The selected images (the active one when none is selected), as ids; with a mask if
    `with_mask`."""
    from ..utils.item_picture import is_picture_item
    settings = get_settings(context)
    chosen = [item for item in settings.images
              if item.is_selected and is_picture_item(item)]
    if not chosen and 0 <= settings.active_image_index < len(settings.images):
        item = settings.images[settings.active_image_index]
        if is_picture_item(item):
            chosen = [item]
    return [item.item_id for item in chosen
            if not (item.mask_editing or item.markup_editing)
            and (not with_mask or (item.mask_enabled and (len(item.mask_dabs)
                                                          or len(item.mask_polygons))))]


class KANVAS_OT_FitBoundsToMask(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.fit_bounds_to_mask'
    bl_label = 'Fit Bounds to Mask'
    bl_description = ('Make the image only as big as what its mask shows: its selection box, '
                      'handles, snapping and frames ignore the transparent rest. The image '
                      'is not changed and stays where it is; Reset Bounds brings it back')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and bool(_images(context, True))

    def execute(self, context):
        from ..utils.item_picture import visible_uv_rect
        settings = get_settings(context)
        fitted, hidden = 0, 0
        for item_id in _images(context, True):
            item = next((i for i in settings.images if i.item_id == item_id), None)
            rect = visible_uv_rect(item) if item is not None else None
            if rect is None:
                hidden += 1          # the mask shows nothing: there is nothing to fit to
                continue
            if item_crop.set_crop(item, rect):
                fitted += 1
        if hidden:
            self.report({'WARNING'}, f'{hidden} mask{"s" if hidden > 1 else ""} show nothing')
        if not fitted:
            return {'CANCELLED'}
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_ResetBounds(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.reset_bounds'
    bl_label = 'Reset Bounds'
    bl_description = 'Give the image its whole size back, without moving what it shows'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        ids = set(_images(context, False))
        return any(item.item_id in ids and item.crop_enabled for item in settings.images)

    def execute(self, context):
        settings = get_settings(context)
        ids = set(_images(context, False))
        done = 0
        for item in settings.images:
            if item.item_id in ids and item.crop_enabled and item_crop.set_crop(item, None):
                done += 1
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'} if done else {'CANCELLED'}
