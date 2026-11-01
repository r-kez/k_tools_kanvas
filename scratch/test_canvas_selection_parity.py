"""Exercise active paint order and arrow selection in Blender 5.2."""

from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers, _set_canvas_active
from k_tools_kanvas.operators.ops_focus import selected_bounds
from k_tools_kanvas.utils.item_geometry import image_draw_indices, text_card_draw_indices


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Selection parity', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        for name in ('Back', 'Front'):
            item = settings.images.add()
            item.item_type = 'IMAGE'
            item.image_data = bpy.data.images.new(name, 40, 40)
            item.location = (0, 0)
        settings.images[0].is_selected = True
        _set_canvas_active(settings, image_index=0)
        assert image_draw_indices(settings) == [1, 0]
        assert KanvasInteractionHelpers()._find_image_at_pos(bpy.context, (0, 0))[0] == 0
        assert [item.z_index for item in settings.images] == [0, 0]

        for name in ('Back card', 'Front card'):
            item = settings.images.add()
            item.item_type = 'TEXT'
            item.name = name
            item.location = (200, 0)
        settings.images[0].is_selected = False
        settings.images[2].is_selected = True
        _set_canvas_active(settings, image_index=2)
        assert text_card_draw_indices(settings) == [3, 2]
        assert KanvasInteractionHelpers()._find_image_at_pos(bpy.context, (200, 0))[0] == 2

        for start, end in (((400, 0), (500, 0)), ((400, 30), (500, 30))):
            arrow = settings.arrows.add()
            arrow.start = start
            arrow.end = end
        helper = KanvasInteractionHelpers()
        helper.box_additive = False
        helper.box_region_start = (0, 0)
        helper.box_region_end = (80, 80)
        settings.box_sel_start = (420, -10)
        settings.box_sel_end = (480, 40)
        assert helper._perform_box_selection(bpy.context)
        assert [arrow.is_selected for arrow in settings.arrows] == [True, True]
        assert settings.active_arrow_index >= 0
        bounds = selected_bounds(settings)
        assert bounds[0] <= 400 and bounds[2] >= 500
        assert bpy.ops.kanvas.remove_arrow() == {'FINISHED'}
        assert len(settings.arrows) == 0
    print('CANVAS SELECTION PARITY PASS')
finally:
    addon.unregister()
