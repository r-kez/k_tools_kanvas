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
        
        if not hasattr(scene, "kanvas_settings"):
            layout.label(text="Kanvas settings not found. Try reloading the addon.", icon='ERROR')
            return
            
        settings = scene.kanvas_settings

        row = layout.row(align=True)
        row.operator("kanvas.add_image_browser", icon='ADD', text="Add")
        row.operator("kanvas.add_multiple_images", icon='FILE_NEW', text="Add Multiple")
        
        selected_count = sum(1 for i in settings.images if i.is_selected)
        if selected_count > 1:
            layout.operator("kanvas.pack_images", icon='GRID', text=f"Pack Selected ({selected_count})")
        
        row = layout.row(align=True)
        row.scale_y = 1.5
        
        is_running = settings.is_modal_running
        btn_text = "KANVAS ACTIVE" if is_running else "START KANVAS"
        btn_icon = 'CHECKMARK' if is_running else 'PLAY'
        row.operator("kanvas.toggle_interactivity", text=btn_text, icon=btn_icon, depress=is_running)
        
        if is_running:
            layout.prop(settings, "use_interactivity", text="Allow Interaction", toggle=True, icon='RESTRICT_SELECT_OFF')
            layout.label(text="Use the floating toolbar in the viewport!", icon='INFO')
        
        row = layout.row(align=True)
        row.prop(settings, "show_all", text="Show Images", toggle=True)
        row.prop(settings, "show_debug_grid", text="", icon='GRID')
        
        # Gizmo & Snap Settings
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(settings, "show_gizmos", text="Gizmos", icon='GIZMO')
        row.prop(settings, "use_snapping", text="Snap", icon='SNAP_GRID' if settings.use_snapping else 'SNAP_OFF')
        
        if settings.show_gizmos:
            row = col.row(align=True)
            row.prop(settings, "gizmo_size", text="Size")
            row.prop(settings, "show_scale_handles", text="Scale", toggle=True)
            row.prop(settings, "show_rotate_handles", text="Rotate", toggle=True)
            
        if settings.use_snapping:
            row = col.row(align=True)
            row.prop(settings, "snap_grid", text="Grid", toggle=True)
            row.prop(settings, "snap_images", text="Edges", toggle=True)
            row.prop(settings, "grid_size", text="Step")
        
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
                col.prop(img, "rotation", text="Rotation")
                
                # Scale & Shear
                row = col.row(align=True)
                row.prop(img, "scale_master", text="Uniform Scale")
                
                row = col.row(align=True)
                row.prop(img, "scale_xy", text="Stretch")
                
                row = col.row(align=True)
                row.prop(img, "shear_xy", text="Shear")
                
                col.separator()
                col.separator()
                
                # Image Adjustments
                from .utils.icons import get_icon
                row = col.row(align=True)
                row.prop(img, "flip_h", text="Flip H", toggle=True, icon_value=get_icon("icon-flip-horizontal"))
                row.prop(img, "flip_v", text="Flip V", toggle=True, icon_value=get_icon("icon-flip-vertical"))
                
                col.separator()
                col.prop(img, "brightness", text="Brightness", slider=True)
                col.prop(img, "contrast", text="Contrast", slider=True)
                col.prop(img, "saturation", text="Saturation", slider=True)
                
                col.separator()
                col.prop(img, "opacity", text="Opacity", slider=True)
                
                row = col.row(align=True)
                row.prop(img, "color_tint", text="")
                row.prop(img, "use_color_correction", text="", icon='IMAGE')
                
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
