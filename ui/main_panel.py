import bpy


class KANVAS_PT_MainPanel(bpy.types.Panel):
    bl_label = "Kanvas"
    bl_idname = "KANVAS_PT_MainPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"

    @classmethod
    def poll(cls, context):
        tree = getattr(getattr(context, 'space_data', None), 'edit_tree', None)
        return tree is not None and tree.bl_idname == 'KanvasNodeTree'

    def draw(self, context):
        from ..utils.kanvas_data import get_settings
        self.layout.row().prop(get_settings(context), 'canvas_mode', expand=True)
        from ..utils.gpu.gpu_common import get_prefs
        prefs = get_prefs()
        if prefs is not None:
            self.layout.prop(prefs, 'show_mode_overlay', text='Show Mode Overlay')
