import bpy

from ..utils.kanvas_data import get_settings
from .main_panel import KANVAS_PT_MainPanel
from .sections.gizmo_settings import draw_gizmo_settings


class KANVAS_PT_GizmoPanel(bpy.types.Panel):
    bl_label = "Gizmos"
    bl_idname = "KANVAS_PT_GizmoPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"
    bl_parent_id = "KANVAS_PT_MainPanel"
    bl_order = 4
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return KANVAS_PT_MainPanel.poll(context)

    def draw_header(self, context):
        self.layout.prop(get_settings(context), "show_gizmos", text="")

    def draw(self, context):
        draw_gizmo_settings(self.layout, get_settings(context))
