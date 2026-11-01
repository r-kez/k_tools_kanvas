"""A click and slight pointer jitter must not move or relayer an image."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Click selection', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        settings = tree.kanvas_settings
        image = settings.images.add()
        image.item_type = 'IMAGE'
        image.image_data = bpy.data.images.new('Click test', 20, 20)
        image.location = (0, 0)
        image.z_index = 3
        image.is_selected = True
        settings.active_image_index = 0
        assert image.z_index == 3

        view = region.view2d
        start = view.region_to_view(region.width // 2, region.height // 2)
        image.location = start
        origin = tuple(image.location)
        helper = KanvasInteractionHelpers()
        helper.start_drag(bpy.context, image, 'MOVE', start)
        slight = view.region_to_view(region.width // 2 + 1, region.height // 2 + 1)
        helper._update_drag(bpy.context, *slight)
        assert tuple(image.location) == origin
        assert image.z_index == 3

        moved = view.region_to_view(region.width // 2 + 12, region.height // 2)
        helper._update_drag(bpy.context, *moved)
        assert tuple(image.location) != origin
        assert image.z_index == 3

    print('CLICK SELECTION NO MOVE PASS')
finally:
    addon.unregister()
