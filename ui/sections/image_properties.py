import os


def draw_image_properties(layout, settings, item):
    img = item
    box = layout.box()
    box.label(text=f"Properties: {img.name}", icon='IMAGE_DATA')

    col = box.column(align=True)
    row = col.row(align=True)
    row.prop(img, "image_data", text="")
    row.operator("kanvas.refresh_image", icon='FILE_REFRESH', text="")
    row.operator("kanvas.replace_image", icon='FILEBROWSER', text="")
    row.operator("kanvas.clear_image_gpu_cache", icon='TRASH', text="")
    from ...operators.ops_image import image_origin
    source_kind, source = image_origin(img.image_data)
    if source:
        row = col.row(align=True)
        source_name = (source if source_kind == 'URL'
                       else os.path.basename(source))
        row.label(text=f"Source: {source_name}")
        if source_kind != 'PUR':
            row.operator('kanvas.open_image_source', text='Open')

    selected_count = sum(1 for i in settings.images if getattr(i, "item_type", 'IMAGE') == 'IMAGE' and i.is_selected)

    if img.image_data:

        row = col.row(align=True)
        row.label(text="Position")
        row.prop(img, "location", index=0, text="X")
        row.prop(img, "location", index=1, text="Y")

        row = col.row(align=True)
        row.label(text="Rotation")
        row.scale_x = 2
        row.prop(img, "rotation_ui", text="")

        row = col.row(align=True)
        row.label(text="Scale")
        row.scale_x = 2
        row.prop(img, "scale_master", text="")

        row = col.row(align=True)
        row.label(text="Stretch")
        row.prop(img, "scale_xy", index=0, text="X")
        row.prop(img, "scale_xy", index=1, text="Y")

        row = col.row(align=True)
        row.label(text="Shear")
        row.prop(img, "shear_xy", index=0, text="X")
        row.prop(img, "shear_xy", index=1, text="Y")

        col.separator()
        col.separator()

        # Image Adjustments
        multi_adjust = selected_count > 1 and img.is_selected
        adjustment_owner = settings if multi_adjust else img
        adjustment_prefix = "batch_" if multi_adjust else ""
        if multi_adjust:
            col.label(text=f"Adjust {selected_count} selected images",
                      icon='IMAGE_DATA')
        from ...utils.icons import get_icon
        row = col.row(align=True)
        row.prop(adjustment_owner, adjustment_prefix + "flip_h", text="Flip H", toggle=True, icon_value=get_icon("icon-flip-horizontal"))
        row.prop(adjustment_owner, adjustment_prefix + "flip_v", text="Flip V", toggle=True, icon_value=get_icon("icon-flip-vertical"))

        col.separator()
        col.prop(adjustment_owner, adjustment_prefix + "brightness", text="Brightness", slider=True)
        col.prop(adjustment_owner, adjustment_prefix + "contrast", text="Contrast", slider=True)
        col.prop(adjustment_owner, adjustment_prefix + "saturation", text="Saturation", slider=True)

        col.separator()
        col.prop(adjustment_owner, adjustment_prefix + "opacity", text="Opacity", slider=True)

        row = col.row(align=True)
        row.prop(adjustment_owner, adjustment_prefix + "color_tint", text="")
        row.prop(adjustment_owner, adjustment_prefix + "use_color_correction", text="", icon='IMAGE')

        row = col.row(align=True)
        row.prop(adjustment_owner, adjustment_prefix + "value_gray", text="Grayscale", toggle=True)
        row.prop(adjustment_owner, adjustment_prefix + "value_levels", text="Posterize")

def _draw_auto_select(layout, img, tool_property):
    """Analyze button and tool toggle for Auto Select (explicit, opt-in)."""
    from ...utils import sam_engine
    column = layout.box().column(align=True)
    column.label(text="Auto Select", icon='VIEWZOOM')
    if not sam_engine.ready():
        column.label(text="Install it in Preferences > General", icon='INFO')
        return
    analysis = sam_engine.snapshot('analyze')
    working = analysis['state'] == 'working'
    analyzed = sam_engine.is_analyzed(img.image_data)
    row = column.row(align=True)
    row.enabled = not working
    row.operator("kanvas.sam_analyze_image",
                 text=("Analyzing..." if working
                       else "Analyze Again" if analyzed else "Analyze Image"),
                 icon='VIEWZOOM')
    tool = column.row(align=True)
    tool.enabled = analyzed
    tool.prop_enum(img, tool_property, 'AUTO', text="Auto Select Tool (A)")
    if analysis['state'] == 'error':
        column.label(text=analysis['message'][:60], icon='ERROR')


def draw_mask_properties(layout, img):
    mask = layout.column(align=True)
    mask.label(text="Mask Tool")
    tools = mask.row(align=True)
    tools.prop_enum(img, "mask_tool", 'BRUSH', text="Brush")
    tools.prop_enum(img, "mask_tool", 'POLYGON', text="Polygon")
    mask.prop_enum(img, "mask_tool", 'RECTANGLE', text="Rectangle / Square")
    _draw_auto_select(mask, img, "mask_tool")
    row = mask.row(align=True)
    row.prop(img, "mask_brush_size", text="Brush")
    row.prop(img, "mask_erase", text="Erase", toggle=True)
    row = mask.row(align=True)
    row.operator_context = 'INVOKE_REGION_WIN'
    row.operator("kanvas.paint_image_mask", text="Edit Mask (M)", icon='BRUSH_DATA')
    row.operator("kanvas.clear_image_mask", text="", icon='TRASH')
    if img.mask_editing:
        mask.label(text="MASK MODE · Tab: switch tools")
        mask.label(text="M: finish · MMB: pan")
        mask.label(text="Wheel: zoom · E: toggle erase")
        mask.label(text="Hold Alt: temporary invert")
        mask.label(text="Ctrl+Z / Ctrl+Shift+Z: stroke undo/redo")
        if img.mask_tool == 'POLYGON':
            mask.label(text="Click: vertex · Double-click: close")
            mask.label(text="Shift: 45° · Enter: close")
            mask.label(text="Esc: cancel/finish")
        elif img.mask_tool == 'RECTANGLE':
            mask.label(text="Drag: rectangle · Shift: square")
            mask.label(text="Ctrl: from center · Shift+Ctrl: square")
            mask.label(text="Esc: cancel/finish")
        elif img.mask_tool == 'AUTO':
            mask.label(text="Click: include · Ctrl+Click: exclude")
            mask.label(text="Enter: apply · Backspace: undo point")
            mask.label(text="Esc: clear points/finish")
        else:
            mask.label(text="Shift+Click: line · Shift+Drag: 45°")
            mask.label(text="Ctrl+Wheel: brush size")
            mask.label(text="Enter: finish · Esc: cancel line/finish")


def draw_color_properties(layout, img):
    from ...utils.icons import get_icon
    markup = layout.column(align=True)
    if img.checklist_associations:
        settings = getattr(img.id_data, 'kanvas_settings', None)
        cards = ({item.item_id: item.name for item in settings.images
                  if item.item_type == 'TEXT'} if settings else {})
        for link in img.checklist_associations:
            markup.label(text=f'Checklist: {cards.get(link.card_id, "Missing card")}',
                         icon='LINKED')
    row = markup.row()
    row.template_list("KANVAS_UL_markup_regions", "", img, "markup_regions",
                      img, "markup_active_index", rows=4)
    buttons = row.column(align=True)
    buttons.operator("kanvas.add_markup_region_in_edit" if img.markup_editing
                     else "kanvas.add_markup_region", text="", icon='ADD')
    buttons.operator("kanvas.remove_markup_region", text="", icon='REMOVE')
    buttons.operator("kanvas.randomize_markup_colors", text="",
                     icon_value=get_icon("arrows-shuffle"))
    move_up = buttons.row(align=True)
    move_up.enabled = not img.markup_editing and len(img.markup_regions) > 1
    move_up.operator('kanvas.move_markup_region', text='', icon='TRIA_UP').direction = -1
    move_down = buttons.row(align=True)
    move_down.enabled = not img.markup_editing and len(img.markup_regions) > 1
    move_down.operator('kanvas.move_markup_region', text='', icon='TRIA_DOWN').direction = 1
    if img.markup_regions:
        active = img.markup_regions[min(img.markup_active_index,
                                        len(img.markup_regions) - 1)]
        row = markup.row(align=True)
        color = row.row(align=True)
        color.enabled = not bool(active.checklist_card_id)
        color.prop(active, "color", text="")
        row.prop(active, "opacity", text="Opacity", slider=True)
        markup.prop(active, "inverse", text="Inverse (color everything else)",
                    toggle=True, icon='SELECT_SUBTRACT')
        markup.label(text="Color Tool")
        tools = markup.row(align=True)
        tools.prop_enum(img, "markup_tool", 'BRUSH', text="Brush")
        tools.prop_enum(img, "markup_tool", 'POLYGON', text="Polygon")
        markup.prop_enum(img, "markup_tool", 'RECTANGLE', text="Rectangle / Square")
        _draw_auto_select(markup, img, "markup_tool")
        row = markup.row(align=True)
        row.prop(img, "markup_brush_size", text="Brush")
        row.prop(img, "markup_erase", text="Erase", toggle=True)
    isolate = markup.row(align=True)
    isolate.operator("kanvas.isolate_markup_region", text="",
                     icon='TRIA_LEFT').direction = -1
    from ...utils.gpu.gpu_markup import isolated_index
    shown = isolated_index(img)
    isolate.operator(
        "kanvas.isolate_markup_region",
        text=(f"Isolating {shown + 1}/{len(img.markup_regions)}: "
              f"{img.markup_regions[shown].name}" if shown >= 0 else "Isolate Color"),
        icon='RESTRICT_VIEW_ON' if shown >= 0 else 'RESTRICT_VIEW_OFF',
        depress=shown >= 0,
    ).direction = 2
    isolate.operator("kanvas.isolate_markup_region", text="",
                     icon='TRIA_RIGHT').direction = 1
    display = markup.row(align=True)
    display.prop(img, "markup_show_names", text="Names", toggle=True, icon='FONT_DATA')
    if img.checklist_associations:
        lines = markup.row(align=True)
        lines.prop(img, "markup_show_done_lines", text="Done Lines", toggle=True,
                   icon='MOD_LINEART')
        opacity = lines.row(align=True)
        opacity.enabled = img.markup_show_done_lines
        opacity.prop(img, "markup_done_line_opacity", text="Opacity", slider=True)
        markup.prop(img, "markup_arrows_all_islands", text="Point All Islands",
                    toggle=True, icon='ORIENTATION_CURSOR')
    row = markup.row(align=True)
    row.operator_context = 'INVOKE_REGION_WIN'
    row.operator("kanvas.edit_color_markup", text="Edit Colors", icon='BRUSH_DATA')
    row.operator("kanvas.pick_pixel_color", text="", icon='EYEDROPPER')
    row.operator("kanvas.extract_palette", text="", icon='COLOR')
    row.operator("kanvas.export_markup_masks", text="", icon='EXPORT')
    if img.markup_editing:
        markup.label(text="COLOR MODE · Tab: switch tools")
        markup.label(text="< / >: change · Shift+C: add · Shift+E: edit")
        markup.label(text="E: erase · Hold Alt: invert · C: finish")
        if img.markup_tool == 'RECTANGLE':
            markup.label(text="Drag: rectangle · Shift: square")
            markup.label(text="Ctrl: from center · Shift+Ctrl: square")
        markup.label(text="Ctrl+Z / Ctrl+Shift+Z: stroke undo/redo")

