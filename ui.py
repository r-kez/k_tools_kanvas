import bpy

class KANVAS_UL_image_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "show_in_editor", text="", icon='HIDE_OFF' if item.show_in_editor else 'HIDE_ON', emboss=False)
            row.prop(item, "name", text="", emboss=False)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='IMAGE_DATA')

class KANVAS_PT_MainPanel(bpy.types.Panel):
    bl_label = "Kanvas"
    bl_idname = "KANVAS_PT_MainPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"

    @classmethod
    def poll(cls, context):
        # Only show in our custom Kanvas Node Tree
        return context.space_data.edit_tree and context.space_data.edit_tree.bl_idname == 'KanvasNodeTree'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.kanvas_settings

        layout.operator("kanvas.add_image", icon='ADD', text="Add Reference")
        
        row = layout.row(align=True)
        row.scale_y = 1.5
        
        is_active = settings.is_modal_active
        btn_text = "MOVE & SELECT (Running)" if is_active else "Move & Select"
        btn_icon = 'MOUSE_MOVE' if is_active else 'RESTRICT_SELECT_OFF'
        row.operator("kanvas.modal", text=btn_text, icon=btn_icon, depress=is_active)
        
        row = layout.row(align=True)
        row.prop(settings, "show_all", text="Show Images", toggle=True)
        row.prop(settings, "show_debug_grid", text="", icon='GRID')
        
        # Gizmo Settings
        box = layout.box()
        row = box.row(align=True)
        row.prop(settings, "show_gizmos", text="Show Gizmos", icon='GIZMO')
        if settings.show_gizmos:
            row.prop(settings, "gizmo_size", text="Size")
        
        layout.separator()
        
        # --- UI LIST ---
        row = layout.row()
        row.template_list("KANVAS_UL_image_list", "", settings, "images", settings, "active_image_index")
        
        col = row.column(align=True)
        col.operator_context = 'INVOKE_DEFAULT'
        col.operator("kanvas.remove_image", icon='REMOVE', text="").index = settings.active_image_index
        
        # --- CONTEXTUAL PROPERTIES ---
        if settings.images and settings.active_image_index < len(settings.images):
            img = settings.images[settings.active_image_index]
            
            box = layout.box()
            box.label(text=f"Properties: {img.name}", icon='IMAGE_DATA')
            
            col = box.column(align=True)
            row = col.row(align=True)
            row.prop(img, "image_data", text="")
            row.operator("kanvas.refresh_image", icon='FILE_REFRESH', text="")
            
            if img.image_data:
                col.prop(img, "location", text="Position")
                
                row = col.row(align=True)
                row.prop(img, "scale", text="Scale")
                row.prop(img, "rotation", text="Rot")
                
                row = col.row(align=True)
                row.prop(img, "color_tint", text="")
                row.prop(img, "use_color_correction", text="", icon='IMAGE')
                row.prop(img, "opacity", text="Alpha", slider=True)
                
                box.operator("kanvas.duplicate_image", icon='DUPLICATE', text="Duplicate Instance")

class KANVAS_PT_DebugPanel(bpy.types.Panel):
    bl_label = "Debug"
    bl_idname = "KANVAS_PT_DebugPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"
    bl_parent_id = "KANVAS_PT_MainPanel"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        
        # Vertical column with operator names only (no icons)
        col.operator("kanvas.reload_shader", text="Reload Custom Shader")
        col.operator("kanvas.clear_cache", text="Clear GPU Cache")
        col.operator("kanvas.debug_info", text="Print Debug Info")
        col.separator()
        col.operator("kanvas.reset_settings", text="Reset All Settings")
