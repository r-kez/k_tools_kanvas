import bpy

from ..utils import measure as mm


class KANVAS_UL_measures(bpy.types.UIList):
    """The marks of the selected image, with what each one reads."""

    def draw_item(self, context, layout, data, mark, icon, active_data, active_propname, index):
        if self.layout_type == 'GRID':
            layout.label(text='', icon='DRIVER_DISTANCE')
            return
        is_scale = mark.measure_id == data.measure_scale_id
        settings = data.id_data.kanvas_settings
        row = layout.row(align=True)
        row.label(text='', icon='PINNED' if is_scale else (
            'DRIVER_DISTANCE' if mark.kind == 'LINE' else 'MESH_PLANE'))
        row.prop(mark, 'name', text='', emboss=False)
        sub = row.row()
        sub.alignment = 'RIGHT'
        sub.label(text=mm.mark_text(data, mark, settings.measure_unit))
        row.prop(mark, 'visible', text='', emboss=False,
                 icon='HIDE_OFF' if mark.visible else 'HIDE_ON')
