def draw_shape_properties(layout, settings, item):
    layout.use_property_split = False
    box = layout.box()
    box.label(text=f"Shape: {item.name}", icon='MESH_PLANE')
    box.prop(item, "name", text="Name")
    box.prop(item, "shape_kind", text="Kind")

    editing = box.row(align=True)
    editing.enabled = item.shape_kind != 'ELLIPSE'
    editing.prop(item, "shape_edit_vertices", text="Edit Vertices", toggle=True,
                 icon='EDITMODE_HLT')
    if item.shape_edit_vertices:
        box.label(text="Drag a vertex or an edge  |  Ctrl+click a vertex: delete")
    box.label(text=f"{len(item.shape_vertices)} vertices")

    geometry = box.column(align=True)
    row = geometry.row(align=True)
    row.label(text="Position")
    row.prop(item, "location", index=0, text="X")
    row.prop(item, "location", index=1, text="Y")
    row = geometry.row(align=True)
    row.label(text="Size")
    row.prop(item, "shape_width", text="X")
    row.prop(item, "shape_height", text="Y")
    row = geometry.row(align=True)
    row.prop(item, "rotation_ui", text="Rotation")
    row.prop(item, "scale_master", text="Scale")

    fill = box.column(align=True)
    row = fill.row(align=True)
    check = row.row(align=True)
    check.enabled = item.shape_show_outline  # never leave a shape without fill and outline
    check.prop(item, "shape_show_fill", text="Fill")
    sub = row.row(align=True)
    sub.enabled = item.shape_show_fill
    sub.prop(item, "shape_fill_color", text="")
    sub.prop(item, "shape_fill_opacity", text="", slider=True)

    outline = box.column(align=True)
    row = outline.row(align=True)
    check = row.row(align=True)
    check.enabled = item.shape_show_fill
    check.prop(item, "shape_show_outline", text="Outline")
    sub = row.row(align=True)
    sub.enabled = item.shape_show_outline
    sub.prop(item, "shape_line_color", text="")
    sub.prop(item, "shape_line_width", text="")
    sub = outline.row(align=True)
    sub.enabled = item.shape_show_outline
    sub.prop(item, "shape_line_style", expand=True)

    box.prop(item, "opacity", text="Opacity", slider=True)

    text = box.column(align=True)
    text.prop(item, "shape_show_text", text="Text")
    content = text.column(align=True)
    content.enabled = item.shape_show_text
    content.prop(item, "text_body", text="")  # one line: the text shrinks to fit the shape
    row = content.row(align=True)
    row.prop(item, "text_font_size", text="Font")
    row.prop(item, "text_color", text="")
