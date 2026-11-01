"""Quick renaming for the selected Kanvas item."""

import bpy
from ..utils.kanvas_data import get_settings

from .kanvas_context import KanvasTreeOnly


def _rename_target_index(settings):
    index = settings.active_image_index
    if 0 <= index < len(settings.images) and settings.images[index].is_selected:
        return index
    selected = [i for i, item in enumerate(settings.images) if item.is_selected]
    return selected[0] if len(selected) == 1 else -1


class KANVAS_OT_RenameItem(KanvasTreeOnly, bpy.types.Operator):
    """Rename the active Frame or image without changing its datablock name."""

    bl_idname = "kanvas.rename_item"
    bl_label = "Rename Kanvas Item"
    bl_description = 'Rename the active item (F2)'
    bl_options = {'REGISTER', 'UNDO'}

    new_name: bpy.props.StringProperty(name="Name")  # type: ignore
    item_index: bpy.props.IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        return settings is not None and _rename_target_index(settings) >= 0

    def invoke(self, context, event):
        settings = get_settings(context)
        self.item_index = _rename_target_index(settings)
        if self.item_index < 0:
            return {'CANCELLED'}
        self.new_name = settings.images[self.item_index].name
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        self.layout.prop(self, "new_name", text="Name")

    def execute(self, context):
        settings = get_settings(context)
        index = self.item_index if self.item_index >= 0 else _rename_target_index(settings)
        if not (0 <= index < len(settings.images)) or not settings.images[index].is_selected:
            return {'CANCELLED'}
        name = self.new_name.strip()
        if not name:
            self.report({'WARNING'}, "Name cannot be empty")
            return {'CANCELLED'}
        if settings.images[index].name == name:
            return {'CANCELLED'}
        settings.images[index].name = name
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}
