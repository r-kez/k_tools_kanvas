def draw_selection_actions(layout, settings):
    selected_count = sum(1 for i in settings.images if getattr(i, "item_type", 'IMAGE') == 'IMAGE' and i.is_selected)
    if selected_count > 1:
        row = layout.row(align=True)
        row.operator("kanvas.average_image_size", icon='FULLSCREEN_ENTER', text="Average Size")
        row.operator("kanvas.pack_images", icon='GRID', text=f"Pack ({selected_count})")
        layout.operator("kanvas.pack_images", icon='GRID', text="Average + Pack").average_size = True

