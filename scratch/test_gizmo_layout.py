"""Check that visible transform handles are the ones hit by Kanvas."""

import sys
from pathlib import Path

import bpy
import gpu

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.utils.gizmo_geometry import (
    collective_handle_layout, handle_layout,
)

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Gizmo layout', 'KanvasNodeTree')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        settings = area.spaces.active.edit_tree.kanvas_settings
        image = settings.images.add()
        image.item_type = 'IMAGE'
        image.image_data = bpy.data.images.new('Gizmo image', 300, 200)
        image.location = (80, -30)
        image.rotation = 24
        image.shear_xy = (0.18, -0.12)
        image.is_selected = True
        settings.active_image_index = 0
        helper = KanvasInteractionHelpers()
        view = region.view2d
        pixel = abs(view.region_to_view(1, 1)[0] - view.region_to_view(0, 0)[0])
        size = settings.gizmo_size * pixel
        corners, edges, stem, rotate = handle_layout(
            image.location, 300, 200, image.shear_xy, image.rotation, size)
        for index, point in enumerate(corners + edges + [rotate]):
            assert helper._get_gizmo_under_mouse(bpy.context, point) == index, index
        assert helper._get_gizmo_under_mouse(bpy.context, stem) == 6

        other = settings.images.add()
        other.item_type = 'IMAGE'
        other.image_data = bpy.data.images.new('Gizmo image 2', 100, 100)
        other.location = (600, 0)
        other.is_selected = True
        from k_tools_kanvas.utils.gpu.gpu_common import get_collective_bounding_box
        bounds = get_collective_bounding_box([
            (item.location, item.scale_xy, item.scale_master,
             item.shear_xy, item.rotation,
             item.image_data.size[0], item.image_data.size[1])
            for item in (image, other)
        ])
        group_corners, _, group_rotate = collective_handle_layout(bounds, size)
        for index, point in enumerate(group_corners + [group_rotate]):
            expected = index if index < 4 else 8
            assert helper._get_gizmo_under_mouse(bpy.context, point) == expected, index

        # Exercise the built-in shaders used by the filled handles and stem.
        from k_tools_kanvas.utils.gpu.gpu_image import (
            _draw_rotation_stem, _draw_transform_handle,
        )
        if hasattr(gpu, 'init'):
            gpu.init()
            offscreen = gpu.types.GPUOffScreen(64, 64)
            try:
                with offscreen.bind():
                    gpu.state.blend_set('ALPHA')
                    _draw_transform_handle((0, 0), 0.35, (0, 0.8, 1, 1), 0.02)
                    _draw_transform_handle((0.5, 0), 0.35,
                                           (0.06, 0.3, 0.16, 1), 0.02,
                                           fill=(0.36, 1, 0.6, 1),
                                           round_handle=True)
                    _draw_rotation_stem((0, 0), (0, 0.5), (0, 0.8, 1, 1))
            finally:
                offscreen.free()
        print('GIZMO LAYOUT PASS')
finally:
    addon.unregister()
