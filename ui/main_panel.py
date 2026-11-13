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
        from ..utils.gpu.gpu_common import get_prefs
        prefs = get_prefs()
        # The switch lives in the editor header; the panel repeats it only on request.
        #if prefs is not None and prefs.show_mode_in_panel:
        #    self.layout.row().prop(get_settings(context), 'canvas_mode', expand=True)
        #if prefs is not None:
        #    self.layout.prop(prefs, 'show_mode_overlay', text='Show Mode Overlay')
#
        tool = context.workspace.tools.from_space_node()
        if tool is not None and tool.idname == 'kanvas.eraser':
            box = self.layout.box()
            box.label(text='Eraser', icon='GREASEPENCIL')
            box.prop(get_settings(context), 'pencil_eraser_size', text='Size')
        if tool is not None and tool.idname == 'kanvas.pencil':
            settings = get_settings(context)
            box = self.layout.box()
            box.label(text='Pencil', icon='GREASEPENCIL')
            column = box.column(align=True)
            column.prop(settings, 'pencil_color', text='Color')
            column.prop(settings, 'pencil_width', text='Width')
            column.prop(settings, 'pencil_smoothing', text='Smoothing')
            column.prop(settings, 'pencil_use_pressure', text='Pressure')
            pressure = column.column(align=True)
            pressure.active = settings.pencil_use_pressure
            pressure.prop(settings, 'pencil_pressure_min', text='Minimum Size')
            pressure.prop(settings, 'pencil_pressure_curve', text='Response')
            column.prop(settings, 'pencil_antialias', text='Antialiasing')
            column.prop(settings, 'pencil_eraser_size', text='Eraser Size (Alt)')
            column.prop(settings, 'pencil_attach', text='Stick to Image (Shift: loose)')
