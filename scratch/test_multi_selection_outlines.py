import bpy
import sys
import os

addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(addon_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu import draw_callback_px

addon.register()

try:
    tree = bpy.data.node_groups.new(name="KanvasTestTree", type='KanvasNodeTree')
    area = bpy.context.window.screen.areas[0]
    area.type = 'NODE_EDITOR'
    area.spaces.active.node_tree = tree

    scene = bpy.context.scene
    settings = scene.kanvas_settings

    # Create 3 images
    data1 = bpy.data.images.new("Img1", 100, 100)
    data2 = bpy.data.images.new("Img2", 100, 100)
    data3 = bpy.data.images.new("Img3", 100, 100)

    for i, data in enumerate([data1, data2, data3]):
        it = settings.images.add()
        it.item_type = 'IMAGE'
        it.name = f"Image_{i}"
        it.image_data = data
        it.location = (i * 150, 0)
        it.is_selected = True

    with bpy.context.temp_override(area=area, space_data=area.spaces.active):
        # Call draw callback — should run without exceptions and process all 3 outlines
        draw_callback_px()
        print("Multi-selection draw callback executed successfully with 3 selected images!")

finally:
    addon.unregister()

print("MULTI-SELECTION OUTLINE TEST PASSED!")
