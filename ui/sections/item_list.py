def draw_item_list(layout, settings):
    list_column = layout.column(align=True)
    search = list_column.row(align=True)
    search.prop(settings, 'list_search', text='Search')
    clear = search.row(align=True)
    clear.enabled = bool(settings.list_search)
    clear.operator('kanvas.clear_list_search', text='', icon='X')

    row = list_column.row(align=True)
    row.template_list("KANVAS_UL_image_list", "", settings, "images", settings, "active_image_index")
    if 0 <= settings.active_image_index < len(settings.images):
        active = settings.images[settings.active_image_index]
        if active.parent_frame:
            from ...utils.gpu import get_frame, frame_ancestors
            parent = get_frame(settings, active.parent_frame)
            chain = ([parent] + frame_ancestors(settings, parent)) if parent else []
            collapsed_parent = next((frame for frame in chain if frame.list_collapsed), None)
            if collapsed_parent:
                layout.label(text=f"Active in {collapsed_parent.name}: {active.name}",
                             icon='RADIOBUT_ON')

    col = row.column(align=True)
    col.operator_context = 'INVOKE_DEFAULT'
    col.operator("kanvas.remove_image", icon='REMOVE', text="").index = settings.active_image_index
    col.operator("kanvas.check_board", icon='CHECKMARK', text="")

    from ...operators.ops_image import missing_external_items
    missing_count = len(missing_external_items(settings))
    if missing_count:
        notice = layout.row(align=True)
        notice.label(text=f"{missing_count} missing image(s)", icon='ERROR')
        notice.operator('kanvas.relink_missing_images', text='Relink', icon='FILEBROWSER')
