"""Check Kanvas focus bounds and native node framing cleanup."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas import keymap
from k_tools_kanvas.operators.ops_focus import selected_bounds
from k_tools_kanvas.utils.arrow_geometry import endpoint
from k_tools_kanvas.utils.item_geometry import item_bounds

addon.register()
try:
    assert any(item.properties.action == 'FOCUS' and item.type == 'NUMPAD_PERIOD'
               for _, item in keymap._items)
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Focus test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        image = settings.images.add()
        image.item_type = 'IMAGE'
        image.image_data = bpy.data.images.new('Focus image', 100, 80)
        image.location = (1000, 800)
        image.is_selected = True
        card = settings.images.add()
        card.item_type = 'TEXT'
        card.location = (1450, 500)
        card.is_selected = True
        frame = settings.images.add()
        frame.item_type = 'FRAME'
        frame.location = (1700, 1000)
        frame.frame_width = 200
        frame.frame_height = 180
        frame.is_selected = True
        assert selected_bounds(settings) == (950, 410, 1900, 1000)

        native = tree.nodes.new('NodeReroute')
        native.select = True
        tree.nodes.active = native
        assert bpy.ops.kanvas.focus_selection() == {'FINISHED'}
        assert list(tree.nodes) == [native]
        assert native.select and tree.nodes.active == native
        view = region.view2d
        center = view.region_to_view(region.width // 2, region.height // 2)
        assert abs(center[0] - 1425) < 10 and abs(center[1] - 705) < 10, center
        lower = view.region_to_view(0, 0)
        upper = view.region_to_view(region.width, region.height)
        assert lower[0] < 950 and lower[1] < 410, (lower, upper)
        assert upper[0] > 1900 and upper[1] > 1000, (lower, upper)

        for target in (image, card, frame):
            for item in settings.images:
                item.is_selected = (item == target)
            assert bpy.ops.kanvas.focus_selection() == {'FINISHED'}
            item_left, item_bottom, item_right, item_top = item_bounds(target)
            center = view.region_to_view(region.width // 2, region.height // 2)
            assert abs(center[0] - (item_left + item_right) / 2) < 10, center
            assert abs(center[1] - (item_bottom + item_top) / 2) < 10, center

        for item in settings.images:
            item.is_selected = False
        assert bpy.ops.kanvas.focus_selection() == {'PASS_THROUGH'}

        arrow = settings.arrows.add()
        arrow.start = (2000, 1200)
        arrow.end = (2400, 1400)
        settings.active_arrow_index = len(settings.arrows) - 1
        assert selected_bounds(settings) == (2000, 1200, 2400, 1400)
        assert bpy.ops.kanvas.focus_selection() == {'FINISHED'}
        center = view.region_to_view(region.width // 2, region.height // 2)
        assert abs(center[0] - 2200) < 10 and abs(center[1] - 1300) < 10, center

        arrow.curve_offset = (0, 100)
        assert selected_bounds(settings)[3] > 1400
        arrow.curve_offset = (0, 300)
        assert selected_bounds(settings)[3] > 1600
        arrow.curve_offset = (0, 0)

        card.item_id = 'focus-card'
        arrow.start_item_id = card.item_id
        arrow.start_uv = (0.5, 0.5)
        card.location = (2800, 1700)
        start = endpoint(settings, arrow, 'start')
        assert selected_bounds(settings) == (min(start[0], 2400),
                                            min(start[1], 1400),
                                            max(start[0], 2400),
                                            max(start[1], 1400))
        assert bpy.ops.kanvas.focus_selection() == {'FINISHED'}
        center = view.region_to_view(region.width // 2, region.height // 2)
        assert abs(center[0] - (start[0] + 2400) / 2) < 10, center
        assert abs(center[1] - (start[1] + 1400) / 2) < 10, center

        arrow.curve_offset = (80, -40)
        assert bpy.ops.kanvas.reset_arrow_curvature() == {'FINISHED'}
        assert tuple(arrow.curve_offset) == (0, 0)
        assert arrow.start_item_id == card.item_id
        assert endpoint(settings, arrow, 'start') == start

        settings.active_arrow_index = -1
        assert bpy.ops.kanvas.focus_selection() == {'FINISHED'}
        arrow.is_selected = False
        assert bpy.ops.kanvas.focus_selection() == {'PASS_THROUGH'}
        assert list(tree.nodes) == [native]
    print('focus selection smoke test passed')
finally:
    addon.unregister()
