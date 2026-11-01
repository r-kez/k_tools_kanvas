import bpy
from ..utils.kanvas_data import get_settings
from .main_panel import KANVAS_PT_MainPanel


class KANVAS_PT_DebugPanel(bpy.types.Panel):
    bl_label = "Debug"
    bl_idname = "KANVAS_PT_DebugPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"
    bl_parent_id = "KANVAS_PT_MainPanel"
    bl_order = 6
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        if not KANVAS_PT_MainPanel.poll(context):
            return False
        addon = context.preferences.addons.get(__package__.split('.')[0])
        return bool(addon and addon.preferences.show_debug_panel)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        # Vertical column with operator names only (no icons)
        col.operator("kanvas.reload_shader", text="Reload Custom Shader")
        col.operator("kanvas.clear_cache", text="Clear GPU Cache")
        col.operator("kanvas.reset_settings", text="Reset All Settings")
        col.separator()

        settings = get_settings(context)
        col.prop(settings, "show_debug_grid", text="Show Grid")
        col.prop(settings, "show_hitbox_debug", text="Show Hitbox Debug")
