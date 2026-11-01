"""Blender regression check for live frame bounds and header sizing."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Frame live updates', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, space_data=area.spaces.active):
        image = settings.images.add()
        image.item_type = 'IMAGE'
        image.image_data = bpy.data.images.new('Frame live image', 100, 80)
        image.location = (100, 100)
        image.is_selected = True
        assert bpy.ops.kanvas.create_frame() == {'FINISHED'}
        frame = next(item for item in settings.images if item.item_type == 'FRAME')
        image = next(item for item in settings.images if item.item_type == 'IMAGE')

        width = frame.frame_width
        image.scale_master = 2
        assert frame.frame_width > width, 'Scale must resize the frame immediately'
        width = frame.frame_width
        image.rotation = 45
        assert frame.frame_width != width, 'Rotation must resize the frame immediately'
        width = frame.frame_width
        old_left = frame.location[0]
        image.location[0] += 100
        assert frame.location[0] > old_left, 'Location must update the frame immediately'
        image.shear_xy[0] = 0.5
        assert frame.frame_width != width, 'Shear must resize the frame immediately'

        from k_tools_kanvas.utils.gpu.gpu_frame import frame_header_height, hit_test_frame
        old_height = frame_header_height(frame)
        old_frame_height = frame.frame_height
        frame.frame_font_size = 30
        assert frame_header_height(frame) > old_height
        assert frame.frame_height > old_frame_height
        point = (frame.location[0] + 5, frame.location[1] - frame_header_height(frame) + 2)
        assert hit_test_frame(frame, point, 1) == 'MOVE'

        frame.auto_resize = False
        frame.frame_width = 500
        frame.frame_height = 400
        original = (frame.frame_width, frame.frame_height)
        from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
        helper = KanvasInteractionHelpers()
        helper._start_frame_drag(bpy.context, frame, 'MOVE', (0, 0))
        helper._update_drag(bpy.context, 100, 0)
        assert (frame.frame_width, frame.frame_height) == original, 'Moving a manual frame must preserve its size'
        print('FRAME LIVE UPDATES PASS')
finally:
    addon.unregister()
