def draw_arrows(layout, settings):
    if settings.arrows:
        layout.label(text="Arrows", icon='TRIA_RIGHT')
        row = layout.row(align=True)
        row.template_list("UI_UL_list", "kanvas_arrows", settings, "arrows",
                          settings, "active_arrow_index", rows=2)
        controls = row.column(align=True)
        controls.operator_context = 'INVOKE_DEFAULT'
        controls.operator("kanvas.remove_arrow", icon='REMOVE', text="")
        if 0 <= settings.active_arrow_index < len(settings.arrows):
            arrow = settings.arrows[settings.active_arrow_index]
            col = layout.column(align=True)
            col.prop(arrow, 'is_locked', text='Lock Arrow', toggle=True,
                     icon='LOCKED' if arrow.is_locked else 'UNLOCKED')
            col.prop(arrow, "label", text="Label")
            col.prop(arrow, "color", text="Color")
            col.prop(arrow, "thickness", text="Thickness")
            col.operator("kanvas.reset_arrow_curvature", text="Reset Curvature",
                         icon='LOOP_BACK')
            from ...utils.gpu import get_item_by_id
            for side, label in (('start', 'Start'), ('end', 'End')):
                target = get_item_by_id(settings, getattr(arrow, side + '_item_id'))
                anchor = col.row(align=True)
                anchor.label(text=f"{label}: {target.name if target else 'Free'}")
                if target:
                    anchor.operator("kanvas.detach_arrow_end", text="",
                                    icon='UNLINKED').side = side
