"""Exercise the optional open arrow in Blender 5.3, including GPU drawing."""

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
import gpu
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.arrow_geometry import hit_arrow, rounded_head_arms
from k_tools_kanvas.utils import arrow_geometry
from k_tools_kanvas.utils.gpu import gpu_common
from k_tools_kanvas.preferences import KanvasPreferences
from k_tools_kanvas.utils.gpu.gpu_arrow import (
    _antialias_fringe, _filled_head_dimensions, _rounded_stroke,
    draw_arrow_labels, draw_arrows,
)


addon.register()
try:
    assert KanvasPreferences.bl_rna.properties['arrow_style'].default == 'SOLID'
    prefs = SimpleNamespace(arrow_style='SOLID',
                            color_arrow_endpoint_handles=(1, 1, 1, 1),
                            color_arrow_curve_handle=(1, 1, 1, 1),
                            visual_theme='CLASSIC')
    gpu_common.get_prefs = lambda: prefs
    arrow_geometry.get_prefs = lambda: prefs
    tree = bpy.data.node_groups.new('Rounded arrow test', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    arrow = settings.arrows.add()
    arrow.start = (20, 100)
    arrow.end = (220, 100)
    arrow.thickness = 12
    arrow.label = 'Zoom label'
    assert hit_arrow(settings, (181, 115), 1.0) == (None, None)

    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = tree
    prefs.arrow_style = 'ROUNDED'
    with bpy.context.temp_override(area=area, space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_arrow('EXEC_DEFAULT') == {'FINISHED'}
    created = settings.arrows[-1]
    assert created.thickness == 8.0
    settings.arrows.remove(len(settings.arrows) - 1)

    arms = rounded_head_arms([tuple(arrow.start), tuple(arrow.end)], 12)
    assert arms == ((142.0, 130.0), (142.0, 70.0)), arms
    assert all(math.isclose(actual, expected) for actual, expected in zip(
        _filled_head_dimensions(12, 200), (6.0, 18.0, 16.8)))
    assert hit_arrow(settings, (181, 115), 1.0) == (0, 'body')

    geometry, contour = _rounded_stroke([(20, 100), (120, 100), (220, 100)], 6)
    assert len(geometry) > 50 and len(contour) > 15
    assert all(math.isfinite(value) for point in geometry for value in point)
    fringe, colors = _antialias_fringe(contour, 1.0, (0, 0, 0, 1))
    assert fringe and len(fringe) == len(colors)

    gpu.init()
    offscreen = gpu.types.GPUOffScreen(256, 256)
    try:
        with offscreen.bind():
            gpu.matrix.push_projection()
            gpu.matrix.load_projection_matrix(Matrix((
                (2 / 256, 0, 0, -1),
                (0, 2 / 256, 0, -1),
                (0, 0, 1, 0),
                (0, 0, 0, 1),
            )))
            for style in ('SOLID', 'ROUNDED'):
                prefs.arrow_style = style
                for pixel_size in (0.25, 1.0, 8.0):
                    draw_arrows(settings, pixel_size)
                    view = SimpleNamespace(
                        region_to_view=lambda x, y: (x * pixel_size, y * pixel_size),
                        view_to_region=lambda x, y, clip=False:
                            (x / pixel_size, y / pixel_size),
                    )
                    draw_arrow_labels(settings, SimpleNamespace(
                        view2d=view, width=256, height=256))
            gpu.matrix.pop_projection()
    finally:
        offscreen.free()
    print('ROUNDED ARROW PASS')
finally:
    addon.unregister()
