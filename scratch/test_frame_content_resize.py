"""A filled frame auto-fits; an empty one remains manually resizable."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu import frame_has_content, update_frame_bounds
from k_tools_kanvas.utils.gpu.gpu_frame import hit_test_frame


addon.register()
try:
    tree = bpy.data.node_groups.new('Frame content resize', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    frame = settings.images.add()
    frame.item_type = 'FRAME'
    frame.frame_node_name = 'frame-content-test'
    frame.location = (0, 0)
    frame.frame_width = 300
    frame.frame_height = 200
    frame.auto_resize = False
    corner = (299, -199)
    assert not frame_has_content(settings, frame.frame_node_name)
    assert hit_test_frame(frame, corner, 1.0, allow_resize=True) == 'RESIZE'

    card = settings.images.add()
    card.item_type = 'TEXT'
    card.location = (150, -100)
    card.parent_frame = frame.frame_node_name
    update_frame_bounds(tree, settings, frame.frame_node_name)
    assert frame_has_content(settings, frame.frame_node_name)
    assert frame.auto_resize
    assert hit_test_frame(frame, corner, 1.0, allow_resize=False) != 'RESIZE'

    card.parent_frame = ''
    assert not frame_has_content(settings, frame.frame_node_name)
    corner = (frame.location[0] + frame.frame_width - 1,
              frame.location[1] - frame.frame_height + 1)
    assert hit_test_frame(frame, corner, 1.0, allow_resize=True) == 'RESIZE'
    print('FRAME CONTENT RESIZE PASS')
finally:
    addon.unregister()
