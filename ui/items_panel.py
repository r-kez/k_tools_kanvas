import bpy

from ..utils.kanvas_data import get_settings
from .main_panel import KANVAS_PT_MainPanel
from .sections.item_list import draw_item_list
from .sections.arrows import draw_arrows


class KANVAS_PT_ItemsPanel(bpy.types.Panel):
    bl_label = "Items"
    bl_idname = "KANVAS_PT_ItemsPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"
    bl_parent_id = "KANVAS_PT_MainPanel"
    bl_order = 1

    @classmethod
    def poll(cls, context):
        return KANVAS_PT_MainPanel.poll(context)

    def draw(self, context):
        settings = get_settings(context)
        draw_item_list(self.layout, settings)
        draw_arrows(self.layout, settings)
