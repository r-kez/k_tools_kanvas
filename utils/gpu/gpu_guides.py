import gpu
from gpu_extras.batch import batch_for_shader

def draw_snap_guides(settings, size=1000000.0, view_bounds=None):
    """Draw green lines where snapping is active."""
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()
    
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
    shader.uniform_float("lineWidth", 1.5)
    shader.uniform_float("color", (0.0, 1.0, 0.4, 0.85)) # Bright Green

    if view_bounds:
        min_x, min_y, max_x, max_y = view_bounds
        pad_x = (max_x - min_x) * 0.1
        pad_y = (max_y - min_y) * 0.1
        x0, x1 = min_x - pad_x, max_x + pad_x
        y0, y1 = min_y - pad_y, max_y + pad_y
    else:
        x0, x1 = -size, size
        y0, y1 = -size, size

    if settings.show_snap_viz_x:
        x = settings.snap_viz_x
        batch = batch_for_shader(shader, 'LINES', {"pos": [(x, y0), (x, y1)]})
        batch.draw(shader)
        
    if settings.show_snap_viz_y:
        y = settings.snap_viz_y
        batch = batch_for_shader(shader, 'LINES', {"pos": [(x0, y), (x1, y)]})
        batch.draw(shader)
        
    gpu.state.blend_set('NONE')
