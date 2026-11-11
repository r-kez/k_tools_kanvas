"""The K-Tools tab of the 3D View sidebar: what Kanvas has put in the scene, and the
controls of the active reference."""

import bpy

from ..utils import measure as mm
from ..utils import reference_3d as ref
from ..utils import view_target


def _prefs(context):
    addon = context.preferences.addons.get(__package__.split('.')[0])
    return addon.preferences if addon else None


class KANVAS_UL_References3D(bpy.types.UIList):
    bl_idname = 'KANVAS_UL_references_3d'

    def draw_item(self, context, layout, data, entry, icon, active_data, active_property,
                  index=0, flt_flag=0):
        row = layout.row(align=True)
        item = ref.board_item(entry.board, entry.item_id)
        orphan = item is None
        if entry.kind == 'OVERLAY':
            row.label(text=item.name if item else entry.name,
                      icon='ERROR' if orphan else 'OVERLAY')
            if entry.adjusting:
                row.label(text='', icon='OBJECT_ORIGIN')
            sub = row.row()
            sub.alignment = 'RIGHT'
            sub.label(text='Not on the board' if orphan else 'Overlay')
            row.prop(entry, 'show', text='', emboss=False,
                     icon='HIDE_OFF' if entry.show else 'HIDE_ON')
            return
        obj = entry.object
        row.label(text=obj.name if obj else '?',
                  icon='ERROR' if orphan else ('LINKED' if entry.live else 'OUTLINER_OB_IMAGE'))
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
    bl_category = 'K-Tools'

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
        if any(entry.kind == 'OVERLAY' for entry in scene.kanvas_references):
            hidden = scene.kanvas_overlays_hidden
            layout.prop(scene, 'kanvas_overlays_hidden', toggle=True,
                        text='Show Overlays' if hidden else 'Hide Overlays',
                        icon='HIDE_ON' if hidden else 'HIDE_OFF')
        row = layout.row()
        row.template_list('KANVAS_UL_references_3d', '', scene, 'kanvas_references',
                          scene, 'kanvas_reference_index', rows=3)
        column = row.column(align=True)
        column.operator('kanvas.update_3d_reference', icon='FILE_REFRESH', text='')
        column.operator('kanvas.show_reference_in_kanvas', icon='VIEWZOOM', text='')
        column.separator()
        column.operator('kanvas.remove_3d_reference', icon='TRASH', text='')
        if any(entry.kind == 'EMPTY' for entry in scene.kanvas_references):
            layout.operator('kanvas.update_all_3d_references', icon='FILE_REFRESH')


class KANVAS_PT_Reference3DSettings(bpy.types.Panel):
    bl_label = 'Settings'
    bl_idname = 'KANVAS_PT_reference_3d_settings'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'K-Tools'
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
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        row = layout.row()
        row.use_property_split = False
        row.operator('kanvas.convert_3d_reference', icon='ARROW_LEFTRIGHT',
                     text='Make Reference Image' if entry.kind == 'OVERLAY' else 'Make Overlay')
        if entry.kind == 'OVERLAY':
            self._draw_overlay(layout, entry)
            self._draw_view(layout, entry)
            return
        obj = entry.object
        item = ref.board_item(entry.board, entry.item_id)
        scaled = item is not None and bool(item.image_data) and mm.is_calibrated(item)
        column = layout.column()
        size = column.row()
        size.active = not (entry.real_scale and scaled)
        size.prop(obj, 'empty_display_size', text='Size')
        real = column.row()
        real.enabled = scaled or entry.real_scale
        real.prop(entry, 'real_scale',
                  text='Real Scale' if scaled else 'Real Scale (the image has no scale)')
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
        if entry.live:
            self._draw_view(layout, entry)
            layout.label(text='Live: drawn from the board', icon='LINKED')
            layout.operator('kanvas.bake_3d_reference', icon='FILE_IMAGE')
        else:
            layout.label(text='Image file: update after edits', icon='FILE_IMAGE')
            layout.operator('kanvas.update_3d_reference', icon='FILE_REFRESH')
            layout.operator('kanvas.make_3d_reference_live', icon='LINKED')

    def _draw_view(self, layout, entry):
        column = layout.column(heading='3D View')
        column.prop(entry, 'limit_view', text='Only in One View')
        if not entry.limit_view:
            return
        row = column.row(align=True)
        row.prop(entry, 'view_id')
        row.operator('kanvas.use_this_3d_view', text='', icon='RESTRICT_SELECT_OFF')
        row.operator('kanvas.identify_3d_views', text='', icon='INFO')
        if not view_target.target_exists(entry):
            column.label(text='No 3D View has this ID', icon='ERROR')

    def _draw_overlay(self, layout, entry):
        row = layout.row()
        row.use_property_split = False
        row.prop(entry, 'adjusting', toggle=True, icon='OBJECT_ORIGIN',
                 text='Adjust in the View')
        column = layout.column()
        column.prop(entry, 'opacity', slider=True)
        column.prop(entry, 'size', slider=True)
        column.prop(entry, 'anchor')
        column.prop(entry, 'offset', text='Offset')
        column.prop(entry, 'flip_h')
        column.prop(entry, 'show_in')
        column.prop(entry, 'fit_camera')
        column = layout.column(heading='Picture')
        column.prop(entry, 'crop_to_mask')
        column.prop(entry, 'keep_stretch', text='Stretch and Shear')
        column.prop(entry, 'include_markup')
