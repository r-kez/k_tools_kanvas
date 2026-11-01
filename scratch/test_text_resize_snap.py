"""Check Ctrl snap on the moving edges of a text card."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.utils.item_geometry import item_bounds


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Text resize snap', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        settings = tree.kanvas_settings
        settings.snap_images = True
        settings.snap_grid = False
        settings.snap_threshold = 20

        card = settings.images.add()
        card.item_type = 'TEXT'
        card.text_width = 200
        card.text_height = 100
        card.location = (0, 0)
        reference = settings.images.add()
        reference.item_type = 'IMAGE'
        reference.image_data = bpy.data.images.new('Resize reference', 20, 20)
        reference.location = (205, -150)

        helper = KanvasInteractionHelpers()
        helper._start_text_resize(card, (0, 0))
        start = (tuple(card.location), card.text_width, card.text_height)
        helper._update_drag(bpy.context, 94, -89)
        assert not settings.show_snap_viz_x and not settings.show_snap_viz_y
        assert abs(item_bounds(card)[2] - 194) < 0.001
        assert abs(item_bounds(card)[1] + 139) < 0.001

        helper._update_drag(bpy.context, 94, -89, ctrl=True)
        assert abs(item_bounds(card)[2] - 195) < 0.001
        assert abs(item_bounds(card)[1] + 140) < 0.001
        assert settings.show_snap_viz_x and settings.show_snap_viz_y
        assert abs(settings.snap_viz_x - 195) < 0.001
        assert abs(settings.snap_viz_y + 140) < 0.001

        zoomed_context = SimpleNamespace(
            space_data=area.spaces.active,
            region=SimpleNamespace(view2d=SimpleNamespace(
                region_to_view=lambda x, y: (x * 0.01, y * 0.01))))
        width, height = helper._snap_text_resize_edges(
            zoomed_context, -100, 50, 294, 189, ctrl=True)
        assert (width, height) == (294, 189)
        assert not settings.show_snap_viz_x and not settings.show_snap_viz_y

        settings.snap_images = False
        settings.snap_grid = True
        settings.grid_size = 10
        width, height = helper._snap_text_resize_edges(
            bpy.context, -100, 50, 294, 189, ctrl=True)
        assert (width, height) == (290, 190)
        assert settings.snap_viz_x == 190 and settings.snap_viz_y == -140
        settings.snap_images = True
        settings.snap_grid = False

        helper._update_drag(bpy.context, 94, -60, ctrl=True)
        assert settings.show_snap_viz_x and not settings.show_snap_viz_y
        assert abs(item_bounds(card)[1] + 110) < 0.001
        helper._cancel_drag(bpy.context)
        assert (tuple(card.location), card.text_width, card.text_height) == start
        assert not settings.show_snap_viz_x and not settings.show_snap_viz_y

    print('TEXT RESIZE SNAP PASS')
finally:
    addon.unregister()
