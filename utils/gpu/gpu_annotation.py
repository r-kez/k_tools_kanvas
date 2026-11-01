"""Draw saved native Node Editor annotations over the Kanvas canvas."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader


def visible_canvas_strokes(space, frame_number):
    """Yield view-space strokes from the same annotation datablock Blender draws."""
    if not space.show_annotation or not space.overlay.show_overlays:
        return
    tree = space.node_tree
    annotation = tree.annotation if tree else None
    if annotation is None:
        return

    for layer in annotation.layers:
        if layer.annotation_hide or layer.annotation_opacity <= 0:
            continue
        if layer.lock_frame:
            frame = layer.active_frame
        else:
            frame = max((item for item in layer.frames
                         if item.frame_number <= frame_number),
                        key=lambda item: item.frame_number, default=None)
        if frame is None:
            continue

        color = (*layer.color, layer.annotation_opacity)
        width = max(1.0, float(layer.thickness))
        for stroke in frame.strokes:
            # In Blender 5.1 display_mode is not exposed by Python. Node Editor
            # Annotate creates canvas-space strokes; 5.2+ lets us check them.
            if getattr(stroke, 'display_mode', '2DSPACE') != '2DSPACE':
                continue
            points = tuple((point.co[0], point.co[1], 0.0)
                           for point in stroke.points)
            if points:
                yield points, color, width


def draw_canvas_annotations(space, frame_number):
    """Redraw completed native strokes after the images; Blender draws the live buffer."""
    strokes = list(visible_canvas_strokes(space, frame_number))
    if not strokes:
        return

    line_shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    point_shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()
    pixel_size = bpy.context.preferences.system.pixel_size
    previous_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        for points, color, width in strokes:
            if len(points) == 1:
                point_size = (width + 2.0) * pixel_size
                gpu.state.point_size_set(point_size)
                point_shader.bind()
                point_shader.uniform_float('color', color)
                point_shader.uniform_float('size', point_size)
                batch_for_shader(point_shader, 'POINTS', {'pos': points}).draw(point_shader)
            else:
                line_shader.bind()
                line_shader.uniform_float('color', color)
                line_shader.uniform_float('lineWidth', width * pixel_size)
                line_shader.uniform_float('viewportSize', (viewport[2], viewport[3]))
                batch_for_shader(line_shader, 'LINE_STRIP', {'pos': points}).draw(line_shader)
    finally:
        gpu.state.point_size_set(1.0)
        gpu.state.blend_set(previous_blend)
