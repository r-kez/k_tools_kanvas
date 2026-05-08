import bpy

class KANVAS_OT_ResetSettings(bpy.types.Operator):
    """Reset all Kanvas settings to default values"""
    bl_idname = "kanvas.reset_settings"
    bl_label = "Reset All Settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.kanvas_settings
        settings.images.clear()
        settings.show_all = True
        settings.show_debug_grid = True
        settings.show_gizmos = True
        settings.gizmo_size = 8.0
        context.area.tag_redraw()
        self.report({'INFO'}, "Kanvas Settings Reset")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

class KANVAS_OT_ClearCache(bpy.types.Operator):
    """Clear the GPU texture cache (Force re-upload of all images)"""
    bl_idname = "kanvas.clear_cache"
    bl_label = "Clear GPU Cache"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..utils.gpu.image import _texture_cache
        _texture_cache.clear()
        context.area.tag_redraw()
        self.report({'INFO'}, "GPU Cache Cleared")
        return {'FINISHED'}

class KANVAS_OT_ReloadShader(bpy.types.Operator):
    """Force re-compilation of the custom GPU shader"""
    bl_idname = "kanvas.reload_shader"
    bl_label = "Reload Custom Shader"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..utils.gpu.common import clear_kanvas_shader
        clear_kanvas_shader()
        context.area.tag_redraw()
        context.area.tag_redraw()
        self.report({'INFO'}, "Shader Reloaded")
        return {'FINISHED'}

class KANVAS_OT_ToggleInteractivity(bpy.types.Operator):
    """Toggle the background interaction mode"""
    bl_idname = "kanvas.toggle_interactivity"
    bl_label = "Toggle Interaction"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.kanvas_settings
        
        # Ensure the tree is protected from Purge when starting interaction
        if context.space_data.type == 'NODE_EDITOR' and context.space_data.edit_tree:
            tree = context.space_data.edit_tree
            if tree.bl_idname == 'KanvasNodeTree' and not tree.use_fake_user:
                tree.use_fake_user = True

        if settings.is_modal_running:
            # Signal the modal to stop
            settings.is_modal_running = False
            self.report({'INFO'}, "Kanvas Interaction Stopped")
        else:
            # Start the modal
            bpy.ops.kanvas.modal('INVOKE_DEFAULT')
            self.report({'INFO'}, "Kanvas Interaction Started")
        
        context.area.tag_redraw()
        return {'FINISHED'}

class KANVAS_OT_DebugInfo(bpy.types.Operator):
    """Print diagnostic information to the system console"""
    bl_idname = "kanvas.debug_info"
    bl_label = "Print Debug Info"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.kanvas_settings
        from ..utils.gpu.image import _texture_cache
        
        print("\n--- KANVAS DEBUG INFO ---")
        print(f"Total Images: {len(settings.images)}")
        print(f"Cached Textures: {len(_texture_cache)}")
        for name in _texture_cache.keys():
            print(f"  - {name}")
        print(f"Modal Running: {settings.is_modal_running}")
        print(f"Interactivity: {settings.use_interactivity}")
        print("-------------------------\n")
        
        self.report({'INFO'}, "Debug Info printed to Console")
        return {'FINISHED'}
