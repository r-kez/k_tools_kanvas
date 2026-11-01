"""Check that the overlay reads the native Node Editor annotation data."""
import sys
from pathlib import Path
from math import isclose

import bpy
import gpu

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_annotation import (
    draw_canvas_annotations, visible_canvas_strokes,
)


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Annotation overlay test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    space = area.spaces.active
    annotation = bpy.data.annotations.new('Native annotation test')
    tree.annotation = annotation
    layer = annotation.layers.new('Pink', set_active=True)
    layer.color = (1.0, 0.0, 0.3)
    layer.annotation_opacity = 0.8
    layer.thickness = 4
    frame = layer.frames.new(1)
    if not hasattr(frame.strokes, 'new'):
        print('ANNOTATION OVERLAY DATA SKIPPED: Blender does not expose stroke creation')
        raise SystemExit(0)
    stroke = frame.strokes.new()
    stroke.points.add(2)
    stroke.points[0].co = (10, 20, 0)
    stroke.points[1].co = (30, 40, 0)
    if hasattr(stroke, 'display_mode'):
        stroke.display_mode = '2DSPACE'

    result = list(visible_canvas_strokes(space, 1))
    assert len(result) == 1, result
    points, color, width = result[0]
    assert points == ((10, 20, 0), (30, 40, 0)), points
    assert all(isclose(a, b, abs_tol=1e-6)
               for a, b in zip(color, (1, 0, 0.3, 0.8))), color
    assert width == 4, width
    gpu.init()
    offscreen = gpu.types.GPUOffScreen(64, 64)
    try:
        with offscreen.bind():
            gpu.state.viewport_set(0, 0, 64, 64)
            draw_canvas_annotations(space, 1)
    finally:
        offscreen.free()
    layer.annotation_hide = True
    assert not list(visible_canvas_strokes(space, 1))
    layer.annotation_hide = False
    space.show_annotation = False
    assert not list(visible_canvas_strokes(space, 1))
    print('ANNOTATION OVERLAY DATA PASS')
finally:
    addon.unregister()
