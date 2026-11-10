"""The Kanvas tab of the 3D View sidebar: what Kanvas has put in the scene, and the
controls of the active reference."""

import bpy

from ..utils import reference_3d as ref


def _prefs(context):
    addon = context.preferences.addons.get(__package__.split('.')[0])
    return addon.preferences if addon else None


class KANVAS_UL_References3D(bpy.types.UIList):
    bl_idname = 'KANVAS_UL_references_3d'

    def draw_item(self, context, layout, data, entry, icon, active_data, active_property,
                  index=0, flt_flag=0):
        obj = entry.object
        row = layout.row(align=True)
        orphan = ref.board_item(entry.board, entry.item_id) is None
        row.label(text=obj.name if obj else '?',
                  icon='ERROR' if orphan else 'OUTLINER_OB_IMAGE')
        view = dict((key, name) for key, name, _ in ref.VIEW_ITEMS).get(entry.view, '')
        sub = row.row()
        sub.alignment = 'RIGHT'
        sub.label(text='Not on the board' if orphan else view)
        if obj is not None:
            row.prop(obj, 'hide_viewport', text='', emboss=False,
                     icon='HIDE_ON' if obj.hide_viewport else 'HIDE_OFF')

    def filter_items(self, context, data, property):
        references = getattr(data, property)
        # Deleted empties are dropped from the list the next time an operator runs.
        flags = [0 if ref.is_deleted(entry) else self.bitflag_filter_item
                 for entry in references]
        return flags, []


class KANVAS_PT_References3D(bpy.types.Panel):
    bl_label = 'References'
    bl_idname = 'KANVAS_PT_references_3d'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Kanvas'

    @classmethod
    def poll(cls, context):
        prefs = _prefs(context)
        return getattr(context, 'scene', None) is not None and (
            prefs is None or getattr(prefs, 'show_3d_references_panel', True))

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        if not any(not ref.is_deleted(entry) for entry in scene.kanvas_references):
            column = layout.column(align=True)
            column.label(text='No references yet', icon='INFO')
            column.label(text='In Kanvas, select images and choose')
            column.label(text='Send to 3D View in the right-click menu')
            return
        row = layout.row()
        row.template_list('KANVAS_UL_references_3d', '', scene, 'kanvas_references',
                          scene, 'kanvas_reference_index', rows=3)
        column = row.column(align=True)
        column.operator('kanvas.update_3d_reference', icon='FILE_REFRESH', text='')
        column.operator('kanvas.show_reference_in_kanvas', icon='VIEWZOOM', text='')
        column.separator()
        column.operator('kanvas.remove_3d_reference', icon='TRASH', text='')
        layout.operator('kanvas.update_all_3d_references', icon='FILE_REFRESH')


class KANVAS_PT_Reference3DSettings(bpy.types.Panel):
    bl_label = 'Settings'
    bl_idname = 'KANVAS_PT_reference_3d_settings'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Kanvas'
    bl_parent_id = 'KANVAS_PT_references_3d'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        index = scene.kanvas_reference_index
        return (0 <= index < len(scene.kanvas_references)
                and not ref.is_deleted(scene.kanvas_references[index]))

    def draw(self, context):
        scene = context.scene
        entry = scene.kanvas_references[scene.kanvas_reference_index]
        obj = entry.object
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        column = layout.column()
        column.prop(obj, 'empty_display_size', text='Size')
        row = column.row(heading='Opacity')
        row.prop(obj, 'use_empty_image_alpha', text='')
        sub = row.row()
        sub.active = obj.use_empty_image_alpha
        sub.prop(obj, 'color', index=3, text='', slider=True)
        column.prop(obj, 'empty_image_depth', text='Depth')
        column.prop(obj, 'empty_image_side', text='Side')
        column = layout.column(heading='Show')
        column.prop(obj, 'show_empty_image_orthographic', text='Orthographic')
        column.prop(obj, 'show_empty_image_perspective', text='Perspective')
        column.prop(obj, 'show_empty_image_only_axis_aligned', text='Only Axis Aligned')
        layout.separator()
        column = layout.column(heading='Picture')
        column.prop(entry, 'crop_to_mask')
        column.prop(entry, 'keep_stretch', text='Stretch and Shear')
        column.prop(entry, 'include_markup')
        layout.operator('kanvas.update_3d_reference', icon='FILE_REFRESH')
