import gpu
from gpu_extras.batch import batch_for_shader

def draw_selection_box(settings):
    """Draw a semi-transparent rectangle for box selection."""
    if not settings.show_box_sel:
        return

    start = settings.box_sel_start
    end = settings.box_sel_end
    
    min_x, max_x = sorted([start[0], end[0]])
    min_y, max_y = sorted([start[1], end[1]])
    
    # Coordinates for the rectangle
    coords = [
        (min_x, min_y), (max_x, min_y), 
        (max_x, max_y), (min_x, max_y)
    ]
    
    # Triangles for the filled area
    indices_fill = [(0, 1, 2), (2, 3, 0)]
    
    # Lines for the outline
    indices_line = [(0, 1), (1, 2), (2, 3), (3, 0)]

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    
    # 1. Draw Fill (Semi-transparent blue)
    batch_fill = batch_for_shader(shader, 'TRIS', {"pos": coords}, indices=indices_fill)
    shader.bind()
    shader.uniform_float("color", (0.2, 0.5, 1.0, 0.15))
    batch_fill.draw(shader)
    
    # 2. Draw Outline (Solid blue)
    batch_line = batch_for_shader(shader, 'LINES', {"pos": coords}, indices=indices_line)
    shader.uniform_float("color", (0.4, 0.7, 1.0, 0.8))
    gpu.state.line_width_set(1.0)
    batch_line.draw(shader)
    
    gpu.state.blend_set('NONE')
