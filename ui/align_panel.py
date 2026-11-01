import bpy

from ..utils.kanvas_data import get_settings
from .main_panel import KANVAS_PT_MainPanel
from .sections.align import alignable_count, draw_align


class KANVAS_PT_AlignPanel(bpy.types.Panel):
    bl_label = "Align"
    bl_idname = "KANVAS_PT_AlignPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"
    bl_parent_id = "KANVAS_PT_MainPanel"
    bl_order = 3
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (KANVAS_PT_MainPanel.poll(context)
                and alignable_count(get_settings(context)) > 1)

    def draw(self, context):
        draw_align(self.layout, get_settings(context))
