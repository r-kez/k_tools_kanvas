"""Headless checks for Kanvas snap sources and guide feedback."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.utils.gpu import ensure_item_ids


addon.register()
try:
    tree = bpy.data.node_groups.new('Snap regression test', 'KanvasNodeTree')
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        settings = tree.kanvas_settings
        bpy.context.tool_settings.use_snap_node = True
        settings.snap_images = True
        settings.snap_grid = False
        settings.snap_threshold = 10
        image = bpy.data.images.new('snap-test', 40, 40)
        moving = settings.images.add()
        moving.name = 'moving'
        moving.image_data = image
        moving.location = (0, 0)
        reference = settings.images.add()
        reference.name = 'reference'
        reference.image_data = image
        reference.location = (100, 0)
        ensure_item_ids(settings)

        helper = KanvasInteractionHelpers()
        helper.drag_mode = 'MOVE'
        helper.multi_targets = [{'img': moving, 'item_id': moving.item_id}]
        nx, ny = helper._snap_item_location(bpy.context, moving, 59.9, 0)
        assert abs(nx - 60) < 0.001 and settings.show_snap_viz_x
        assert abs(settings.snap_viz_x - 80) < 0.001

        nx, ny = helper._snap_item_location(bpy.context, moving, 59.9, 0, ctrl=True)
        assert abs(nx - 59.9) < 0.001 and not settings.show_snap_viz_x

        second = settings.images.add()
        second.name = 'second moving image'
        second.image_data = image
        second.location = (40, 0)
        ensure_item_ids(settings)
        helper.multi_targets = [{'img': moving, 'item_id': moving.item_id},
                                {'img': second, 'item_id': second.item_id}]
        nx, ny = helper._snap_item_location(bpy.context, moving, 19.9, 0)
        assert abs(nx - 20) < 0.001 and settings.snap_viz_x == 80

        # Threshold is in screen pixels: the same view-space gap changes with zoom.
        second.show_in_editor = False
        single = [{'img': moving, 'item_id': moving.item_id}]
        helper.multi_targets = single
        fake_view = lambda scale: SimpleNamespace(
            region_to_view=lambda x, y: (x * scale, y * scale))
        fake_context = lambda scale: SimpleNamespace(
            scene=bpy.context.scene,
            kanvas_tree=tree,
            tool_settings=bpy.context.tool_settings,
            region=SimpleNamespace(view2d=fake_view(scale)))
        nx, _ = helper._snap_item_location(fake_context(1), moving, 48, 0)
        assert nx == 48 and not settings.show_snap_viz_x
        nx, _ = helper._snap_item_location(fake_context(2), moving, 48, 0)
        assert nx == 60 and settings.show_snap_viz_x

        reference.show_in_editor = False
        frame = settings.images.add()
        frame.item_type = 'FRAME'
        frame.frame_node_name = 'snap-frame'
        frame.location = (0, 100)
        frame.frame_width = 150
        frame.frame_height = 150
        frame.auto_resize = True
        moving.parent_frame = frame.frame_node_name
        ensure_item_ids(settings)

        # A frame that fits its moving child must not become a moving snap target.
        helper.frame_targets = []
        nx, ny = helper._snap_item_location(bpy.context, moving, 0.2, 0.2)
        assert (nx, ny) == (0.2, 0.2)
        assert not settings.show_snap_viz_x and not settings.show_snap_viz_y

        # A moving frame must ignore its own children.
        helper.drag_mode = 'FRAME_MOVE'
        helper.multi_targets = []
        helper.frame_targets = [(frame.item_id, tuple(frame.location), 150, 150)]
        nx, ny = helper._snap_item_location(bpy.context, frame, 0.2, 100.2)
        assert (nx, ny) == (0.2, 100.2)
        assert not settings.show_snap_viz_x and not settings.show_snap_viz_y

        # Grid uses the item's anchor and displays the exact snapped axes.
        settings.snap_images = False
        settings.snap_grid = True
        settings.grid_size = 20
        nx, ny = helper._snap_item_location(bpy.context, frame, 7, 107)
        assert (nx, ny) == (0, 100)
        assert settings.show_snap_viz_x and settings.show_snap_viz_y
        assert (settings.snap_viz_x, settings.snap_viz_y) == (0, 100)

        moving.show_in_editor = False
        frame.show_in_editor = False
        settings.snap_images = True
        settings.snap_grid = False
        card = settings.images.add()
        card.item_type = 'TEXT'
        card.text_width = 100
        card.text_height = 60
        card.location = (0, 0)
        reference.show_in_editor = True
        reference.location = (200, 0)
        ensure_item_ids(settings)
        helper.drag_mode = 'MOVE'
        helper.multi_targets = [{'img': card, 'item_id': card.item_id}]
        helper.frame_targets = []
        nx, ny = helper._snap_item_location(bpy.context, card, 129.9, 0)
        assert abs(nx - 130) < 0.001 and settings.snap_viz_x == 180

        print('Snap predictability checks passed')
finally:
    addon.unregister()
