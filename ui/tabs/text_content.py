"""Content tab: the title and what the card holds (text, Markdown or a checklist)."""

from .common import gap


def draw(layout, context, settings, item):
    content = layout.column(align=True)
    content.prop(item, "text_show_header", text="Show Title")
    modes = content.row(align=True)
    modes.prop(item, "text_checklist")

    if not item.text_checklist:
        modes = content.row(align=True)
        modes.prop(item, "text_markdown", text="Markdown")

    gap(layout)
    content = layout.column(align=True)

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
            content.label(text='Select images too, to link them')
        gap(content)
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
