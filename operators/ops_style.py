"""Copy the look of one item and paste it onto others of the same kind."""

import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils.kanvas_data import get_settings

# Appearance only: never position, size, content, or links.
STYLE_PROPERTIES = {
    'IMAGE': ('opacity', 'color_tint', 'brightness', 'contrast', 'saturation',
              'use_color_correction', 'value_gray', 'value_levels', 'sampling'),
    'TEXT': ('text_color', 'text_background', 'text_opacity', 'text_font_size'),
    'SHAPE': ('shape_show_fill', 'shape_fill_color', 'shape_fill_opacity', 'shape_show_outline',
              'shape_line_color', 'shape_line_width', 'shape_line_style', 'shape_line_join',
              'shape_line_cap', 'shape_line_align', 'shape_corner_radius', 'text_color',
              'text_font_size'),
    'FRAME': ('frame_color', 'frame_opacity', 'frame_font_size'),
}

_clipboard = {'kind': None, 'values': {}}


def copy_style(item):
    """Remember the appearance of `item`; returns False for an unsupported item."""
    names = STYLE_PROPERTIES.get(item.item_type)
    if not names:
        return False
    values = {}
    for name in names:
        value = getattr(item, name)
        values[name] = tuple(value) if hasattr(value, '__len__') and not isinstance(value, str) else value
    if item.item_type == 'SHAPE':
        from ..utils.shape_gradient import gradient_record
        values['gradient'] = gradient_record(item)
    _clipboard['kind'] = item.item_type
    _clipboard['values'] = values
    return True


def style_kind():
    return _clipboard['kind']


def apply_style(item):
    """Paste the remembered appearance onto `item`; returns whether it changed."""
    if item.item_type != _clipboard['kind']:
        return False
    for name, value in _clipboard['values'].items():
        if name == 'gradient':
            from ..utils.shape_gradient import set_gradient_record
            set_gradient_record(item, value)
        else:
            setattr(item, name, value)
    return True


def clear_style():
    _clipboard['kind'] = None
    _clipboard['values'] = {}


def _active_item(context):
    settings = get_settings(context)
    index = settings.active_image_index if settings else -1
    if settings and 0 <= index < len(settings.images):
        return settings.images[index]
    return None


def _paste_targets(context):
    settings = get_settings(context)
    kind = style_kind()
    if kind is None or settings is None:
        return []
    return [item for item in settings.images
            if item.is_selected and not item.is_locked and item.item_type == kind]


class KANVAS_OT_CopyStyle(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.copy_style'
    bl_label = 'Copy Style'
    bl_description = ('Remember the appearance of the active item (colors, opacity, '
                      'font size, or image adjustments) to paste onto other items')
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        item = _active_item(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and item.item_type in STYLE_PROPERTIES

    def execute(self, context):
        item = _active_item(context)
        if not copy_style(item):
            return {'CANCELLED'}
        self.report({'INFO'}, f'Copied the style of {item.name}')
        return {'FINISHED'}


class KANVAS_OT_PasteStyle(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.paste_style'
    bl_label = 'Paste Style'
    bl_description = ('Apply the copied appearance to the selected items of the same kind. '
                      'Position, size, and content are not changed')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and bool(_paste_targets(context))

    def execute(self, context):
        changed = sum(apply_style(item) for item in _paste_targets(context))
        if not changed:
            return {'CANCELLED'}
        self.report({'INFO'}, f'Pasted the style onto {changed} item(s)')
        context.area.tag_redraw()
        return {'FINISHED'}
