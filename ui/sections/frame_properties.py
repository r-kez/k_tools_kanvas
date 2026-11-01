def draw_frame_properties(layout, settings, item):
    box = layout.box()
    box.label(text=f"Frame Properties: {item.name}", icon='FULLSCREEN_ENTER')

    col = box.column(align=True)
    if item.parent_frame:
        from ...utils.gpu import get_frame
        parent = get_frame(settings, item.parent_frame)
        parent_row = col.row(align=True)
        parent_row.label(text=f"Parent: {parent.name if parent else item.parent_frame}")

    col.prop(item, "frame_color", text="Color")
    col.prop(item, "frame_opacity", text="Opacity")
    col.prop(item, "frame_font_size", text="Header Font Size")
    from ...utils.gpu import frame_has_content
    if not frame_has_content(settings, item.frame_node_name):
        row = col.row(align=True)
        row.prop(item, "frame_width", text="Width")
        row.prop(item, "frame_height", text="Height")

    col.separator()
    col.operator("kanvas.fit_frame", text="Fit Frame to Content", icon='FULLSCREEN_ENTER').frame_name = item.frame_node_name

    child_count = sum(1 for img in settings.images if img.parent_frame == item.frame_node_name)
    box.label(text=f"Contains {child_count} item(s)", icon='INFO')
