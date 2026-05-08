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
    
    key_shear_mod: bpy.props.EnumProperty(
        name="Shear Modifier",
        items=[
            ('ALT', 'Alt', 'Use Alt key'),
            ('SHIFT', 'Shift', 'Use Shift key'),
            ('CTRL', 'Ctrl', 'Use Ctrl key'),
        ],
        default='ALT'
    )

    auto_copy: bpy.props.BoolProperty( #type: ignore
        name="Auto-Copy to Assets",
        description="Automatically copy images to the project assets folder when added",
        default=True
    ) #type: ignore

    def draw(self, context):
        layout = self.layout
        
        # Main split for two columns
        main_row = layout.row()
        col_left = main_row.column()
        col_right = main_row.column()

        # --- LEFT COLUMN: SYSTEM & CONTROLS ---
        # File System Group
        box = col_left.box()
        box.label(text="Storage & Workflow", icon='FILE_FOLDER')
        box.prop(self, "assets_folder")
        box.prop(self, "auto_copy")

        col_left.separator()

        # Hotkeys Group
        box = col_left.box()
        box.label(text="Interactive Controls", icon='MOUSE_MOVE')
        
        flow = box.grid_flow(columns=2, align=True)
        flow.prop(self, "key_move", text="Move")
        flow.prop(self, "key_scale", text="Scale")
        flow.prop(self, "key_rotate", text="Rotate")
        flow.prop(self, "key_delete", text="Delete")
        
        box.separator()
        box.prop(self, "key_shear_mod", text="Shear Mod (Hold)")

        # --- RIGHT COLUMN: VISUAL STYLE ---
        box = col_right.box()
        box.label(text="Aesthetics & Visuals", icon='RESTRICT_SELECT_OFF')
        
        col = box.column(align=True)
        col.prop(self, "color_x_axis", text="X Axis Color")
        col.prop(self, "color_y_axis", text="Y Axis Color")
        col.separator()
        col.prop(self, "color_selection", text="Selection")
        col.prop(self, "selection_thickness", text="Thickness")
        
        # Add a placeholder for future visual settings
        col_right.separator()
        box = col_right.box()
        box.label(text="UI Info", icon='INFO')
        box.label(text="Kanvas Engine: Active", icon='CHECKMARK')
