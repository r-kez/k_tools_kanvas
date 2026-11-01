"""Locked board items stay visible but cannot be selected or transformed by gestures."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers, _select_canvas_items
from k_tools_kanvas.utils.arrow_geometry import hit_arrow


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Locked items', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        image = settings.images.add()
        image.item_type = 'IMAGE'
        image.image_data = bpy.data.images.new('Lock image', 20, 20)
        image.location = (0, 0)
        image.is_selected = True
        image.is_locked = True
        assert not image.is_selected

        card = settings.images.add()
        card.item_type = 'TEXT'
        card.location = (200, 0)

        frame = settings.images.add()
        frame.item_type = 'FRAME'
        frame.frame_node_name = 'locked-frame'
        frame.location = (400, 0)
        frame.frame_width = 150
        frame.frame_height = 100
        frame.is_locked = True

        arrow = settings.arrows.add()
        arrow.start = (600, 0)
        arrow.end = (700, 0)
        arrow.is_selected = True
        arrow.is_locked = True
        assert not arrow.is_selected

        helper = KanvasInteractionHelpers()
        assert helper._find_image_at_pos(bpy.context, (0, 0)) == (None, None)
        assert helper._frame_hit(bpy.context, (450, -10)) == (None, None, None)
        assert hit_arrow(settings, (600, 0), 1.0) == (None, None)
        assert _select_canvas_items(settings)
        assert not image.is_selected and card.is_selected and not frame.is_selected
        assert not arrow.is_selected

        settings.active_image_index = 0
        assert not image.is_selected
        assert bpy.ops.kanvas.remove_image(index=0) == {'CANCELLED'}
        assert bpy.ops.kanvas.duplicate_image() == {'CANCELLED'}
        settings.active_arrow_index = 0
        assert bpy.ops.kanvas.remove_arrow() == {'CANCELLED'}

        image.is_locked = False
        frame.is_locked = False
        arrow.is_locked = False
        assert helper._find_image_at_pos(bpy.context, (0, 0))[1] is not None
        assert helper._frame_hit(bpy.context, (450, -10))[1] is not None
        assert hit_arrow(settings, (600, 0), 1.0)[0] == 0
    print('LOCKED ITEMS PASS')
finally:
    addon.unregister()
