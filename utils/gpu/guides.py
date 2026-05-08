import gpu
from gpu_extras.batch import batch_for_shader

def draw_snap_guides(settings, size=10000.0):
    """Draw green lines where snapping is active."""
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()
    
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
    shader.uniform_float("lineWidth", 1.5)
    shader.uniform_float("color", (0.0, 1.0, 0.4, 0.8)) # Bright Green

    if settings.show_snap_viz_x:
        x = settings.snap_viz_x
        batch = batch_for_shader(shader, 'LINES', {"pos": [(x, -size), (x, size)]})
        batch.draw(shader)
        
    if settings.show_snap_viz_y:
        y = settings.snap_viz_y
        batch = batch_for_shader(shader, 'LINES', {"pos": [(-size, y), (size, y)]})
        batch.draw(shader)
        
    gpu.state.blend_set('NONE')
