def draw_shape_properties(layout, settings, item):
    layout.use_property_split = False
    box = layout.box()
    box.label(text=f"Shape: {item.name}", icon='MESH_PLANE')
    box.prop(item, "name", text="Name")
    box.prop(item, "shape_kind", text="Kind")

    editing = box.row(align=True)
    editing.prop(item, "shape_edit_vertices", text="Edit Vertices", toggle=True,
                 icon='EDITMODE_HLT')
    if item.shape_edit_vertices:
        box.label(text="Click / box: select  |  drag: move  |  click edge: add")
        selected = sum(1 for vertex in item.shape_vertices if vertex.select)
        row = box.row(align=True)
        row.label(text=f"{len(item.shape_vertices)} vertices, {selected} selected")
        delete = row.row(align=True)
        delete.enabled = selected > 0
        delete.operator("kanvas.delete_shape_vertices", text="Delete", icon='X')
        tools = box.column(align=True)
        tools.enabled = selected > 0
        tools.prop(item, "shape_vertex_location", text="Position")
        row = tools.row(align=True)
        row.operator("kanvas.select_contour", text="Contour (L)", icon='SELECT_EXTEND')
        row.operator("kanvas.reverse_contour", text="Reverse", icon='ARROW_LEFTRIGHT')
        row = tools.row(align=True)
        row.operator("kanvas.flip_shape", text="Flip H", icon='MOD_MIRROR').axis = 'X'
        row.operator("kanvas.flip_shape", text="Flip V", icon='MOD_MIRROR').axis = 'Y'
        from ...utils.shape_geometry import HANDLE_TYPES
        types = {item.shape_vertices[i].handle_type
                 for i in range(len(item.shape_vertices)) if item.shape_vertices[i].select}
        column = box.column(align=True)
        column.enabled = selected > 0
        column.label(text="Vertex Type (V)")
        row = column.grid_flow(row_major=True, columns=3, even_columns=True, align=True)
        for identifier, label, _, icon in HANDLE_TYPES:
            row.operator("kanvas.set_vertex_type", text=label, icon=icon,
                         depress=types == {identifier}).kind = identifier
    else:
        box.label(text=f"{len(item.shape_vertices)} vertices")
        row = box.row(align=True)
        row.operator("kanvas.flip_shape", text="Flip H", icon='MOD_MIRROR').axis = 'X'
        row.operator("kanvas.flip_shape", text="Flip V", icon='MOD_MIRROR').axis = 'Y'
    row = box.row(align=True)
    row.prop(item, "shape_closed", text="Closed", toggle=True,
             icon='MESH_CIRCLE' if item.shape_closed else 'IPO_LINEAR')
    from ...utils.shape_geometry import item_contour_ranges
    contours = len(item_contour_ranges(item))
    if contours > 1:
        row = box.row(align=True)
        row.label(text=f"{contours} contours (inner ones are holes)", icon='SELECT_DIFFERENCE')
        row.operator("kanvas.separate_contours", text="Separate", icon='MOD_EXPLODE')
    box.prop(item, "shape_corner_radius", text="Corner Radius")
    from ...utils.shape_geometry import uses_curve_resolution
    row = box.row()
    # Curved edges and rounded corners use it; a shape with neither has nothing to smooth.
    row.enabled = uses_curve_resolution(item)
    row.prop(item, "shape_curve_resolution", text="Curve Resolution")
    box.operator("kanvas.export_shapes_svg", text="Export SVG...", icon='EXPORT')

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
    sub = outline.row(align=True)
    sub.enabled = item.shape_show_outline
    sub.prop(item, "shape_line_join", text="")
    ends = sub.row(align=True)
    ends.enabled = not item.shape_closed or item.shape_line_style == 'DASHED'
    ends.prop(item, "shape_line_cap", text="")
    align = sub.row(align=True)
    align.enabled = item.shape_closed
    align.prop(item, "shape_line_align", text="")

    box.prop(item, "opacity", text="Opacity", slider=True)

    text = box.column(align=True)
    text.prop(item, "shape_show_text", text="Text")
    content = text.column(align=True)
    content.enabled = item.shape_show_text
    content.prop(item, "text_body", text="")  # one line: the text shrinks to fit the shape
    row = content.row(align=True)
    row.prop(item, "text_font_size", text="Font")
    row.prop(item, "text_color", text="")
