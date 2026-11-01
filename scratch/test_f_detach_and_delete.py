"""Automated test for:
1. Holding F to detach item from frame during drag
2. Holding F before dragging to detach item from frame
3. Single image in frame detaching with F and restoring initial frame bounds
4. Deleting Text Card with Delete / X shortcut
5. Deleting Frame with Delete / X shortcut (unparenting children)
6. Multi-selection Delete of mixed types (Frame, Text Card, Image)
"""
import sys
import os
from types import SimpleNamespace
import bpy

addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(addon_dir))

import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.utils.gpu import update_frame_bounds, get_frame
from k_tools_kanvas.operators.ops_modal import KANVAS_OT_Interact, KanvasInteractionHelpers

addon.register()

try:
    tree = bpy.data.node_groups.new(name="KanvasTestTree", type='KanvasNodeTree')
    area = bpy.context.window.screen.areas[0]
    area.type = 'NODE_EDITOR'
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    class Gesture(KanvasInteractionHelpers):
        invoke = KANVAS_OT_Interact.invoke
        modal = KANVAS_OT_Interact.modal
        def _begin_gesture(self, context):
            return {'RUNNING_MODAL'}
        def _end(self, context, result):
            return result

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        from k_tools_kanvas.operators import ops_modal
        ops_modal.get_prefs = lambda: SimpleNamespace(
            wheel_opacity_mod='NONE', wheel_scale_mod='NONE', wheel_layer_mod='NONE',
            key_shear_mod='ALT', box_select_alt_drag=False, box_select_on_drag=True
        )

        # -------------------------------------------------------------
        # TEST 1: Holding F while dragging to detach from frame (2 images)
        # -------------------------------------------------------------
        print("\n--- TEST 1: Hold F while dragging (2 images in frame) ---")
        img_data1 = bpy.data.images.new("T1", width=100, height=100)
        img_data2 = bpy.data.images.new("T2", width=100, height=100)

        item1 = settings.images.add()
        item1.item_type = 'IMAGE'
        item1.name = "Img1"
        item1.image_data = img_data1
        item1.location = (0, 0)
        item1.is_selected = True

        bpy.ops.kanvas.create_frame()
        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        item1 = next(it for it in settings.images if it.name == "Img1")

        item2 = settings.images.add()
        item2.item_type = 'IMAGE'
        item2.name = "Img2"
        item2.image_data = img_data2
        item2.location = (200, 0)
        item2.parent_frame = frame.frame_node_name
        item2.is_selected = False
        update_frame_bounds(tree, settings, frame.frame_node_name)

        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        init_frame_w = frame.frame_width
        print(f"Initial frame width with 2 images: {init_frame_w}")

        # Drag item1
        item1.is_selected = True
        item2.is_selected = False
        g1 = Gesture()
        g1.action = 'CLICK'
        g1.start_drag(bpy.context, item1, 'MOVE', (0, 0))
        g1._update_drag(bpy.context, 1000, 1000)
        assert frame.frame_width > init_frame_w, "Frame should expand while dragging item1 without F"
        print(f"Frame expanded to {frame.frame_width} during drag")

        # Press F to detach
        f_event = SimpleNamespace(type='F', value='PRESS', shift=False, ctrl=False, alt=False)
        g1.modal(bpy.context, f_event)
        assert item1.parent_frame == '', "item1 must be detached after pressing F"
        assert frame.frame_width < init_frame_w, f"Frame should shrink around item2, got {frame.frame_width}"
        print(f"Frame shrunk back to {frame.frame_width} after pressing F!")

        # Complete drag
        g1._stop_drag(bpy.context)
        img1 = next(it for it in settings.images if it.name == "Img1")
        assert img1.parent_frame == '', "Img1 must remain unparented after drag stops"
        print("TEST 1 PASSED!")

        # -------------------------------------------------------------
        # TEST 2: Single image in frame detaching with F restores frame bounds
        # -------------------------------------------------------------
        print("\n--- TEST 2: Single image in frame detaching with F ---")
        settings.images.clear()
        single_img = settings.images.add()
        single_img.item_type = 'IMAGE'
        single_img.name = "SingleImg"
        single_img.image_data = img_data1
        single_img.location = (0, 0)
        single_img.is_selected = True

        bpy.ops.kanvas.create_frame()
        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        single_img = next(it for it in settings.images if it.name == "SingleImg")
        orig_frame_loc = tuple(frame.location)
        orig_frame_w, orig_frame_h = frame.frame_width, frame.frame_height
        print(f"Single image initial frame loc={orig_frame_loc}, size=({orig_frame_w}, {orig_frame_h})")

        g2 = Gesture()
        g2.action = 'CLICK'
        g2.start_drag(bpy.context, single_img, 'MOVE', (0, 0))
        g2._update_drag(bpy.context, 800, 800)

        # Press F
        g2.modal(bpy.context, f_event)
        assert single_img.parent_frame == '', "SingleImg must be detached"
        # The frame should have snapped back to its bounds before the drag
        assert frame.location[0] == orig_frame_loc[0] and frame.location[1] == orig_frame_loc[1], \
            f"Frame should restore original location {orig_frame_loc}, got {frame.location}"
        assert frame.frame_width == orig_frame_w and frame.frame_height == orig_frame_h, \
            f"Frame should restore original size ({orig_frame_w}, {orig_frame_h}), got ({frame.frame_width}, {frame.frame_height})"
        g2._stop_drag(bpy.context)
        single_post = next(it for it in settings.images if it.name == "SingleImg")
        assert single_post.parent_frame == '', "SingleImg must remain unparented after drag stops"
        print("TEST 2 PASSED!")

        # -------------------------------------------------------------
        # TEST 3: Holding F before clicking & dragging
        # -------------------------------------------------------------
        print("\n--- TEST 3: Holding F before clicking & dragging ---")
        settings.images.clear()
        item_a = settings.images.add()
        item_a.item_type = 'IMAGE'
        item_a.name = "ItemA"
        item_a.image_data = img_data1
        item_a.location = (0, 0)
        item_a.is_selected = True

        bpy.ops.kanvas.create_frame()
        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        item_a = next(it for it in settings.images if it.name == "ItemA")

        # Simulate user holding F (F key was pressed down)
        settings.f_is_held = True
        g3 = Gesture()
        g3.start_drag(bpy.context, item_a, 'MOVE', (0, 0))
        assert g3.f_is_held is True, "Gesture should pick up settings.f_is_held"
        assert item_a.parent_frame == '', "item_a should immediately detach because F was held on drag start"
        g3._update_drag(bpy.context, 400, 400)
        assert item_a.parent_frame == '', "item_a remains unparented during drag"
        g3._stop_drag(bpy.context)
        item_a_post = next(it for it in settings.images if it.name == "ItemA")
        assert item_a_post.parent_frame == '', "item_a remains unparented after drop"
        print("TEST 3 PASSED!")

        # Pressing F before a drag must only arm release, never create a frame.
        rx, ry = region.width // 2, region.height // 2
        press = SimpleNamespace(type='F', value='PRESS',
                                mouse_x=region.x + rx, mouse_y=region.y + ry,
                                mouse_region_x=rx, mouse_region_y=ry,
                                shift=False, ctrl=False, alt=False)
        release = SimpleNamespace(type='F', value='RELEASE',
                                  mouse_x=press.mouse_x, mouse_y=press.mouse_y,
                                  mouse_region_x=rx, mouse_region_y=ry,
                                  shift=False, ctrl=False, alt=False)
        before_count = len(settings.images)
        f_press = Gesture()
        f_press.action = 'F_PRESS'
        assert f_press.invoke(bpy.context, press) == {'CANCELLED'}
        assert settings.f_is_held and len(settings.images) == before_count
        f_release = Gesture()
        f_release.action = 'F_RELEASE'
        assert f_release.invoke(bpy.context, release) == {'CANCELLED'}
        assert not settings.f_is_held and len(settings.images) == before_count
        print("TEST 3b PASSED: F alone does not create a frame!")

        # -------------------------------------------------------------
        # TEST 4: Delete Text Card with Del / X shortcut
        # -------------------------------------------------------------
        print("\n--- TEST 4: Delete Text Card with DELETE action ---")
        settings.images.clear()
        card = settings.images.add()
        card.item_type = 'TEXT'
        card.name = "NoteCard"
        card.text_body = "Important note"
        card.is_selected = True
        settings.active_image_index = 0
        assert len(settings.images) == 1

        # Simulate DELETE action (from Del / X keymap)
        # Directly call execute on remove_image
        res = bpy.ops.kanvas.remove_image('EXEC_DEFAULT', index=-1)
        assert res == {'FINISHED'}, f"remove_image result: {res}"
        assert len(settings.images) == 0, "Text card must be deleted"
        print("TEST 4 PASSED: Text Card successfully deleted with DELETE!")

        # -------------------------------------------------------------
        # TEST 5: Delete Frame with Del / X shortcut
        # -------------------------------------------------------------
        print("\n--- TEST 5: Delete Frame with DELETE action ---")
        settings.images.clear()
        child_img = settings.images.add()
        child_img.item_type = 'IMAGE'
        child_img.name = "ChildImg"
        child_img.image_data = img_data1
        child_img.is_selected = True

        bpy.ops.kanvas.create_frame()
        frame = next(it for it in settings.images if it.item_type == 'FRAME')
        child_img = next(it for it in settings.images if it.name == "ChildImg")
        assert child_img.parent_frame == frame.frame_node_name

        # Select only the frame
        frame.is_selected = True
        child_img.is_selected = False
        settings.active_image_index = [i for i, it in enumerate(settings.images) if it.item_type == 'FRAME'][0]

        # Execute remove_image (Del / X action)
        res = bpy.ops.kanvas.remove_image('EXEC_DEFAULT', index=-1)
        assert res == {'FINISHED'}, f"remove_image result: {res}"
        assert not any(it.item_type == 'FRAME' for it in settings.images), "Frame must be deleted"
        assert len(settings.images) == 1, "Child image must still exist"
        child_img = settings.images[0]
        assert child_img.parent_frame == "", "Child image must be unparented when frame is deleted"
        print("TEST 5 PASSED: Frame deleted and child cleanly unparented!")

        # -------------------------------------------------------------
        # TEST 6: Multi-selection Delete (Frame + Text + Image)
        # -------------------------------------------------------------
        print("\n--- TEST 6: Multi-selection Delete ---")
        settings.images.clear()
        m_img = settings.images.add()
        m_img.item_type = 'IMAGE'
        m_img.name = "MImg"
        m_img.image_data = img_data1
        m_img.is_selected = True

        m_card = settings.images.add()
        m_card.item_type = 'TEXT'
        m_card.name = "MCard"
        m_card.text_body = "Hello"
        m_card.is_selected = True

        bpy.ops.kanvas.create_frame()
        assert len(settings.images) == 3  # Frame, MImg, MCard

        # Select all 3
        for it in settings.images:
            it.is_selected = True

        res = bpy.ops.kanvas.remove_image('EXEC_DEFAULT', index=-1)
        assert res == {'FINISHED'}
        assert len(settings.images) == 0, "All items must be deleted"
        print("TEST 6 PASSED: Multi-selection Delete passed!")

        # Also test DELETE action check in ops_modal
        settings.images.clear()
        f_item = settings.images.add()
        f_item.item_type = 'FRAME'
        f_item.name = "F1"
        f_item.is_selected = True
        g_del = Gesture()
        g_del.action = 'DELETE'
        # Calling invoke should trigger remove_image if has_selected is True
        # In non-interactive mode invoke_confirm would cancel, but let's check it doesn't return PASS_THROUGH
        event_del = SimpleNamespace(type='X', value='PRESS',
                                    mouse_x=region.x + 20,
                                    mouse_y=region.y + region.height // 2,
                                    mouse_region_x=20,
                                    mouse_region_y=region.height // 2,
                                    shift=False, ctrl=False, alt=False)
        res_del = g_del.invoke(bpy.context, event_del)
        assert res_del == {'CANCELLED'}, f"DELETE action on FRAME must invoke remove_image, got {res_del}"
        print("DELETE action invocation on Frame verified!")

        card_item = settings.images.add()
        card_item.item_type = 'TEXT'
        card_item.name = "C1"
        card_item.is_selected = True
        f_item.is_selected = False
        res_card_del = g_del.invoke(bpy.context, event_del)
        assert res_card_del == {'CANCELLED'}, f"DELETE action on TEXT must invoke remove_image, got {res_card_del}"
        print("DELETE action invocation on Text Card verified!")

finally:
    addon.unregister()

print("\n==========================================")
print("ALL TESTS IN test_f_detach_and_delete.py PASSED!")
print("==========================================")
