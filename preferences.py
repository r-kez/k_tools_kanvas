import bpy

class KanvasPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    assets_folder: bpy.props.StringProperty( #type: ignore
        name="Assets Folder",
        description="Folder where reference images will be stored relative to the .blend file",
        default="assets/kanvas-ref/",
        subtype='DIR_PATH'
    )

    # Design Tokens
    color_x_axis: bpy.props.FloatVectorProperty( #type: ignore
        name="X Axis Color",
        subtype='COLOR',
        size=4,
        default=(1.0, 0.2, 0.2, 0.5),
        min=0.0, max=1.0
    ) #type: ignore

    color_y_axis: bpy.props.FloatVectorProperty( #type: ignore
        name="Y Axis Color",
        subtype='COLOR',
        size=4,
        default=(0.2, 1.0, 0.2, 0.5),
        min=0.0, max=1.0
    ) #type: ignore

    color_selection: bpy.props.FloatVectorProperty( #type: ignore
        name="Selection Color",
        subtype='COLOR',
        size=4,
        default=(0.0, 0.8, 1.0, 1.0),
        min=0.0, max=1.0
    ) #type: ignore

    selection_thickness: bpy.props.FloatProperty( #type: ignore
        name="Outline Thickness",
        default=2.0,
        min=1.0, max=10.0
    ) #type: ignore

    # Hotkeys
    key_move: bpy.props.StringProperty(name="Move Key", default="G") #type: ignore
    key_scale: bpy.props.StringProperty(name="Scale Key", default="S") #type: ignore
    key_rotate: bpy.props.StringProperty(name="Rotate Key", default="R") #type: ignore
    key_delete: bpy.props.StringProperty(name="Delete Key", default="X") #type: ignore

    auto_copy: bpy.props.BoolProperty( #type: ignore
        name="Auto-Copy to Assets",
        description="Automatically copy images to the project assets folder when added",
        default=True
    ) #type: ignore

    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="File System", icon='FILE_FOLDER')
        box.prop(self, "assets_folder")
        box.prop(self, "auto_copy")

        box = layout.box()
        box.label(text="Visual Style", icon='RESTRICT_SELECT_OFF')
        
        split = box.split(factor=0.5)
        col = split.column()
        col.prop(self, "color_x_axis")
        col.prop(self, "color_y_axis")
        
        col = split.column()
        col.prop(self, "color_selection")
        col.prop(self, "selection_thickness")

        box = layout.box()
        box.label(text="Hotkeys (Interactive Mode)", icon='IMAGE')
        grid = box.grid_flow(columns=4, align=True)
        grid.prop(self, "key_move", text="Move")
        grid.prop(self, "key_scale", text="Scale")
        grid.prop(self, "key_rotate", text="Rotate")
        grid.prop(self, "key_delete", text="Delete")
