"""Markup tab: named color regions painted on the image, linked checklists."""

from .auto_select import draw_auto_select
from .common import gap


def draw(layout, context, settings, item):
    layout.prop(item, "markup_visible", text="Show Markup", toggle=True, icon="BRUSH_DATA")
    gap(layout)
    draw_color_properties(layout, item)


def draw_color_properties(layout, img):
    from ...utils.icons import get_icon
    markup = layout.column(align=True)
    if img.checklist_associations:
        settings = getattr(img.id_data, 'kanvas_settings', None)
        cards = ({item.item_id: item.name for item in settings.images
                  if item.item_type == 'TEXT'} if settings else {})
        for link in img.checklist_associations:
            markup.label(text=f'Checklist: {cards.get(link.card_id, "Missing card")}',
                         icon='LINKED')
    row = markup.row()
    row.template_list("KANVAS_UL_markup_regions", "", img, "markup_regions",
                      img, "markup_active_index", rows=4)
    buttons = row.column(align=True)
    buttons.operator("kanvas.add_markup_region_in_edit" if img.markup_editing
                     else "kanvas.add_markup_region", text="", icon='ADD')
    buttons.operator("kanvas.remove_markup_region", text="", icon='REMOVE')
    buttons.operator("kanvas.randomize_markup_colors", text="",
                     icon_value=get_icon("arrows-shuffle"))
    move_up = buttons.row(align=True)
    move_up.enabled = not img.markup_editing and len(img.markup_regions) > 1
    move_up.operator('kanvas.move_markup_region', text='', icon='TRIA_UP').direction = -1
    move_down = buttons.row(align=True)
    move_down.enabled = not img.markup_editing and len(img.markup_regions) > 1
    move_down.operator('kanvas.move_markup_region', text='', icon='TRIA_DOWN').direction = 1
    if img.markup_regions:
        active = img.markup_regions[min(img.markup_active_index,
                                        len(img.markup_regions) - 1)]
        row = markup.row(align=True)
        color = row.row(align=True)
        color.enabled = not bool(active.checklist_card_id)
        color.prop(active, "color", text="")
        row.prop(active, "opacity", text="Opacity", slider=True)
        markup.prop(active, "inverse", text="Inverse (color everything else)",
                    toggle=True, icon='SELECT_SUBTRACT')
        gap(markup)
        markup.label(text="Color Tool")
        tools = markup.row(align=True)
        tools.prop_enum(img, "markup_tool", 'BRUSH', text="Brush")
        tools.prop_enum(img, "markup_tool", 'POLYGON', text="Polygon")
        markup.prop_enum(img, "markup_tool", 'RECTANGLE', text="Rectangle / Square")
        gap(markup)
        draw_auto_select(markup, img, "markup_tool")
        gap(markup)
        row = markup.row(align=True)
        row.prop(img, "markup_brush_size", text="Brush")
        row.prop(img, "markup_erase", text="Erase", toggle=True)
    gap(markup)
    isolate = markup.row(align=True)
    isolate.operator("kanvas.isolate_markup_region", text="",
                     icon='TRIA_LEFT').direction = -1
    from ...utils.gpu.gpu_markup import isolated_index
    shown = isolated_index(img)
    isolate.operator(
        "kanvas.isolate_markup_region",
        text=(f"Isolating {shown + 1}/{len(img.markup_regions)}: "
              f"{img.markup_regions[shown].name}" if shown >= 0 else "Isolate Color"),
        icon='RESTRICT_VIEW_ON' if shown >= 0 else 'RESTRICT_VIEW_OFF',
        depress=shown >= 0,
    ).direction = 2
    isolate.operator("kanvas.isolate_markup_region", text="",
                     icon='TRIA_RIGHT').direction = 1
    display = markup.row(align=True)
    display.prop(img, "markup_show_names", text="Names", toggle=True, icon='FONT_DATA')
    if img.checklist_associations:
        lines = markup.row(align=True)
        lines.prop(img, "markup_show_done_lines", text="Done Lines", toggle=True,
                   icon='MOD_LINEART')
        opacity = lines.row(align=True)
        opacity.enabled = img.markup_show_done_lines
        opacity.prop(img, "markup_done_line_opacity", text="Opacity", slider=True)
        markup.prop(img, "markup_arrows_all_islands", text="Point All Islands",
                    toggle=True, icon='ORIENTATION_CURSOR')
    gap(markup)
    row = markup.row(align=True)
    row.operator_context = 'INVOKE_REGION_WIN'
    row.operator("kanvas.edit_color_markup", text="Edit Colors", icon='BRUSH_DATA')
    row.operator("kanvas.pick_pixel_color", text="", icon='EYEDROPPER')
    row.operator("kanvas.extract_palette", text="", icon='COLOR')
    row.operator("kanvas.export_markup_masks", text="", icon='EXPORT')
    if img.markup_editing:
        markup.label(text="COLOR MODE · Tab: switch tools")
        markup.label(text="< / >: change · Shift+C: add · Shift+E: edit")
        markup.label(text="E: erase · Hold Alt: invert · C: finish")
        if img.markup_tool == 'RECTANGLE':
            markup.label(text="Drag: rectangle · Shift: square")
            markup.label(text="Ctrl: from center · Shift+Ctrl: square")
        markup.label(text="Ctrl+Z / Ctrl+Shift+Z: stroke undo/redo")
