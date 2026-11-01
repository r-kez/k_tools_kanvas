import bpy
from ..utils.kanvas_data import get_settings
from .kanvas_context import KanvasTreeOnly

class KANVAS_OT_ClearListSearch(KanvasTreeOnly, bpy.types.Operator):
    """Clear the item list search filter"""
    bl_idname = "kanvas.clear_list_search"
    bl_label = "Clear Search"
    bl_description = 'Show all items in the list again'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        get_settings(context).list_search = ''
        return {'FINISHED'}


class KANVAS_OT_ResetSettings(KanvasTreeOnly, bpy.types.Operator):
    """Reset all Kanvas settings to default values"""
    bl_idname = "kanvas.reset_settings"
    bl_label = "Reset All Settings"
    bl_description = 'Clear the current Kanvas board and restore default settings'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = get_settings(context)
        settings.images.clear()
        settings.show_debug_grid = True
        settings.show_gizmos = True
        settings.gizmo_size = 8.0
        context.area.tag_redraw()
        self.report({'INFO'}, "Kanvas Settings Reset")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

class KANVAS_OT_ClearCache(KanvasTreeOnly, bpy.types.Operator):
    """Clear the GPU texture cache (Force re-upload of all images)"""
    bl_idname = "kanvas.clear_cache"
    bl_label = "Clear GPU Cache"
    bl_description = 'Discard cached image textures so they are rebuilt on the next draw'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        from ..utils.gpu.gpu_image import clear_texture_cache
        clear_texture_cache()
        context.area.tag_redraw()
        self.report({'INFO'}, "GPU Cache Cleared")
        return {'FINISHED'}

class KANVAS_OT_ReloadShader(KanvasTreeOnly, bpy.types.Operator):
    """Force re-compilation of the custom GPU shader"""
    bl_idname = "kanvas.reload_shader"
    bl_label = "Reload Custom Shader"
    bl_description = 'Recompile the Kanvas drawing shader'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        from ..utils.gpu.gpu_common import clear_kanvas_shader
        clear_kanvas_shader()
        context.area.tag_redraw()
        context.area.tag_redraw()
        self.report({'INFO'}, "Shader Reloaded")
        return {'FINISHED'}

class KANVAS_OT_DebugInfo(KanvasTreeOnly, bpy.types.Operator):
    """Print diagnostic information to the system console"""
    bl_idname = "kanvas.debug_info"
    bl_label = "Print Debug Info"
    bl_description = 'Print board and texture diagnostics to the Blender console'
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = get_settings(context)
        from ..utils.gpu.gpu_image import _texture_cache
        
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
