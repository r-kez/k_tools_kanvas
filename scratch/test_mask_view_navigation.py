"""Check that paint navigation changes Blender's real View2D coordinates."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_mask import KANVAS_OT_PaintImageMask


class NavigationHarness:
    _window_region = KANVAS_OT_PaintImageMask._window_region
    _pan_by = KANVAS_OT_PaintImageMask._pan_by
    _zoom_view = KANVAS_OT_PaintImageMask._zoom_view


addon.register()
try:
    area = max(bpy.context.screen.areas, key=lambda value: value.width * value.height)
    area.type = 'NODE_EDITOR'
    region = next(part for part in area.regions if part.type == 'WINDOW')
    navigation = NavigationHarness()
    navigation._area = area
    view = region.view2d
    left_before = view.region_to_view(0, 0)[0]
    navigation._pan_by(bpy.context, 30, 10)
    left_after = view.region_to_view(0, 0)[0]
    assert left_after < left_before, (left_before, left_after)

    width_before = view.region_to_view(region.width, 0)[0] - left_after
    navigation._zoom_view(bpy.context, -1)
    width_zoomed_out = view.region_to_view(region.width, 0)[0] - view.region_to_view(0, 0)[0]
    assert width_zoomed_out > width_before, (width_before, width_zoomed_out)
    navigation._zoom_view(bpy.context, 1)
    width_restored = view.region_to_view(region.width, 0)[0] - view.region_to_view(0, 0)[0]
    assert abs(width_restored - width_before) < 0.05, (width_before, width_restored)
    print('MASK_VIEW2D_NAVIGATION_OK')
finally:
    addon.unregister()
