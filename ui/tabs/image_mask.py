"""Mask tab: show only the painted parts of the image; tools and shortcuts."""

from .auto_select import draw_auto_select
from .common import gap


def draw(layout, context, settings, item):
    layout.prop(item, "mask_enabled", text="Use Mask", toggle=True, icon="MOD_MASK")
    draw_bounds(layout, item)
    gap(layout)
    draw_mask_properties(layout, item)


def draw_bounds(layout, item):
    """Fit Bounds to Mask: the item is only as big as what its mask shows."""
    column = layout.column(align=True)
    row = column.row(align=True)
    row.operator("kanvas.fit_bounds_to_mask", icon='SHADING_BBOX')
    sub = row.row(align=True)
    sub.enabled = item.crop_enabled and not item.mask_editing
    sub.operator("kanvas.reset_bounds", text="", icon='LOOP_BACK')
    column.prop(item, "crop_follow_mask", text="Auto-fit Bounds to Mask")
    if item.crop_enabled:
        column.label(text="Bounds fitted to the mask", icon='CHECKMARK')


def draw_mask_properties(layout, img):
    mask = layout.column(align=True)
    mask.label(text="Mask Tool")
    tools = mask.row(align=True)
    tools.prop_enum(img, "mask_tool", 'BRUSH', text="Brush")
    tools.prop_enum(img, "mask_tool", 'POLYGON', text="Polygon")
    mask.prop_enum(img, "mask_tool", 'RECTANGLE', text="Rectangle / Square")
    gap(mask)
    draw_auto_select(mask, img, "mask_tool")
    gap(mask)
    row = mask.row(align=True)
    row.prop(img, "mask_brush_size", text="Brush")
    row.prop(img, "mask_erase", text="Erase", toggle=True)
    row = mask.row(align=True)
    row.operator_context = 'INVOKE_REGION_WIN'
    row.operator("kanvas.paint_image_mask", text="Edit Mask (M)", icon='BRUSH_DATA')
    row.operator("kanvas.clear_image_mask", text="", icon='TRASH')
    if img.mask_editing:
        mask.label(text="MASK MODE · Tab: switch tools")
        mask.label(text="M: finish · MMB: pan")
        mask.label(text="Wheel: zoom · E: toggle erase")
        mask.label(text="Hold Alt: temporary invert")
        mask.label(text="Ctrl+Z / Ctrl+Shift+Z: stroke undo/redo")
        if img.mask_tool == 'POLYGON':
            mask.label(text="Click: vertex · Double-click: close")
            mask.label(text="Shift: 45° · Enter: close")
            mask.label(text="Esc: cancel/finish")
        elif img.mask_tool == 'RECTANGLE':
            mask.label(text="Drag: rectangle · Shift: square")
            mask.label(text="Ctrl: from center · Shift+Ctrl: square")
            mask.label(text="Esc: cancel/finish")
        elif img.mask_tool == 'AUTO':
            mask.label(text="Click: include · Ctrl+Click: exclude")
            mask.label(text="Enter: apply · Backspace: undo point")
            mask.label(text="Esc: clear points/finish")
        else:
            mask.label(text="Shift+Click: line · Shift+Drag: 45°")
            mask.label(text="Ctrl+Wheel: brush size")
            mask.label(text="Enter: finish · Esc: cancel line/finish")
