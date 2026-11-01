import bpy
import sys
import os

addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(addon_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu import update_frame_bounds, get_frame
from k_tools_kanvas.operators.ops_modal import KANVAS_OT_Interact

addon.register()

try:
    tree = bpy.data.node_groups.new(name="KanvasTestTree", type='KanvasNodeTree')
    area = bpy.context.window.screen.areas[0]
    area.type = 'NODE_EDITOR'
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')

    scene = bpy.context.scene
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        # Create dummy images
        img_data1 = bpy.data.images.new("TestImg1", width=100, height=100)
        img_data2 = bpy.data.images.new("TestImg2", width=100, height=100)

        item1 = settings.images.add()
        item1.item_type = 'IMAGE'
        item1.image_data = img_data1
        item1.name = "Img1"
        item1.location = (0, 0)
        item1.is_selected = True

        # Create frame around item1
        bpy.ops.kanvas.create_frame()
        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        item1 = next(it for it in settings.images if it.name == "Img1")
        assert item1.parent_frame == frame.frame_node_name

        # Add item2 inside the frame
        item2 = settings.images.add()
        item2.item_type = 'IMAGE'
        item2.image_data = img_data2
        item2.name = "Img2"
        item2.location = (0, 0)
        item2.parent_frame = frame.frame_node_name
        item2.is_selected = False
        update_frame_bounds(tree, settings, frame.frame_node_name)

        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        item1 = next(it for it in settings.images if it.name == "Img1")
        init_w = frame.frame_width
        init_h = frame.frame_height

        from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
        class DummyInteract(KanvasInteractionHelpers):
            modal = KANVAS_OT_Interact.modal
            _end = lambda self, ctx, res: res

        interact = DummyInteract()
        interact.start_drag(bpy.context, item1, 'MOVE', (0, 0))

        assert interact.drag_target == item1
        assert interact.f_is_held is False
        assert len(interact.multi_targets) == 1
        assert interact.multi_targets[0]['orig_parent'] == frame.frame_node_name

        # Move mouse by (200, 200)
        interact._update_drag(bpy.context, 200, 200)
        assert item1.location[0] == 200
        assert item1.location[1] == 200
        # Frame should have dynamically grown
        assert frame.frame_width > init_w, f"Frame width {frame.frame_width} should be > {init_w}"
        print(f"1. Dynamic resize during drag verified: frame grew from {init_w} to {frame.frame_width}")

        # Simulate pressing 'F' while dragging
        class FakeFPressEvent:
            type = 'F'
            value = 'PRESS'
            shift = False
            alt = False
            ctrl = False

        res = interact.modal(bpy.context, FakeFPressEvent())
        assert res == {'RUNNING_MODAL'}
        assert interact.f_is_held is True
        assert item1.parent_frame == ''
        assert item1.item_id in interact.detached_in_gesture
        print("2. Detached using 'F' key during drag verified!")

        # Stop drag
        interact._stop_drag(bpy.context)
        item1 = next(it for it in settings.images if it.name == "Img1")
        assert item1.parent_frame == ''
        print("3. Drag stopped: item remains detached and unparented.")

        # Test drag cancel: re-attach item1 and drag, then cancel
        item1.parent_frame = frame.frame_node_name
        update_frame_bounds(tree, settings, frame.frame_node_name)
        item1 = next(it for it in settings.images if it.name == "Img1")
        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        before_cancel_w = frame.frame_width

        interact.start_drag(bpy.context, item1, 'MOVE', (item1.location[0], item1.location[1]))
        interact._update_drag(bpy.context, 500, 500)
        assert frame.frame_width > before_cancel_w

        # Cancel drag (simulating ESC)
        interact._cancel_drag(bpy.context)
        item1 = next(it for it in settings.images if it.name == "Img1")
        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        assert item1.parent_frame == frame.frame_node_name
        assert frame.frame_width == before_cancel_w
        print("4. Drag cancelled: original parenting and frame bounds restored successfully.")

finally:
    addon.unregister()

print("ALL MODAL DRAG & 'F' KEY TESTS PASSED!")
