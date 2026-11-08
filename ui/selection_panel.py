import bpy

from ..utils.kanvas_data import get_settings
from .main_panel import KANVAS_PT_MainPanel
from .sections.selection import draw_selection_actions
from .sections.frame_properties import draw_frame_properties, draw_group_properties
from .sections.compare_properties import draw_compare_properties
from .tabs import draw_tabbed


def selected_item(settings):
    """The item the panel shows: the active one when selected, else the first selected."""
    index = settings.active_image_index
    if not (0 <= index < len(settings.images) and settings.images[index].is_selected):
        index = next((i for i, item in enumerate(settings.images) if item.is_selected), -1)
    return settings.images[index] if index >= 0 else None


class KANVAS_PT_SelectionPanel(bpy.types.Panel):
    """Properties of the selected item. Images, shapes and text cards show tabs
    (`ui/tabs`), so only one group of options is open at a time."""
    bl_label = "Selection"
    bl_idname = "KANVAS_PT_SelectionPanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "K-Tools"
    bl_parent_id = "KANVAS_PT_MainPanel"
    bl_order = 2

    @classmethod
    def poll(cls, context):
        return KANVAS_PT_MainPanel.poll(context)

    def draw(self, context):
        layout = self.layout
        settings = get_settings(context)
        item = selected_item(settings)
        if item is None:
            if (0 <= settings.active_arrow_index < len(settings.arrows)
                    or any(arrow.is_selected for arrow in settings.arrows)):
                layout.label(text="Arrow selected")
            else:
                layout.label(text="Nothing selected")
            return
        draw_selection_actions(layout, settings)
        if draw_tabbed(layout, context, settings, item):
            return
        if item.item_type == 'FRAME' and item.frame_is_group:
            draw_group_properties(layout, settings, item)
        elif item.item_type == 'FRAME':
            draw_frame_properties(layout, settings, item)
        elif item.item_type == 'TEXT':
            draw_compare_properties(layout, settings, item)
