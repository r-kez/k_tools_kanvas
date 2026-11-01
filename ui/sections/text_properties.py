def _draw_compare_properties(layout, settings, item):
    layout.use_property_split = False
    box = layout.box()
    box.label(text=f"Comparison: {item.name}", icon='UV_SYNC_SELECT')
    box.prop(item, "name", text="Title")
    box.prop(item, "text_show_header", text="Show Title")
    from ...utils.gpu.gpu_compare import side_item
    for side in ('A', 'B'):
        source = side_item(settings, item, side)
        row = box.row(align=True)
        row.label(text=f"{side}: {source.name if source else 'none'}")
        pick = row.operator("kanvas.pick_compare_side", text="", icon='EYEDROPPER')
        pick.item_id, pick.side = item.item_id, side
    box.prop(item, "compare_split", text="Divider", slider=True)
    size = box.row(align=True)
    size.prop(item, "text_width", text="Width")
    size.prop(item, "text_height", text="Height")


def draw_text_properties(layout, settings, item):
    if item.text_compare:
        _draw_compare_properties(layout, settings, item)
        return
    layout.use_property_split = False
    box = layout.box()
    box.label(text=f"Text Card: {item.name}", icon='TEXT')
    foldout = box.row(align=True)
    foldout.prop(item, "text_layout_expanded", text="Layout",
                 icon='TRIA_DOWN' if item.text_layout_expanded else 'TRIA_RIGHT',
                 emboss=False)
    
    if item.text_layout_expanded:
        geometry = box.column(align=True)
        row = geometry.row(align=True)
        row.label(text="Position")
        row.prop(item, "location", index=0, text="X")
        row.prop(item, "location", index=1, text="Y")
        row = geometry.row(align=True)
        row.label(text="Size")
        row.prop(item, "text_width", text="X")
        row.prop(item, "text_height", text="Y")
        row = geometry.row(align=True)
        row.prop(item, "text_scale", text="Scale")
        row.prop(item, "text_font_size", text="Font")

    foldout = box.row(align=True)
    foldout.prop(item, "text_appearance_expanded", text="Appearance",
                 icon='TRIA_DOWN' if item.text_appearance_expanded else 'TRIA_RIGHT',
                 emboss=False)
    
    if item.text_appearance_expanded:
        appearance = box.column(align=True)
        row = appearance.row(align=True)
        row.label(text="Text")
        row.prop(item, "text_color", text="")
        row = appearance.row(align=True)
        row.label(text="Background")
        row.prop(item, "text_background", text="")
        row = appearance.row(align=True)
        row.label(text="Opacity")
        row.prop(item, "text_opacity", text="", slider=True)

    content = box.column(align=True)
    content.label(text="Content", icon='TEXT')
    content.prop(item, "name", text="Title")
    content.prop(item, "text_show_header", text="Show Title")
    modes = content.row(align=True)
    modes.prop(item, "text_checklist")

    
    if not item.text_checklist:
        modes = content.row(align=True)
        modes.prop(item, "text_markdown", text="Markdown")

    if item.text_checklist:
        from ...operators.ops_checklist import is_associated, selected_images
        targets = selected_images(settings)
        if targets:
            linked = sum(is_associated(image, item.item_id) for image in targets)
            relation = content.box()
            relation.label(text=f'Images: {linked}/{len(targets)} linked', icon='LINKED')
            row = relation.row(align=True)
            row.operator('kanvas.associate_checklist', text='Link Selected', icon='LINKED')
            if linked:
                row.operator('kanvas.dissociate_checklist', text='', icon='UNLINKED')
        else:
            content.label(text='Select this checklist with images to link them')
        progress = content.row(align=True)
        
        progress.label(text="Tasks:")
        progress = content.row(align=True)
        progress.prop(item, "text_show_progress", toggle=False)
        
        actions = content.row(align=True)
        actions.operator("kanvas.add_text_line", icon='ADD', text="Add Task")
        actions.operator_menu_enum("kanvas.sort_checklist", "mode", text="Sort", icon='SORTALPHA')
        
        for index, line in enumerate(item.text_lines):
            row = content.row(align=True)
            row.prop(line, "done", text="")
            row.prop(line, "show_color_links", text="",
                     icon='HIDE_OFF' if line.show_color_links else 'HIDE_ON',
                     emboss=False)
            row.prop(line, "color", text="")
            row.prop(line, "value", text="")
            up = row.row(align=True)
            up.enabled = index > 0
            move = up.operator("kanvas.move_checklist_task", icon='TRIA_UP', text="")
            move.index, move.direction = index, -1
            down = row.row(align=True)
            down.enabled = index < len(item.text_lines) - 1
            move = down.operator("kanvas.move_checklist_task", icon='TRIA_DOWN', text="")
            move.index, move.direction = index, 1
            row.operator("kanvas.remove_text_line", icon='X', text="").index = index
    
    elif hasattr(content, 'textbox'):
        content.textbox(item, "text_body", initial_visible_lines=4,
                    placeholder="Write here...")
    
    else:
        content.label(text="Lines")
        
        for index, line in enumerate(item.text_lines):
            row = content.row(align=True)
            row.prop(line, "value", text=str(index + 1))
            row.operator("kanvas.remove_text_line", icon='X', text="").index = index
        content.operator("kanvas.add_text_line", icon='ADD', text="Add Line")
