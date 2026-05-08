from bpy import context
import bpy
from bpy_extras.io_utils import ImportHelper

def add_image_to_kanvas(context, filepath, location=None):
    """Helper to add an image from a path to the Kanvas"""
    settings = context.scene.kanvas_settings
    
    # Protect the tree from being purged (Safe to write in operator context)
    space_data = getattr(context, 'space_data', None)
    if space_data and space_data.type == 'NODE_EDITOR' and getattr(space_data, 'edit_tree', None):
        tree = space_data.edit_tree
        if tree.bl_idname == 'KanvasNodeTree' and not tree.use_fake_user:
            tree.use_fake_user = True
    
    # Load image into Blender
    img = bpy.data.images.load(filepath, check_existing=True)
    
    # If no location provided, use view center
    if location is None:
        region = getattr(context, 'region', None)
        if region and getattr(region, 'view2d', None):
            v2d = region.view2d
            # Center of the region in view coordinates
            location = v2d.region_to_view(region.width / 2, region.height / 2)
        else:
            location = (0, 0)

    # Create Kanvas Item
    new_item = settings.images.add()
    new_item.name = img.name
    new_item.image_data = img
    
    new_item.location = (location[0], location[1])

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

class KANVAS_OT_AddImage(bpy.types.Operator):
    """Add a reference image silently (used by Drag & Drop)"""
    bl_idname = "kanvas.add_image"
    bl_label = "Add Reference"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH") # type: ignore

    def execute(self, context):
        if not self.filepath:
            return {'CANCELLED'}
        
        # Check if called from drop (modal handles location usually, but fallback here)
        add_image_to_kanvas(context, self.filepath)
        return {'FINISHED'}

class KANVAS_OT_AddImageBrowser(bpy.types.Operator, ImportHelper):
    """Add a new reference image via file browser"""
    bl_idname = "kanvas.add_image_browser"
    bl_label = "Add Reference"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH", options={'SKIP_SAVE'}) # type: ignore
    filter_glob: bpy.props.StringProperty( #type: ignore
        default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.webp",
        options={'HIDDEN'},
        maxlen=255,
    ) # type: ignore

    def execute(self, context):
        if not self.filepath:
            return {'CANCELLED'}
        add_image_to_kanvas(context, self.filepath)
        return {'FINISHED'}

class KANVAS_OT_AddMultipleImages(bpy.types.Operator, ImportHelper):
    """Add multiple reference images at once via file browser"""
    bl_idname = "kanvas.add_multiple_images"
    bl_label = "Add Multiple References"
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(subtype='DIR_PATH') #type: ignore
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement) #type: ignore
    
    filter_glob: bpy.props.StringProperty( #type: ignore
        default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.webp",
        options={'HIDDEN'},
        maxlen=255,
    ) # type: ignore

    def execute(self, context):
        import os
        settings = context.scene.kanvas_settings
        
        # 1. Clear selection to start fresh
        for item in settings.images:
            item.is_selected = False

        paths_to_load = [os.path.join(self.directory, f.name) for f in self.files]
        if not paths_to_load:
            return {'CANCELLED'}

        # Pre-calculate center from current context since timers won't have it
        region = getattr(context, 'region', None)
        location = (0, 0)
        if region and getattr(region, 'view2d', None):
            location = region.view2d.region_to_view(region.width / 2, region.height / 2)

        added_count = len(paths_to_load)

        def load_next_image():
            if not paths_to_load:
                # Finish up
                if added_count > 1:
                    try:
                        # Pack images safely from queue
                        bpy.ops.kanvas.pack_images()
                    except Exception as e:
                        print(f"Kanvas: Auto-pack failed: {e}")
                return None # Stops the timer
            
            path = paths_to_load.pop(0)
            try:
                # Loading individual image
                new_item = add_image_to_kanvas(bpy.context, path, location=location)
                new_item.is_selected = True
                
                # Tag redraw across all node editors
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'NODE_EDITOR':
                            area.tag_redraw()
            except Exception as e:
                print(f"Kanvas: Failed to load {path}: {e}")
            
            return 0.01 # Load next in 10ms

        # Start the queue
        bpy.app.timers.register(load_next_image, first_interval=0.01)
        
        self.report({'INFO'}, f"Started loading {added_count} images in background...")
        return {'FINISHED'}

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
            from ..utils.gpu.image import _texture_cache
            
            image = img_item.image_data
            if image:
                key = (image.name, id(image))
                if key in _texture_cache:
                    del _texture_cache[key]
            
            name = img_item.name
            settings.images.remove(self.index)
            settings.active_image_index = max(0, self.index - 1)
            
            # Deep RAM cleanup
            if image and image.users <= 1:
                try:
                    bpy.data.images.remove(image)
                except Exception as e:
                    print(f"Kanvas: Could not purge image data {name}: {e}")
            
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
        new_img.scale_master = source.scale_master
        new_img.scale_xy = source.scale_xy
        new_img.shear_xy = source.shear_xy
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
            from ..utils.gpu.image import _texture_cache
            key = (img_item.image_data.name, id(img_item.image_data))
            if key in _texture_cache:
                del _texture_cache[key]
            
            context.area.tag_redraw()
            self.report({'INFO'}, f"Refreshed {img_item.name}")
            return {'FINISHED'}
        return {'CANCELLED'}

class KANVAS_OT_PackImages(bpy.types.Operator):
    """Pack selected reference images into a clean grid."""
    bl_idname = "kanvas.pack_images"
    bl_label = "Pack Images"
    bl_options = {'REGISTER', 'UNDO'}

    gap: bpy.props.IntProperty( # type: ignore
        name="Gap",
        description="Space between packed images",
        default=40,
        min=0
    )

    def execute(self, context):
        settings = context.scene.kanvas_settings
        selected = [img for img in settings.images if img.is_selected and img.image_data]
        
        if not selected:
            self.report({'WARNING'}, "No images selected for packing")
            return {'CANCELLED'}

        from ..utils.gpu.common import get_collective_bounding_box

        # 1. Get initial data and dimensions
        data_list = []
        items_to_pack = []
        for img in selected:
            image = img.image_data
            if not image or image.size[0] == 0 or image.size[1] == 0:
                continue
            
            base_w, base_h = image.size[0], image.size[1]
            
            # Use current scale for packing dimensions
            w = base_w * img.scale_xy[0] * img.scale_master
            h = base_h * img.scale_xy[1] * img.scale_master
            
            # Store original state for bounding box calculation
            data_list.append((img.location, img.scale_xy, img.scale_master, img.shear_xy, img.rotation, base_w, base_h))
            
            items_to_pack.append({
                'img': img,
                'w': w,
                'h': h
            })

        if not items_to_pack:
            return {'CANCELLED'}

        # 2. Sort by height (descending) for shelf packing
        items_to_pack.sort(key=lambda x: x['h'], reverse=True)

        # 3. Determine start position (Top-Left of original selection)
        bbox = get_collective_bounding_box(data_list)
        if not bbox:
            return {'CANCELLED'}
            
        start_x = bbox[0]
        start_y = bbox[3] # Top
        
        # Determine target width (square-ish or original width)
        padding = self.gap
        total_area = sum((i['w'] + padding) * (i['h'] + padding) for i in items_to_pack)
        target_width = max(max(i['w'] for i in items_to_pack), (total_area ** 0.5) * 1.15)
        
        # 4. Shelf Packing
        curr_x = start_x
        curr_y = start_y
        row_max_h = 0
        
        for item in items_to_pack:
            img = item['img']
            w, h = item['w'], item['h']
            
            # If item exceeds row width, move to next shelf
            if curr_x + w > start_x + target_width and curr_x > start_x:
                curr_x = start_x
                curr_y -= (row_max_h + padding)
                row_max_h = 0
            
            # Align image
            img.rotation = 0.0 # Clean rotation for moodboard style
            img.location = (curr_x + w/2, curr_y - h/2)
            
            curr_x += (w + padding)
            row_max_h = max(row_max_h, h)

        self.report({'INFO'}, f"Packed {len(items_to_pack)} images")
        if context.area:
            context.area.tag_redraw()

        return {'FINISHED'}
