import gpu
from gpu_extras.batch import batch_for_shader

def draw_kanvas_frame(node, view_pixel_size):
    """Draw a semi-transparent box for a NodeFrame."""
    loc = node.location
    w = node.width
    h = node.height
    
    color = (0.2, 0.2, 0.2, 0.3)
    if node.use_custom_color:
        c = node.color
        color = (c[0], c[1], c[2], 0.3)

    v0 = (loc[0], loc[1])
    v1 = (loc[0] + w, loc[1])
    v2 = (loc[0] + w, loc[1] - h)
    v3 = (loc[0], loc[1] - h)
    
    vertices = [v0, v1, v2, v0, v2, v3]
    
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    
    # Border
    border_vertices = [v0, v1, v1, v2, v2, v3, v3, v0]
    batch_border = batch_for_shader(shader, 'LINES', {"pos": border_vertices})
    shader.uniform_float("color", (color[0], color[1], color[2], 0.8))
    batch_border.draw(shader)
    
    gpu.state.blend_set('NONE')
