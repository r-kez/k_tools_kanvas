"""Comparison card (an A/B text card): drawn without tabs."""


def draw_compare_properties(layout, settings, item):
    layout.use_property_split = False
    box = layout.box()
    box.label(text=f"Comparison: {item.name}", icon='UV_SYNC_SELECT')
    box.prop(item, "name", text="Title")
    box.prop(item, "text_show_header", text="Show Title")
    from ...utils.gpu.gpu_compare import side_item
    for side in ('A', 'B'):
        source = side_item(settings, item, side)
        row = box.row(align=True)
        row.label(text=f"{side}: {source.name if source else 'none'}")
        pick = row.operator("kanvas.pick_compare_side", text="", icon='EYEDROPPER')
        pick.item_id, pick.side = item.item_id, side
    flip = box.operator("kanvas.flip_compare", text="Flip A / B", icon='ARROW_LEFTRIGHT')
    flip.item_id = item.item_id
    box.prop(item, "compare_mode", text="Mode")
    if item.compare_mode == 'SPLIT':
        box.prop(item, "compare_split", text="Divider", slider=True)
    elif item.compare_mode == 'FADE':
        box.prop(item, "compare_blend", text="B Opacity", slider=True)
    else:
        box.prop(item, "compare_gain", text="Amplify")
    size = box.row(align=True)
    size.prop(item, "text_width", text="Width")
    size.prop(item, "text_height", text="Height")
