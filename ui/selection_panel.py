import bpy

from ..utils.kanvas_data import get_settings
from .main_panel import KANVAS_PT_MainPanel
from .sections.selection import draw_selection_actions
from .sections.frame_properties import draw_frame_properties
from .sections.text_properties import draw_text_properties
from .sections.image_properties import draw_image_properties


class KANVAS_PT_SelectionPanel(bpy.types.Panel):
    bl_label = "Selection"
    bl_idname = "KANVAS_PT_SelectionPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"
    bl_parent_id = "KANVAS_PT_MainPanel"
    bl_order = 2

    @classmethod
    def poll(cls, context):
        return KANVAS_PT_MainPanel.poll(context)

    def draw(self, context):
        settings = get_settings(context)
        active_index = settings.active_image_index
        if not (0 <= active_index < len(settings.images)
                and settings.images[active_index].is_selected):
            active_index = next((i for i, item in enumerate(settings.images)
                                 if item.is_selected), -1)
        if active_index < 0:
            if (0 <= settings.active_arrow_index < len(settings.arrows)
                    or any(arrow.is_selected for arrow in settings.arrows)):
                self.layout.label(text="Arrow selected")
            else:
                self.layout.label(text="Nothing selected")
            return
        draw_selection_actions(self.layout, settings)
        item = settings.images[active_index]
        if item.item_type == 'FRAME':
            draw_frame_properties(self.layout, settings, item)
        elif item.item_type == 'TEXT':
            draw_text_properties(self.layout, settings, item)
        else:
            draw_image_properties(self.layout, settings, item)
