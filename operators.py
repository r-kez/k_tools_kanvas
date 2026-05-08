import bpy

def add_image_to_kanvas(context, filepath, location=(0, 0)):
    """Helper to add an image from a path to the Kanvas"""
    settings = context.scene.kanvas_settings
    
    # Load image into Blender
    img = bpy.data.images.load(filepath, check_existing=True)
    
    # Create Kanvas Item
    new_item = settings.images.add()
    new_item.name = img.name
    new_item.image_data = img
    new_item.location = location
    
    # Trigger auto-copy logic if enabled (it's in the property update)
    # Actually, the property update triggers when image_data is SET.
    
    # Select the new one
    settings.active_image_index = len(settings.images) - 1
    return new_item

class KANVAS_FH_ImageHandler(bpy.types.FileHandler):
    """File handler for drag-and-dropping image files into Kanvas."""
    bl_idname = "KANVAS_FH_ImageHandler"
    bl_label = "Kanvas Image Drop Handler"
    bl_file_extensions = ".png;.jpg;.jpeg;.tga;.tif;.tiff;.webp"
    
    # This links the drop directly to our operator
    bl_import_operator = "kanvas.add_image"

    @classmethod
    def poll_drop(cls, context):
        # Only handle if we are in a Kanvas Node Editor
        return context.space_data.type == 'NODE_EDITOR' and \
               context.space_data.edit_tree and \
               context.space_data.edit_tree.bl_idname == 'KanvasNodeTree'

from bpy_extras.io_utils import ImportHelper

class KANVAS_OT_AddImage(bpy.types.Operator, ImportHelper):
    """Add a new reference image (from Browser or Drag & Drop)"""
    bl_idname = "kanvas.add_image"
    bl_label = "Add Reference"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH", options={'SKIP_SAVE'}) # type: ignore

    filter_glob: bpy.props.StringProperty( #type: ignore
        default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.webp",
        options={'HIDDEN'},
        maxlen=255,
    ) #type: ignore

    def execute(self, context):
        if not self.filepath:
            return {'CANCELLED'}
            
        add_image_to_kanvas(context, self.filepath)
        return {'FINISHED'}

    def invoke(self, context, event):
        # If filepath is already provided (by Drag & Drop), skip the browser
        if self.filepath:
            return self.execute(context)
            
        # Otherwise, open the file browser
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class KANVAS_OT_RemoveImage(bpy.types.Operator):
    """Remove a reference image from the Kanvas (supports Undo)"""
    bl_idname = "kanvas.remove_image"
    bl_label = "Remove Image?"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty() #type: ignore

    def execute(self, context):
        settings = context.scene.kanvas_settings
        if 0 <= self.index < len(settings.images):
            img_item = settings.images[self.index]
            
            # Clear GPU cache for this name
            from .utils.gpu_draw import _texture_cache
            if img_item.image_data and img_item.image_data.name in _texture_cache:
                del _texture_cache[img_item.image_data.name]
            
            name = img_item.name
            settings.images.remove(self.index)
            settings.active_image_index = max(0, self.index - 1)
            self.report({'INFO'}, f"Removed {name}")
            return {'FINISHED'}
        return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

class KANVAS_OT_DuplicateImage(bpy.types.Operator):
    """Duplicate the active reference image (supports Undo)"""
    bl_idname = "kanvas.duplicate_image"
    bl_label = "Duplicate Image"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.kanvas_settings
        if not settings.images or settings.active_image_index >= len(settings.images):
            return {'CANCELLED'}
        
        source = settings.images[settings.active_image_index]
        new_img = settings.images.add()
        
        # Copy properties
        new_img.name = f"{source.name}_copy"
        new_img.image_data = source.image_data
        new_img.location = source.location
        new_img.scale = source.scale
        new_img.rotation = source.rotation
        new_img.opacity = source.opacity
        new_img.color_tint = source.color_tint
        
        # Select the new one
        settings.active_image_index = len(settings.images) - 1
        
        self.report({'INFO'}, f"Duplicated {source.name}")
        return {'FINISHED'}

class KANVAS_OT_RefreshImage(bpy.types.Operator):
    """Force re-load of the active image from Blender to GPU cache"""
    bl_idname = "kanvas.refresh_image"
    bl_label = "Refresh Image"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.kanvas_settings
        if not settings.images or settings.active_image_index >= len(settings.images):
            return {'CANCELLED'}
            
        img_item = settings.images[settings.active_image_index]
        if img_item.image_data:
            # Clear GPU cache for this name
            from .utils.gpu_draw import _texture_cache
            if img_item.image_data.name in _texture_cache:
                del _texture_cache[img_item.image_data.name]
            
            context.area.tag_redraw()
            self.report({'INFO'}, f"Refreshed {img_item.name}")
            return {'FINISHED'}
        return {'CANCELLED'}

class KANVAS_OT_Modal(bpy.types.Operator):
    """Interactive mode for Kanvas: Select and Move images"""
    bl_idname = "kanvas.modal"
    bl_label = "Kanvas Interactivity"
    bl_options = {'REGISTER', 'UNDO'}

    # State variables
    drag_target = None
    drag_mode = 'MOVE' # 'MOVE', 'SCALE', 'ROTATE'
    active_gizmo = -1 # -1 to 7
    last_mouse_pos = (0, 0)
    initial_scale = 1.0
    initial_rotation = 0.0
    initial_angle = 0.0

    def get_angle(self, center, mouse):
        import math
        return math.degrees(math.atan2(mouse[1] - center[1], mouse[0] - center[0]))

    def get_gizmo_under_mouse(self, context, mouse_pos):
        settings = context.scene.kanvas_settings
        if settings.active_image_index >= len(settings.images):
            return -1
        
        img = settings.images[settings.active_image_index]
        if not img.show_in_editor or not img.image_data or not settings.show_gizmos:
            return -1

        from .utils.gpu_draw import get_kanvas_texture, rotate_point
        tex_manager = get_kanvas_texture(img.image_data)
        if not tex_manager.texture:
            return -1

        w = tex_manager.texture.width * img.scale
        h = tex_manager.texture.height * img.scale
        x_mid, y_mid = img.location[0], img.location[1]

        # 8 Handle positions (Pre-rotation)
        handles = [
            (img.location[0] - w/2, img.location[1] - h/2), (x_mid, img.location[1] - h/2), (img.location[0] + w/2, img.location[1] - h/2),
            (img.location[0] - w/2, y_mid),                                                 (img.location[0] + w/2, y_mid),
            (img.location[0] - w/2, img.location[1] + h/2), (x_mid, img.location[1] + h/2), (img.location[0] + w/2, img.location[1] + h/2)
        ]

        s = settings.gizmo_size
        for idx, h_pos in enumerate(handles):
            rh_pos = rotate_point(h_pos, img.location, img.rotation)
            if rh_pos[0] - s <= mouse_pos[0] <= rh_pos[0] + s and \
               rh_pos[1] - s <= mouse_pos[1] <= rh_pos[1] + s:
                return idx
        return -1

    def modal(self, context, event):
        settings = context.scene.kanvas_settings
        from .utils.gpu_draw import get_prefs
        prefs = get_prefs()

        # Convert mouse to view2d coordinates
        region = context.region
        v2d = region.view2d
        mouse_x, mouse_y = v2d.region_to_view(event.mouse_region_x, event.mouse_region_y)

        # 1. Hotkey Handling
        if event.value == 'PRESS':
            key = event.type
            # We assume the user typed "G", "S", "R", "X" in preferences
            # event.type is 'G', 'S', 'R', 'X' etc.
            
            if key == prefs.key_move:
                self.drag_mode = 'MOVE'
                self.drag_target = settings.images[settings.active_image_index] if settings.images else None
                return {'RUNNING_MODAL'}
            
            elif key == prefs.key_scale:
                self.drag_mode = 'SCALE'
                self.drag_target = settings.images[settings.active_image_index] if settings.images else None
                return {'RUNNING_MODAL'}
            
            elif key == prefs.key_rotate:
                self.drag_mode = 'ROTATE'
                self.drag_target = settings.images[settings.active_image_index] if settings.images else None
                if self.drag_target:
                    self.initial_rotation = self.drag_target.rotation
                    self.initial_angle = self.get_angle(self.drag_target.location, (mouse_x, mouse_y))
                return {'RUNNING_MODAL'}
            
            elif key == 'D' and event.shift:
                # Duplicate
                bpy.ops.kanvas.duplicate_image()
                # Immediately start moving the duplicate
                self.drag_mode = 'MOVE'
                self.drag_target = settings.images[settings.active_image_index]
                self.last_mouse_pos = (mouse_x, mouse_y)
                return {'RUNNING_MODAL'}
            
            elif key == prefs.key_delete:
                if settings.images and settings.active_image_index < len(settings.images):
                    # Call the removal operator which has confirmation
                    bpy.ops.kanvas.remove_image('INVOKE_DEFAULT', index=settings.active_image_index)
                return {'RUNNING_MODAL'}

        # Handle Mouse Wheel for Opacity (Interactive)
        if event.type in {'WHEELUP_MOUSE', 'WHEELDOWN_MOUSE'}:
            if settings.images and settings.active_image_index < len(settings.images):
                img = settings.images[settings.active_image_index]
                delta = 0.05 if event.type == 'WHEELUP_MOUSE' else -0.05
                img.opacity = max(0.0, min(1.0, img.opacity + delta))
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                # Check for Gizmos first
                gizmo_idx = self.get_gizmo_under_mouse(context, (mouse_x, mouse_y))
                if gizmo_idx != -1:
                    self.drag_mode = 'SCALE'
                    self.active_gizmo = gizmo_idx
                    self.drag_target = settings.images[settings.active_image_index]
                    self.initial_scale = self.drag_target.scale
                    self.last_mouse_pos = (mouse_x, mouse_y)
                    return {'RUNNING_MODAL'}

                # Selection Logic
                self.drag_target = None
                self.drag_mode = 'MOVE'
                # Deselect all first
                for img in settings.images:
                    img.is_selected = False

                # Find image under mouse (reverse order to get top-most)
                for idx in range(len(settings.images) - 1, -1, -1):
                    img = settings.images[idx]
                    if not img.show_in_editor or not img.image_data:
                        continue
                    
                    from .utils.gpu_draw import get_kanvas_texture, rotate_point
                    tex_manager = get_kanvas_texture(img.image_data)
                    if tex_manager.texture:
                        w = tex_manager.texture.width * img.scale
                        h = tex_manager.texture.height * img.scale
                        
                        # For selection, we should check the rotated bounds.
                        # For simplicity, we can just check if mouse is inside the oriented rectangle.
                        # Better approach: rotate the mouse position INVERSELY and check vs AABB.
                        from .utils.gpu_draw import rotate_point
                        inv_mouse = rotate_point((mouse_x, mouse_y), img.location, -img.rotation)
                        
                        x_min, x_max = img.location[0] - w/2, img.location[0] + w/2
                        y_min, y_max = img.location[1] - h/2, img.location[1] + h/2

                        if x_min <= inv_mouse[0] <= x_max and y_min <= inv_mouse[1] <= y_max:
                            # Selection and Z-Depth Sorting
                            settings.images.move(idx, len(settings.images) - 1)
                            new_idx = len(settings.images) - 1
                            img = settings.images[new_idx]
                            img.is_selected = True
                            settings.active_image_index = new_idx
                            self.drag_target = img
                            self.last_mouse_pos = (mouse_x, mouse_y)
                            context.area.tag_redraw()
                            return {'RUNNING_MODAL'}
                
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            elif event.value == 'RELEASE':
                # Only stop dragging if we are in a temporary mode (like Gizmo drag)
                # Native G/S/R modes in Blender usually stay until ENTER or click.
                # But here we stick to the user's request for drag-and-drop feel.
                self.drag_target = None
                self.drag_mode = 'MOVE'
                return {'RUNNING_MODAL'}

        elif event.type == 'MOUSEMOVE':
            if self.drag_target:
                if self.drag_mode == 'MOVE':
                    dx = mouse_x - self.last_mouse_pos[0]
                    dy = mouse_y - self.last_mouse_pos[1]
                    self.drag_target.location[0] += dx
                    self.drag_target.location[1] += dy
                
                elif self.drag_mode == 'SCALE':
                    center = self.drag_target.location
                    dist_init = ((self.last_mouse_pos[0] - center[0])**2 + (self.last_mouse_pos[1] - center[1])**2)**0.5
                    dist_curr = ((mouse_x - center[0])**2 + (mouse_y - center[1])**2)**0.5
                    if dist_init > 0:
                        self.drag_target.scale *= (dist_curr / dist_init)
                
                elif self.drag_mode == 'ROTATE':
                    # Rotate logic
                    curr_angle = self.get_angle(self.drag_target.location, (mouse_x, mouse_y))
                    diff = curr_angle - self.initial_angle
                    self.drag_target.rotation = self.initial_rotation + diff
                
                self.last_mouse_pos = (mouse_x, mouse_y)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

        elif event.type in {'ESC', 'RIGHTMOUSE'}:
            # Exit modal
            for img in settings.images:
                img.is_selected = False
            
            settings.is_modal_active = False
            context.area.tag_redraw()
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if context.area.type == 'NODE_EDITOR':
            self.drag_target = None
            self.last_mouse_pos = (event.mouse_region_x, event.mouse_region_y)
            
            context.scene.kanvas_settings.is_modal_active = True
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Node Editor not found")
            return {'CANCELLED'}

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
        from .utils.gpu_draw import _texture_cache
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
        from .utils import gpu_draw
        gpu_draw._kanvas_shader = None
        context.area.tag_redraw()
        self.report({'INFO'}, "Shader Reloaded")
        return {'FINISHED'}

class KANVAS_OT_DebugInfo(bpy.types.Operator):
    """Print diagnostic information to the system console"""
    bl_idname = "kanvas.debug_info"
    bl_label = "Print Debug Info"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.kanvas_settings
        from .utils.gpu_draw import _texture_cache
        
        print("\n--- KANVAS DEBUG INFO ---")
        print(f"Total Images: {len(settings.images)}")
        print(f"Cached Textures: {len(_texture_cache)}")
        for name in _texture_cache.keys():
            print(f"  - {name}")
        print(f"Modal Active: {settings.is_modal_active}")
        print("-------------------------\n")
        
        self.report({'INFO'}, "Debug Info printed to Console")
        return {'FINISHED'}
