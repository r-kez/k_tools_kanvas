import bpy

from ..utils.kanvas_data import get_settings
from .main_panel import KANVAS_PT_MainPanel
from .sections.snap_settings import draw_snap_settings


class KANVAS_PT_SnapPanel(bpy.types.Panel):
    bl_label = "Snap"
    bl_idname = "KANVAS_PT_SnapPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"
    bl_parent_id = "KANVAS_PT_MainPanel"
    bl_order = 5
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return KANVAS_PT_MainPanel.poll(context)

    def draw_header(self, context):
        self.layout.prop(context.tool_settings, "use_snap_node", text="", toggle=False)

    def draw(self, context):
        draw_snap_settings(self.layout, context, get_settings(context))
