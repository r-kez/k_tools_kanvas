import sys
from pathlib import Path
import bpy

# Setup addon import
sys.path.insert(0, str(Path.cwd().parent))
import k_tools_kanvas as addon
addon.register()

try:
    tree = bpy.data.node_groups.new('Kanvas Frame Test', 'KanvasNodeTree')
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = tree

    scene = bpy.context.scene
    settings = tree.kanvas_settings

    # An explicit multi-attach command is available for small or overlapping frames.
    assert 'attach_to_frame' in dir(bpy.ops.kanvas), "Attach-to-frame operator is missing"
    print("1. Explicit kanvas.attach_to_frame operator is available.")

    with bpy.context.temp_override(area=area, space_data=area.spaces.active):
        # 1. Create first image
        img1 = settings.images.add()
        img1.item_type = 'IMAGE'
        img1.name = 'Image 1'
        img1.image_data = bpy.data.images.new('Img1_data', 100, 100)
        img1.location = (100, 100)
        img1.is_selected = True

        # Create Frame around Image 1
        res = bpy.ops.kanvas.create_frame()
        assert res == {'FINISHED'}
        frames = [i for i in settings.images if i.item_type == 'FRAME']
        assert len(frames) == 1
        frame = frames[0]
        assert frame.auto_resize is True
        img1_item = next(i for i in settings.images if i.name == 'Image 1')
        assert img1_item.parent_frame == frame.frame_node_name
        initial_w = frame.frame_width
        initial_h = frame.frame_height
        print(f"2. Frame created around Image 1. Initial size: {initial_w}x{initial_h}")

        # 2. Add Image 2 directly inside the frame
        from k_tools_kanvas.utils.gpu import find_frame_at_location, update_frame_bounds, auto_fit_frame, auto_parent_images_to_frames, _get_frame_bounds
        
        # Test find_frame_at_location
        found_frame = find_frame_at_location(settings, (100, 80))
        assert found_frame is not None and found_frame.frame_node_name == frame.frame_node_name
        print("3. find_frame_at_location correctly detects frame.")

        # Simulate adding a second image at (200, 50) which is inside or extends the frame
        img2 = settings.images.add()
        img2.item_type = 'IMAGE'
        img2.name = 'Image 2'
        img2.image_data = bpy.data.images.new('Img2_data', 100, 100)
        img2.location = (140, 70)
        
        # Check automatic attachment on location
        target = find_frame_at_location(settings, img2.location)
        if target:
            img2.parent_frame = target.frame_node_name
            update_frame_bounds(tree, settings, target.frame_node_name)
        
        frame = next(i for i in settings.images if i.item_type == 'FRAME')
        img2_item = next(i for i in settings.images if i.name == 'Image 2')
        assert img2_item.parent_frame == frame.frame_node_name
        assert frame.frame_width > initial_w, f"Frame width {frame.frame_width} should be larger than {initial_w}"
        print(f"4. Image 2 added inside frame -> auto-resized to: {frame.frame_width}x{frame.frame_height}")

        # 3. Duplicate Image 2
        settings.active_image_index = [i for i, it in enumerate(settings.images) if it.name == 'Image 2'][0]
        res = bpy.ops.kanvas.duplicate_image()
        assert res == {'FINISHED'}
        img2_copy = settings.images[settings.active_image_index]
        assert img2_copy.parent_frame == frame.frame_node_name
        print("5. Duplicated image retained frame parenting.")

        # 4. Moving image outside without unparent keeps it attached and expands frame
        img2_copy.location = (1500, 1500)
        update_frame_bounds(tree, settings, frame.frame_node_name)
        assert img2_copy.parent_frame == frame.frame_node_name
        assert frame.frame_width > 1000, "Frame should dynamically expand with moving child"
        print("6a. Moving child dynamically expands frame in real time.")

        # Explicit unparenting (pressing F): clears parent and shrinks frame
        img2_copy.parent_frame = ''
        update_frame_bounds(tree, settings, frame.frame_node_name)
        assert img2_copy.parent_frame == ''
        assert frame.frame_width < 500, f"Frame should shrink back after detaching with F, got {frame.frame_width}"
        print("6b. Detached copy with F -> frame dynamically shrunk back.")

        # 5. Detach img2 via operator
        img2_item = next(i for i in settings.images if i.name == 'Image 2')
        img1_item = next(i for i in settings.images if i.name == 'Image 1')
        img2_item.is_selected = True
        img1_item.is_selected = False
        settings.active_image_index = [i for i, it in enumerate(settings.images) if it.name == 'Image 2'][0]
        res = bpy.ops.kanvas.detach_from_frame()
        assert res == {'FINISHED'}
        img2_item = next(i for i in settings.images if i.name == 'Image 2')
        frame = next(i for i in settings.images if i.item_type == 'FRAME')
        assert img2_item.parent_frame == ''
        assert frame.frame_width == initial_w, f"Frame width {frame.frame_width} should have shrunk back to {initial_w}"
        print("7. Detached Image 2 -> frame auto-shrunk back around Image 1.")

        # 6. Frames with images always use Auto Fit, including an attempted
        # manual setting inherited from an older project.
        frame.auto_resize = False
        assert frame.auto_resize is True
        frame.frame_width = 500
        frame.frame_height = 400
        # Re-attach img2
        img2_item.parent_frame = frame.frame_node_name
        update_frame_bounds(tree, settings, frame.frame_node_name)
        assert frame.auto_resize is True
        assert frame.frame_width < 500
        from k_tools_kanvas.utils.gpu.gpu_frame import hit_test_frame
        from k_tools_kanvas.utils.gpu import frame_has_images
        corner = (frame.location[0] + frame.frame_width - 2,
                  frame.location[1] - frame.frame_height + 2)
        assert hit_test_frame(frame, corner, 1,
                              allow_resize=not frame_has_images(settings, frame.frame_node_name)) == 'BODY'
        print("8. Image frame keeps Auto Fit and hides manual corner resize.")

        empty = settings.images.add()
        empty.item_type = 'FRAME'
        empty.frame_node_name = 'empty-test-frame'
        empty.location = (500, 500)
        empty.frame_width = 120
        empty.frame_height = 100
        empty_corner = (618, 402)
        assert not frame_has_images(settings, empty.frame_node_name)
        assert hit_test_frame(empty, empty_corner, 1,
                              allow_resize=True) == 'RESIZE'

        # An already fitted frame must not add an empty Undo step.
        res = bpy.ops.kanvas.fit_frame(frame_name=frame.frame_node_name)
        assert res == {'CANCELLED'}
        frame = next(i for i in settings.images if i.item_type == 'FRAME')
        assert frame.auto_resize is True
        assert frame.frame_width < 500
        print(f"9. Fit frame snapped back to content: {frame.frame_width}x{frame.frame_height}")

finally:
    addon.unregister()

print("ALL TESTS PASSED SUCCESSFULLY!")
