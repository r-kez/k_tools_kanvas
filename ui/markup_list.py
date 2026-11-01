import bpy


def checklist_task_done(image, region):
    """Read the current task state by ID, independent of name or list order."""
    if not region.checklist_card_id or not region.checklist_line_id:
        return False
    settings = getattr(image.id_data, 'kanvas_settings', None)
    if settings is None:
        return False
    card = next((item for item in settings.images
                 if item.item_id == region.checklist_card_id
                 and item.item_type == 'TEXT' and item.text_checklist), None)
    if card is None:
        return False
    line = next((line for line in card.text_lines
                 if line.line_id == region.checklist_line_id), None)
    return bool(line.done) if line is not None else False


class KANVAS_UL_markup_regions(bpy.types.UIList):
    """Compact list of paint colors for the selected image."""

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type == 'GRID':
            layout.label(text="", icon='COLOR')
            return
        row = layout.row(align=True)
        row.prop(item, "color", text="")
        if item.checklist_card_id:
            icon = 'CHECKBOX_HLT' if checklist_task_done(data, item) else 'CHECKBOX_DEHLT'
            row.label(text=item.name or 'Checklist task', icon=icon)
        else:
            row.prop(item, "name", text="", emboss=False)
        row.prop(item, "visible", text="",
                 icon='HIDE_OFF' if item.visible else 'HIDE_ON', emboss=False)
