import bpy

def update_kanvas_image(self, context):
    if self.image_data:
        # 1. Smart Fit
        w, h = self.image_data.size
        if w > 0 and h > 0:
            self.scale = 300.0 / max(w, h)
        if self.name == "Image":
            self.name = self.image_data.name
        
        # 2. Auto-Copy Logic
        from .utils.gpu_draw import get_prefs
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
    scale: bpy.props.FloatProperty(name="Scale", default=1.0) #type: ignore
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
    use_color_correction: bpy.props.BoolProperty(
        name="Color Correction", 
        description="Convert sRGB to Linear for correct viewport colors",
        default=True
    ) #type: ignore
    is_selected: bpy.props.BoolProperty(name="Is Selected", default=False) #type: ignore

def update_active_image(self, context):
    settings = context.scene.kanvas_settings
    for idx, img in enumerate(settings.images):
        img.is_selected = (idx == settings.active_image_index)

class KanvasSettings(bpy.types.PropertyGroup):
    images: bpy.props.CollectionProperty(type=KanvasImageItem) #type: ignore
    active_image_index: bpy.props.IntProperty( #type: ignore
        name="Active Image Index", 
        default=0,
        update=update_active_image
    ) #type: ignore
    
    show_all: bpy.props.BoolProperty(name="Show All", default=True) #type: ignore
    show_debug_grid: bpy.props.BoolProperty(name="Show Debug Grid", default=True) #type: ignore
    is_modal_active: bpy.props.BoolProperty(name="Is Modal Active", default=False) #type: ignore
    
    show_gizmos: bpy.props.BoolProperty(name="Show Gizmos", default=True) #type: ignore
    gizmo_size: bpy.props.FloatProperty(name="Gizmo Size", default=8.0, min=4.0, max=20.0) #type: ignore

def register():
    bpy.types.Scene.kanvas_settings = bpy.props.PointerProperty(type=KanvasSettings)

def unregister():
    del bpy.types.Scene.kanvas_settings
