def draw_gizmo_settings(layout, settings):
    row = layout.row(align=True)
    row.enabled = settings.show_gizmos
    row.prop(settings, "gizmo_size", text="Size")
    row.prop(settings, "show_scale_handles", text="Scale", toggle=True)
    row.prop(settings, "show_rotate_handles", text="Rotate", toggle=True)
