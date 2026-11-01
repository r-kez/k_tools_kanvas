def draw_snap_settings(layout, context, settings):
    column = layout.column(align=True)
    column.enabled = context.tool_settings.use_snap_node
    row = column.row(align=True)
    row.prop(settings, "snap_grid", text="Grid", toggle=True)
    row.prop(settings, "snap_images", text="Edges", toggle=True)
    row = column.row(align=True)
    row.prop(settings, "grid_size", text="Step")
    row.prop(settings, "snap_threshold", text="Threshold")
