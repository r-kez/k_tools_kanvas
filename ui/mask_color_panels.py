import bpy

from ..utils.kanvas_data import get_settings
from .selection_panel import KANVAS_PT_SelectionPanel
from .sections.image_properties import draw_mask_properties, draw_color_properties


def _selected_image(context):
    settings = get_settings(context)
    if settings is None:
        return None
    index = settings.active_image_index
    if not (0 <= index < len(settings.images)
            and settings.images[index].is_selected):
        index = next((i for i, item in enumerate(settings.images)
                      if item.is_selected), -1)
    if index < 0:
        return None
    item = settings.images[index]
    return item if item.item_type == 'IMAGE' and item.image_data else None


class _SelectedImagePanel:
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'K-Tools'
    bl_parent_id = 'KANVAS_PT_SelectionPanel'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (KANVAS_PT_SelectionPanel.poll(context)
                and _selected_image(context) is not None)


class KANVAS_PT_MaskPanel(_SelectedImagePanel, bpy.types.Panel):
    bl_label = 'Mask'
    bl_idname = 'KANVAS_PT_MaskPanel'
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 1

    def draw_header(self, context):
        self.layout.prop(_selected_image(context), 'mask_enabled', text='')

    def draw(self, context):
        draw_mask_properties(self.layout, _selected_image(context))


class KANVAS_PT_ColorPanel(_SelectedImagePanel, bpy.types.Panel):
    bl_label = 'Markup'
    bl_idname = 'KANVAS_PT_ColorPanel'
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 2

    def draw_header(self, context):
        self.layout.prop(_selected_image(context), 'markup_visible', text='')

    def draw(self, context):
        draw_color_properties(self.layout, _selected_image(context))
