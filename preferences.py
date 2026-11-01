import bpy


def _update_hide_datablocks(self, context):
    import bpy
    from .utils.hidden_datablocks import sweep
    # Deferred: a property update must not rename datablocks while Blender draws.
    bpy.app.timers.register(lambda: sweep(), first_interval=0.0)


def _update_axis_appearance(self, context):
    manager = getattr(context, 'window_manager', None)
    if manager is None:
        return
    for window in manager.windows:
        for area in window.screen.areas:
            if area.type == 'NODE_EDITOR':
                area.tag_redraw()

class KANVAS_OT_prefs_select_dir(bpy.types.Operator):
    bl_idname = "kanvas.prefs_select_dir"
    bl_label = "Select Directory"
    bl_options = {'REGISTER', 'INTERNAL'}

    directory: bpy.props.StringProperty(subtype='DIR_PATH') #type: ignore

    relative_path: bpy.props.BoolProperty( #type: ignore
        name="Relative Path",
        default=True,
        description="Enable relative path by default"
    )

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        prefs.assets_folder = self.directory
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class KanvasPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    category: bpy.props.EnumProperty( #type: ignore
        name="Category",
        description="Configuration category",
        items=[
            ('GENERAL', "General", "Storage, workflow, and memory optimization", 'SETTINGS', 0),
            ('CONTROLS', "Controls", "Keymap shortcuts, gestures, and mouse navigation", 'MOUSE_MOVE', 1),
            ('AESTHETICS', "Aesthetics", "Theme colors, axis styling, and selection appearance", 'RESTRICT_SELECT_OFF', 2),
            ('ABOUT', "About", "Add-on information and quick start guide", 'INFO', 3),
        ],
        default='GENERAL',
    )

    # Removed subtype='DIR_PATH' to avoid Blender warnings with '//' prefix
    assets_folder: bpy.props.StringProperty( #type: ignore
        name="Assets Folder",
        description="Folder where reference images will be stored relative to the .blend file",
        default="//assets/kanvas"
    )

    # Design Tokens
    visual_theme: bpy.props.EnumProperty( #type: ignore
        name="Canvas Style",
        description="Visual style of items drawn on the Kanvas canvas",
        items=[
            ('CLASSIC', "Classic", "Original Kanvas appearance"),
            ('STUDIO', "Studio", "Rounded cards, refined borders and soft accents"),
            ('GLASS', "Glass", "Translucent cards with soft highlights and bright edges"),
        ],
        default='CLASSIC',
        update=_update_axis_appearance,
    )

    text_shadow_enabled: bpy.props.BoolProperty(  # type: ignore
        name="Soft Text Shadow",
        description="Add a subtle contrast halo behind Kanvas card text, frame titles, and arrow labels",
        default=True,
        update=_update_axis_appearance,
    )

    text_shadow_strength: bpy.props.FloatProperty(  # type: ignore
        name="Shadow Strength",
        description="Strength of the text shadow; 50% matches the original soft shadow",
        default=0.5, min=0.0, max=1.0, subtype='FACTOR',
        update=_update_axis_appearance,
    )

    text_shadow_spread: bpy.props.EnumProperty(  # type: ignore
        name="Shadow Spread",
        description="Choose how far the contrast shadow extends around letters",
        items=[
            ('TIGHT', 'Tight', 'Subtle 3×3 soft shadow'),
            ('WIDE', 'Wide', 'Broader 5×5 soft shadow'),
            ('OUTLINE', 'Outline', 'Defined outline around each letter'),
            ('DIFFUSE', 'Diffuse', 'Broad soft halo on large text; small text uses the faster Wide shadow'),
        ],
        default='TIGHT',
        update=_update_axis_appearance,
    )

    text_shadow_diffuse_reach: bpy.props.FloatProperty(  # type: ignore
        name="Diffuse Reach",
        description="Scale the radius of the broad shadow around large letters",
        default=1.0, min=0.5, max=2.0,
        update=_update_axis_appearance,
    )

    arrow_style: bpy.props.EnumProperty(  # type: ignore
        name="Arrow Style",
        description="Style used by every Kanvas arrow",
        items=[
            ('SOLID', 'Filled', 'Filled arrowhead'),
            ('ROUNDED', 'Rounded Stroke', 'Open V-shaped head with rounded strokes'),
        ],
        default='SOLID',
        update=_update_axis_appearance,
    )

    canvas_background_enabled: bpy.props.BoolProperty( #type: ignore
        name="Solid Background",
        description="Cover the native Node Editor background in Kanvas only",
        default=False, update=_update_axis_appearance,
    )
    canvas_background_color: bpy.props.FloatVectorProperty( #type: ignore
        name="Background Color",
        description="Color of the optional solid Kanvas canvas background",
        subtype='COLOR', size=3,
        default=(0.075, 0.085, 0.105),
        min=0.0, max=1.0, update=_update_axis_appearance,
    )
    canvas_grid_enabled: bpy.props.BoolProperty( #type: ignore
        name="Grid Lines",
        description="Draw square guide lines aligned to the native Node Editor dots",
        default=False, update=_update_axis_appearance,
    )
    canvas_grid_color: bpy.props.FloatVectorProperty( #type: ignore
        name="Grid Color",
        description="Color and opacity of the optional square guide grid",
        subtype='COLOR', size=4,
        default=(0.36, 0.42, 0.5, 0.26),
        min=0.0, max=1.0, update=_update_axis_appearance,
    )

    color_x_axis: bpy.props.FloatVectorProperty( #type: ignore
        name="X Axis Color",
        description="Color of the horizontal canvas origin axis",
        subtype='COLOR',
        size=4,
        default=(1.0, 0.2, 0.2, 0.5),
        min=0.0, max=1.0,
        update=_update_axis_appearance,
    )

    color_y_axis: bpy.props.FloatVectorProperty( #type: ignore
        name="Y Axis Color",
        description="Color of the vertical canvas origin axis",
        subtype='COLOR',
        size=4,
        default=(0.2, 1.0, 0.2, 0.5),
        min=0.0, max=1.0,
        update=_update_axis_appearance,
    )

    color_selection: bpy.props.FloatVectorProperty( #type: ignore
        name="Selection Color",
        description="Color of selected item outlines and transform handles",
        subtype='COLOR',
        size=4,
        default=(0.0, 0.8, 1.0, 1.0),
        min=0.0, max=1.0,
        update=_update_axis_appearance,
    )

    color_arrow_curve_handle: bpy.props.FloatVectorProperty( #type: ignore
        name="Arrow Curve Handle",
        description="Color of the selected arrow's middle curvature handle",
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0, max=1.0,
        update=_update_axis_appearance,
    )

    color_arrow_endpoint_handles: bpy.props.FloatVectorProperty( #type: ignore
        name="Arrow Endpoint Handles",
        description="Color of the selected arrow's start and end handles",
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0, max=1.0,
        update=_update_axis_appearance,
    )

    gizmo_background: bpy.props.BoolProperty( #type: ignore
        name="Gizmo Background",
        description="Draw a subtle background behind transform icons for contrast",
        default=False,
        update=_update_axis_appearance,
    )

    selection_thickness: bpy.props.FloatProperty( #type: ignore
        name="Outline Thickness",
        description="Thickness of selected image outlines in screen pixels",
        default=2.0,
        min=1.0, max=10.0
    )

    # Gesture options; keyboard shortcuts use Blender's keymap editor below.
    box_select_on_drag: bpy.props.BoolProperty( #type: ignore
        name="Select with Background Drag",
        description="Left drag on the canvas, including frame bodies, starts box selection",
        default=True,
    )
    box_select_alt_drag: bpy.props.BoolProperty( #type: ignore
        name="Keep Alt + Drag Selection",
        description="Also allow the previous Alt + left drag gesture",
        default=True,
    )
    card_wheel_scroll: bpy.props.EnumProperty( #type: ignore
        name="Scroll Text Cards with Wheel",
        description="Use the mouse wheel to scroll long text cards and checklists",
        items=[
            ('SELECTED', 'Selected Cards', 'The wheel scrolls a card only while it is selected, so zooming is never interrupted by accident'),
            ('HOVER', 'Any Hovered Card', 'The wheel scrolls any scrollable card under the pointer, which also stops zooming while the pointer is over one'),
            ('OFF', 'Off', 'The wheel always zooms; drag the scrollbar instead'),
        ],
        default='SELECTED',
    )
    wheel_opacity_mod: bpy.props.EnumProperty( #type: ignore
        name="Opacity Scroll Modifier",
        description="Modifier held while scrolling to change image opacity",
        items=[('CTRL', 'Ctrl', ''), ('SHIFT', 'Shift', ''), ('ALT', 'Alt', '')],
        default='CTRL',
    )
    wheel_scale_mod: bpy.props.EnumProperty( #type: ignore
        name="Scale Scroll Modifier",
        description="Modifier held while scrolling to scale the active image",
        items=[('CTRL', 'Ctrl', ''), ('SHIFT', 'Shift', ''), ('ALT', 'Alt', '')],
        default='SHIFT',
    )
    wheel_layer_mod: bpy.props.EnumProperty( #type: ignore
        name="Layer Scroll Modifier",
        description="Modifier held while scrolling to change image drawing order",
        items=[('CTRL', 'Ctrl', ''), ('SHIFT', 'Shift', ''), ('ALT', 'Alt', '')],
        default='ALT',
    )
    
    key_shear_mod: bpy.props.EnumProperty( #type: ignore
        name="Shear Modifier",
        description="Modifier held on an edge handle to shear an image",
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
    )

    show_debug_panel: bpy.props.BoolProperty( #type: ignore
        name="Show Debug Panel",
        description="Show Kanvas debugging tools in the sidebar",
        default=False,
        update=_update_axis_appearance,
    )

    hide_datablocks: bpy.props.BoolProperty( #type: ignore
        name="Hide Kanvas Images in Blender Lists",
        description=("Prefix the images Kanvas uses (your pictures, masks, color layers, "
                     "icons) with a dot, so Blender's image pickers do not list them. "
                     "They still appear in the Outliner's Blender File view; turn this off "
                     "to restore the normal names"),
        default=True,
        update=lambda self, context: _update_hide_datablocks(self, context),
    )

    show_mode_overlay: bpy.props.BoolProperty( #type: ignore
        name="Show Edit/Move Overlay",
        description="Show the Edit / Move switch at the top of the canvas (Tab still toggles the mode)",
        default=True,
        update=_update_axis_appearance,
    )

    show_text_edit_button: bpy.props.BoolProperty( #type: ignore
        name="Show Text Card Edit Button",
        description="Show an edit button on text cards and checklists in the canvas",
        default=True,
        update=_update_axis_appearance,
    )

    use_optimization: bpy.props.BoolProperty( #type: ignore
        name="Optimization",
        description="Enable memory optimization when loading images to save RAM/VRAM",
        default=True
    )

    max_image_resolution: bpy.props.EnumProperty( #type: ignore
        name="Max Resolution",
        description="Limit the resolution of imported images to save RAM/VRAM",
        items=[
            ('0', "Original (No Limit)", "Keep original resolution"),
            ('720', "720p (Fastest)", "Limit longest edge to 720px"),
            ('1080', "1080p (Balanced)", "Limit longest edge to 1080px"),
            ('2048', "2K (High Quality)", "Limit longest edge to 2048px"),
        ],
        default='1080'
    )

    force_8bit: bpy.props.BoolProperty( #type: ignore
        name="Force 8-bit Depth",
        description="Convert imported images to 8-bit depth to save VRAM",
        default=True
    )

    texture_budget_mb: bpy.props.IntProperty( #type: ignore
        name="Texture Memory Budget (MB)",
        description=("Estimated GPU memory Kanvas may keep resident. Keeping images loaded "
                     "avoids a stutter when zooming out over the whole board; the least "
                     "recently used images are released above this limit"),
        default=2048, min=256, max=65536,
    )

    def draw(self, context):
        layout = self.layout

        # Category Tabs
        row = layout.row(align=True)
        row.scale_y = 1.25
        row.prop(self, "category", expand=True)

        layout.separator(factor=0.8)

        # Draw content by active category
        if self.category == 'GENERAL':
            self._draw_general(context, layout)
        elif self.category == 'CONTROLS':
            self._draw_controls(context, layout)
        elif self.category == 'AESTHETICS':
            self._draw_aesthetics(context, layout)
        elif self.category == 'ABOUT':
            self._draw_about(context, layout)

    def _draw_segmentation(self, layout):
        from .utils import sam_engine
        box = layout.box()
        box.label(text="Auto Select (Segment Anything)", icon='VIEWZOOM')
        column = box.column(align=True)
        column.label(text="Optional. Nothing runs until you press Analyze Image")
        column.label(text="in Mask or Color mode. Uses MobileSAM, " + sam_engine.MODEL_LICENSE)
        engine_ok, model_ok = sam_engine.engine_ready(), sam_engine.models_ready()
        engine, model = sam_engine.snapshot('engine'), sam_engine.snapshot('model')

        row = box.row(align=True)
        row.label(text="ONNX Runtime" + (" installed" if engine_ok else " (about 50 MB)"),
                  icon='CHECKMARK' if engine_ok else 'X')
        sub = row.row(align=True)
        sub.enabled = not engine_ok and engine['state'] != 'working'
        sub.operator("kanvas.sam_install_engine", text="Install", icon='IMPORT')
        if engine['state'] in {'working', 'error'} and engine['message']:
            box.label(text=engine['message'][:90],
                      icon='ERROR' if engine['state'] == 'error' else 'TIME')

        row = box.row(align=True)
        row.label(text="Model" + (" downloaded" if model_ok else " (about 45 MB)"),
                  icon='CHECKMARK' if model_ok else 'X')
        sub = row.row(align=True)
        sub.enabled = not model_ok and model['state'] != 'working'
        sub.operator("kanvas.sam_download_model", text="Download", icon='IMPORT')
        if model['state'] == 'working':
            box.label(text=f"{model['message']}  {model['progress'] * 100:.0f}%", icon='TIME')
        elif model['state'] == 'error':
            box.label(text=model['message'][:90], icon='ERROR')

        if engine_ok or model_ok:
            row = box.row(align=True)
            row.label(text=f"Using {sam_engine.folder_size_mb():.0f} MB in {sam_engine.data_dir()}")
            row.operator("kanvas.sam_remove_files", text="", icon='TRASH')

    def _draw_general(self, context, layout):
        col = layout.column()

        # Storage & Workflow Box
        box = col.box()
        box.label(text="Storage & Workflow", icon='FILE_FOLDER')

        row = box.row(align=True)
        row.prop(self, "assets_folder", text="")
        row.operator("kanvas.prefs_select_dir", icon='FILE_FOLDER', text="")

        if self.assets_folder.startswith("//"):
            if bpy.data.filepath:
                abs_path = bpy.path.abspath(self.assets_folder)
                row = box.row()
                row.alignment = 'RIGHT'
                row.label(text=f"Resolved: {abs_path}", icon='LINKED')
            else:
                row = box.row()
                row.alignment = 'RIGHT'
                row.label(text="(Save .blend to resolve relative path)", icon='ERROR')

        box.prop(self, "auto_copy")

        col.separator()

        # Memory Optimization Box
        box = col.box()
        box.label(text="Memory Optimization", icon='MEMORY')
        box.prop(self, "use_optimization")
        box.prop(self, "texture_budget_mb")

        if self.use_optimization:
            opt_col = box.column(align=True)
            opt_col.prop(self, "max_image_resolution")
            opt_col.prop(self, "force_8bit")

        col.separator()
        box = col.box()
        box.label(text="Interface", icon='PREFERENCES')
        box.prop(self, "show_debug_panel")
        box.prop(self, "show_text_edit_button")
        box.prop(self, "show_mode_overlay")
        box.prop(self, "hide_datablocks")

        col.separator()
        self._draw_segmentation(col)

    def _draw_controls(self, context, layout):
        col = layout.column()

        # Navigation & Mouse Gestures
        box = col.box()
        box.label(text="Navigation & Gestures", icon='MOUSE_MOVE')

        box.prop(self, "box_select_on_drag")
        box.prop(self, "box_select_alt_drag")
        box.prop(self, "key_shear_mod", text="Shear Modifier (Hold)")
        box.prop(self, "card_wheel_scroll")

        box.separator()
        box.label(text="Scroll Wheel Modifiers:")
        wheel = box.row(align=True)
        wheel.prop(self, "wheel_opacity_mod", text="Opacity")
        wheel.prop(self, "wheel_scale_mod", text="Scale")
        wheel.prop(self, "wheel_layer_mod", text="Layer")

        col.separator()

        # Keymap Shortcuts
        box = col.box()
        box.label(text="Keymap Shortcuts", icon='KEYINGSET')

        from . import keymap
        import rna_keymap_ui
        bindings = list(keymap.iter_ui_bindings(context.window_manager))
        if bindings:
            for label, keyconfig, km, item in bindings:
                item_box = box.box()
                item_box.label(text=label)
                item_box.context_pointer_set('keymap', km)
                rna_keymap_ui.draw_kmi([], keyconfig, km, item, item_box, 0)
        else:
            box.label(text="Shortcuts unavailable until the add-on keymap loads", icon='INFO')

        col.separator()

        # Controls Reference / Cheat Sheet
        box = col.box()
        box.label(text="Controls Reference", icon='INFO')

        ref_col = box.column(align=True)
        ref_col.label(text="• Transform: Move mouse; Left Click or Enter confirms; Esc cancels")
        ref_col.label(text="• Selection: Left Click selects; Shift + Left Click adds; Left Drag moves")
        ref_col.label(text="• Background: Left Drag box selects (Shift to add, Alt drag optional)")
        ref_col.label(text="• Gizmos: Ctrl = snap steps; Shift = fine; Ctrl + Shift = fine steps")
        ref_col.label(text="• Snapping: Align to image edges & grid; Ctrl inverts snap state")
        ref_col.label(text="• Actions: F2 renames; Right Click context menu; Delete / X removes")
        ref_col.separator()
        ref_col.label(text="* Shortcuts are active exclusively inside a Kanvas Tree", icon='DOT')

    def _draw_aesthetics(self, context, layout):
        col = layout.column()

        box = col.box()
        box.label(text="Canvas Style", icon='SHADING_RENDERED')
        box.prop(self, "visual_theme", text="")
        box.label(text="Applies to cards, frames, selection and canvas controls.")
        col.separator()

        box = col.box()
        box.label(text="Canvas Text", icon='FONT_DATA')
        box.prop(self, "text_shadow_enabled")
        if self.text_shadow_enabled:
            box.prop(self, "text_shadow_strength", slider=True)
            box.prop(self, "text_shadow_spread", text="Spread")
            if self.text_shadow_spread == 'DIFFUSE':
                box.prop(self, "text_shadow_diffuse_reach", slider=True)
        col.separator()

        box = col.box()
        box.label(text="Arrows", icon='TRIA_RIGHT')
        box.prop(self, "arrow_style", text="Style")
        col.separator()

        box = col.box()
        box.label(text="Canvas Background", icon='GRID')
        box.prop(self, "canvas_background_enabled")
        if self.canvas_background_enabled:
            box.prop(self, "canvas_background_color")
        box.prop(self, "canvas_grid_enabled")
        if self.canvas_grid_enabled:
            row = box.row(align=True)
            row.prop(self, "canvas_grid_color", text="Grid Color")
            row.prop(self, "canvas_grid_color", index=3, text="Opacity", slider=True)
        col.separator()

        # Canvas Axes Box
        box = col.box()
        box.label(text="Canvas Axes", icon='ORIENTATION_GLOBAL')

        style_col = box.column(align=True)
        row = style_col.row(align=True)
        row.prop(self, "color_x_axis", text="X Axis Color")
        row.prop(self, "color_x_axis", index=3, text="Opacity", slider=True)
        row = style_col.row(align=True)
        row.prop(self, "color_y_axis", text="Y Axis Color")
        row.prop(self, "color_y_axis", index=3, text="Opacity", slider=True)

        col.separator()

        # Selection Outlines Box
        box = col.box()
        box.label(text="Selection Outlines", icon='RESTRICT_SELECT_OFF')

        sel_col = box.column(align=True)
        sel_col.prop(self, "color_selection", text="Selection Color")
        sel_col.prop(self, "selection_thickness", text="Outline Thickness")
        sel_col.prop(self, "gizmo_background")

        col.separator()
        box = col.box()
        box.label(text="Arrow Handles", icon='TRIA_RIGHT')
        box.prop(self, "color_arrow_endpoint_handles", text="Endpoints")
        box.prop(self, "color_arrow_curve_handle", text="Curve Handle")

    def _draw_about(self, context, layout):
        col = layout.column()

        box = col.box()
        box.label(text="Kanvas Engine", icon='INFO')
        box.label(text="Engine Status: Active", icon='CHECKMARK')

        col.separator()

        box = col.box()
        box.label(text="About K-Tools: Kanvas", icon='QUESTION')
        info_col = box.column(align=True)
        info_col.label(text="High-performance infinite reference canvas for Blender's Node Editor.")
        info_col.label(text="Created by Robert Kezives")

        info_col.separator()
        info_col.label(text="Quick Start:")
        info_col.label(text="1. Switch editor to Node Editor and select Kanvas tree type.")
        info_col.label(text="2. Use the 'K-Tools' sidebar panel (N) or drag & drop images into the canvas.")
        info_col.label(text="3. Use Shift+F to create frames, Text Cards for notes, and G/S/R to transform.")
