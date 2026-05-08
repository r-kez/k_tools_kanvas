import bpy

def update_kanvas_image(self, context):
    if self.image_data:
        # 1. Smart Fit
        w, h = self.image_data.size
        if w > 0 and h > 0:
            val = 300.0 / max(w, h)
            self.scale_xy = (val, val)
        if self.name == "Image":
            self.name = self.image_data.name
        
        # 2. Auto-Copy Logic
        from .utils.gpu.common import get_prefs
        from .utils.file_system import copy_image_to_project
        
        prefs = get_prefs()
        if prefs and prefs.auto_copy:
            result = copy_image_to_project(self.image_data, prefs.assets_folder)
            if isinstance(result, str) and result.startswith("ERROR"):
                # We can't use self.report here as it's a PropertyGroup
                # But we can print to console
                print(f"Kanvas: {result}")

class KanvasImageItem(bpy.types.PropertyGroup): # type: ignore
    name: bpy.props.StringProperty(name="Name", default="Image") #type: ignore
    image_data: bpy.props.PointerProperty( # type: ignore
        name="Image", 
        type=bpy.types.Image,
        update=update_kanvas_image
    ) #type: ignore
    
    location: bpy.props.FloatVectorProperty(name="Location", size=2, default=(0.0, 0.0)) #type: ignore
    scale_xy: bpy.props.FloatVectorProperty(name="Stretch", size=2, default=(1.0, 1.0)) #type: ignore
    scale_master: bpy.props.FloatProperty(name="Scale", default=1.0, min=0.001) #type: ignore
    shear_xy: bpy.props.FloatVectorProperty(name="Shear", size=2, default=(0.0, 0.0)) #type: ignore
    rotation: bpy.props.FloatProperty(name="Rotation", default=0.0) #type: ignore
    opacity: bpy.props.FloatProperty(name="Opacity", default=1.0, min=0.0, max=1.0) #type: ignore
    color_tint: bpy.props.FloatVectorProperty( #type: ignore
        name="Color Tint",
        subtype='COLOR',
        size=3,
        default=(1.0, 1.0, 1.0),
        min=0.0, max=1.0
    ) #type: ignore
    
    show_in_editor: bpy.props.BoolProperty(name="Show", default=True) #type: ignore
    use_color_correction: bpy.props.BoolProperty( #type: ignore
        name="Color Correction", 
        description="Convert sRGB to Linear for correct viewport colors",
        default=True
    ) #type: ignore
    is_selected: bpy.props.BoolProperty(name="Is Selected", default=False) #type: ignore
    
    # Image Adjustments
    flip_h: bpy.props.BoolProperty(name="Flip Horizontal", default=False) #type: ignore
    flip_v: bpy.props.BoolProperty(name="Flip Vertical", default=False) #type: ignore
    brightness: bpy.props.FloatProperty(name="Brightness", default=1.0, min=0.0, max=5.0) #type: ignore
    contrast: bpy.props.FloatProperty(name="Contrast", default=1.0, min=0.0, max=5.0) #type: ignore
    saturation: bpy.props.FloatProperty(name="Saturation", default=1.0, min=0.0, max=5.0) #type: ignore

def update_active_image(self, context):
    settings = context.scene.kanvas_settings
    
    if getattr(settings, "show_box_sel", False):
        return
        
    if not settings.shift_is_held:
        for idx, img in enumerate(settings.images):
            img.is_selected = (idx == settings.active_image_index)
    else:
        if 0 <= settings.active_image_index < len(settings.images):
            settings.images[settings.active_image_index].is_selected = True

class KanvasSettings(bpy.types.PropertyGroup):
    images: bpy.props.CollectionProperty(type=KanvasImageItem) #type: ignore
    active_image_index: bpy.props.IntProperty( #type: ignore
        name="Active Image Index", 
        default=0,
        update=update_active_image
    ) #type: ignore
    
    show_all: bpy.props.BoolProperty(name="Show All", default=True) #type: ignore
    show_debug_grid: bpy.props.BoolProperty(name="Show Debug Grid", default=True) #type: ignore
    is_modal_running: bpy.props.BoolProperty(name="Is Modal Running", default=False) #type: ignore
    use_interactivity: bpy.props.BoolProperty( #type: ignore
        name="Interactivity",
        description="Allow moving and scaling images in the viewport",
        default=True
    )
    
    # Gizmo Settings
    show_gizmos: bpy.props.BoolProperty(name="Show Gizmos", default=True) #type: ignore
    gizmo_size: bpy.props.FloatProperty(name="Gizmo Size", default=25.0, min=10.0, max=100.0) #type: ignore
    show_scale_handles: bpy.props.BoolProperty(name="Scale Handles", default=True) #type: ignore
    show_rotate_handles: bpy.props.BoolProperty(name="Rotate Handles", default=True) #type: ignore

    # Snapping Settings
    use_snapping: bpy.props.BoolProperty(name="Snap", default=False) #type: ignore
    snap_grid: bpy.props.BoolProperty(name="Grid Snap", default=True) #type: ignore
    snap_images: bpy.props.BoolProperty(name="Image Snap", default=True) #type: ignore
    grid_size: bpy.props.IntProperty(name="Grid Size", default=20, min=1) #type: ignore
    snap_threshold: bpy.props.FloatProperty(name="Threshold", default=10.0, min=1.0) #type: ignore

    # Transient Snap Visualization (Not saved)
    snap_viz_x: bpy.props.FloatProperty(options={'SKIP_SAVE'}) #type: ignore
    snap_viz_y: bpy.props.FloatProperty(options={'SKIP_SAVE'}) #type: ignore
    show_snap_viz_x: bpy.props.BoolProperty(options={'SKIP_SAVE'}) #type: ignore
    show_snap_viz_y: bpy.props.BoolProperty(options={'SKIP_SAVE'}) #type: ignore

    # UI State
    shift_is_held: bpy.props.BoolProperty(options={'SKIP_SAVE'}) # type: ignore
    alt_is_held: bpy.props.BoolProperty(options={'SKIP_SAVE'}) # type: ignore
    ctrl_is_held: bpy.props.BoolProperty(options={'SKIP_SAVE'}) # type: ignore

    # Box Selection (Transient)
    box_sel_start: bpy.props.FloatVectorProperty(size=2, options={'SKIP_SAVE'}) # type: ignore
    box_sel_end: bpy.props.FloatVectorProperty(size=2, options={'SKIP_SAVE'}) # type: ignore
    show_box_sel: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'}) # type: ignore

class KanvasNodeTree(bpy.types.NodeTree): # type: ignore
    """A custom node tree for managing Kanvas references."""
    bl_idname = 'KanvasNodeTree'
    bl_label = 'Kanvas Tree'
    bl_icon = 'IMAGE'

def register():
    bpy.types.Scene.kanvas_settings = bpy.props.PointerProperty(type=KanvasSettings)

def unregister():
    del bpy.types.Scene.kanvas_settings
