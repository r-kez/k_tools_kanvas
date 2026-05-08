import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader

def rotate_point(point, center, angle_deg):
    angle_rad = math.radians(angle_deg)
    px, py = point
    cx, cy = center
    
    qx = cx + math.cos(angle_rad) * (px - cx) - math.sin(angle_rad) * (py - cy)
    qy = cy + math.sin(angle_rad) * (px - cx) + math.cos(angle_rad) * (py - cy)
    return qx, qy

class KanvasTexture:
    """Manages the GPU texture for a single Blender Image"""
    def __init__(self, image: bpy.types.Image):
        self.image_name = image.name
        self.texture = None
        self.update(image)

    def update(self, image: bpy.types.Image):
        """Upload image to GPU if not already there"""
        if not self.texture:
            self.texture = gpu.texture.from_image(image)
    
# Custom Shader for Color Management (sRGB to Linear)
vertex_shader = """
    uniform mat4 ModelViewProjectionMatrix;
    in vec2 pos;
    in vec2 texCoord;
    out vec2 uv;
    void main() {
        uv = texCoord;
        gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0);
    }
"""

fragment_shader = """
    uniform sampler2D image;
    uniform vec4 color;
    uniform int use_correction;
    in vec2 uv;
    out vec4 fragColor;
    
    // Precise sRGB to Linear conversion
    vec3 srgb_to_linear(vec3 c) {
        vec3 b = lessThanEqual(c, vec3(0.04045));
        vec3 c1 = c / 12.92;
        vec3 c2 = pow((c + 0.055) / 1.055, vec3(2.4));
        return mix(c2, c1, b);
    }

    void main() {
        vec4 tex_color = texture(image, uv);
        
        vec3 rgb = tex_color.rgb;
        if (use_correction != 0) {
            rgb = srgb_to_linear(rgb);
        }
        
        // Apply tint (color.rgb) and alpha (color.a * tex_color.a)
        fragColor = vec4(rgb * color.rgb, tex_color.a * color.a);
    }
"""

_kanvas_shader = None

def get_kanvas_shader():
    global _kanvas_shader
    if _kanvas_shader is None:
        import gpu
        try:
            # Try to find the correct Info class (it changed names in some versions)
            info_class = None
            for name in ["GPUShaderInfo", "GPUShaderCreateInfo", "GPU_ShaderInfo"]:
                if hasattr(gpu.types, name):
                    info_class = getattr(gpu.types, name)
                    break
            
            if info_class:
                info = info_class()
                info.vertex_source(vertex_shader)
                info.fragment_source(fragment_shader)
                
                # Register Attributes (Inputs to Vertex Shader)
                info.vertex_in(0, 'VEC2', "pos")
                info.vertex_in(1, 'VEC2', "texCoord")
                
                # Register Interface (Vertex to Fragment)
                if hasattr(info, "interstage_variable"): # Blender 4.1+
                    info.interstage_variable('VEC2', "uv")
                
                # Standard samplers/uniforms
                try:
                    # Try 3 arguments first (Newer Blender versions)
                    info.sampler("image", '2D', 'COLOR')
                except:
                    try:
                        # Try 2 arguments (Older 4.0 versions)
                        info.sampler("image", '2D')
                    except:
                        pass
                
                info.uniform_float("color", 'VEC4')
                info.uniform_float("ModelViewProjectionMatrix", 'MAT4')
                info.uniform_int("use_correction", 'INT')
                
                _kanvas_shader = gpu.shader.create_from_info(info)
            else:
                # Fallback to builtin if we can't find the info class
                _kanvas_shader = gpu.shader.from_builtin('IMAGE')
                
        except Exception as e:
            print(f"Kanvas Shader Error: {e}")
            _kanvas_shader = gpu.shader.from_builtin('IMAGE')
            
    return _kanvas_shader

class KanvasTexture:
    """Manages the GPU texture for a single Blender Image"""
    def __init__(self, image: bpy.types.Image):
        self.image_name = image.name
        self.texture = None
        self.update(image)

    def update(self, image: bpy.types.Image):
        """Upload image to GPU if not already there"""
        if not self.texture:
            self.texture = gpu.texture.from_image(image)
    
    def draw(self, location, scale, rotation, opacity, color_tint, use_correction):
        """Draw the texture centered and rotated at the specified location"""
        if not self.texture:
            return

        w = self.texture.width * scale
        h = self.texture.height * scale
        
        # Base bounds (Centered)
        pts = [
            (location[0] - w/2, location[1] - h/2),
            (location[0] + w/2, location[1] - h/2),
            (location[0] + w/2, location[1] + h/2),
            (location[0] - w/2, location[1] + h/2)
        ]

        # Apply rotation
        rotated_pts = [rotate_point(p, location, rotation) for p in pts]

        shader = get_kanvas_shader()
        
        # --- MVP MATRIX INJECTION ---
        # Capture current Node Editor view transformation (Zoom/Pan)
        matrix = gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix()
        
        batch = batch_for_shader(
            shader, 'TRI_FAN',
            {
                "pos": rotated_pts,
                "texCoord": [(0, 0), (1, 0), (1, 1), (0, 1)],
            },
        )

        gpu.state.blend_set('ALPHA')
        shader.bind()
        
        # Mandatory: Send current Viewport Matrix to the custom shader
        shader.uniform_matrix("ModelViewProjectionMatrix", matrix)
        
        shader.uniform_sampler("image", self.texture)
        
        # Send dynamic properties
        final_color = (color_tint[0], color_tint[1], color_tint[2], opacity)
        shader.uniform_float("color", final_color)
        shader.uniform_int("use_correction", int(use_correction))

        batch.draw(shader)
        gpu.state.blend_set('NONE')

    def draw_outline(self, location, scale, rotation):
        """Draw a selection border around the image"""
        if not self.texture:
            return

        prefs = get_prefs()
        w = self.texture.width * scale
        h = self.texture.height * scale
        
        pts = [
            (location[0] - w/2, location[1] - h/2),
            (location[0] + w/2, location[1] - h/2),
            (location[0] + w/2, location[1] + h/2),
            (location[0] - w/2, location[1] + h/2)
        ]
        rotated_pts = [rotate_point(p, location, rotation) for p in pts]

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(
            shader, 'LINE_LOOP',
            {"pos": rotated_pts},
        )
        shader.bind()
        shader.uniform_float("color", prefs.color_selection)
        gpu.state.line_width_set(prefs.selection_thickness)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)

    def draw_gizmos(self, location, scale, rotation, gizmo_size_px):
        """Draw interactive handles for scaling"""
        if not self.texture:
            return

        w = self.texture.width * scale
        h = self.texture.height * scale
        x_mid, y_mid = location[0], location[1]

        # 8 Handle positions (Pre-rotation)
        handles = [
            (location[0] - w/2, location[1] - h/2), (x_mid, location[1] - h/2), (location[0] + w/2, location[1] - h/2),
            (location[0] - w/2, y_mid),                                         (location[0] + w/2, y_mid),
            (location[0] - w/2, location[1] + h/2), (x_mid, location[1] + h/2), (location[0] + w/2, location[1] + h/2)
        ]

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        s = gizmo_size_px
        
        for h_pos in handles:
            # Rotate the handle center point
            rh_pos = rotate_point(h_pos, location, rotation)
            
            # The handle square itself should also rotate or stay screen-aligned?
            # To be simple and robust, let's rotate the handle vertices too.
            h_pts = [
                (rh_pos[0] - s/2, rh_pos[1] - s/2),
                (rh_pos[0] + s/2, rh_pos[1] - s/2),
                (rh_pos[0] + s/2, rh_pos[1] + s/2),
                (rh_pos[0] - s/2, rh_pos[1] + s/2)
            ]
            # Optionally rotate handle squares around their own center to align with image
            rh_pts = [rotate_point(p, rh_pos, rotation) for p in h_pts]

            batch = batch_for_shader(shader, 'TRI_FAN', {"pos": rh_pts})
            shader.bind()
            shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
            batch.draw(shader)
            
            outline_batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": rh_pts})
            shader.uniform_float("color", (0.0, 0.0, 0.0, 1.0))
            outline_batch.draw(shader)

def get_prefs():
    # The name of the addon in the preferences is always the name of the top-level package.
    # We climb up the package parts to find the one registered in Blender.
    pkg_parts = __package__.split('.')
    for i in range(len(pkg_parts), 0, -1):
        test_name = ".".join(pkg_parts[:i])
        if test_name in bpy.context.preferences.addons:
            return bpy.context.preferences.addons[test_name].preferences
            
    # Fuzzy fallback: search for any addon key containing our ID
    for addon_name in bpy.context.preferences.addons.keys():
        if 'k_toolskanvas' in addon_name or 'k_tools_kanvas' in addon_name:
            return bpy.context.preferences.addons[addon_name].preferences
            
    return None

# Global cache for textures
_texture_cache = {}

def get_kanvas_texture(image: bpy.types.Image):
    if image.name not in _texture_cache:
        _texture_cache[image.name] = KanvasTexture(image)
    return _texture_cache[image.name]

def draw_axes(size=10000.0):
    """Draw X and Y axes for orientation"""
    prefs = get_prefs()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # X Axis
    batch_x = batch_for_shader(
        shader, 'LINES',
        {"pos": [(-size, 0), (size, 0)]}
    )
    shader.bind()
    shader.uniform_float("color", prefs.color_x_axis)
    batch_x.draw(shader)
    
    # Y Axis
    batch_y = batch_for_shader(
        shader, 'LINES',
        {"pos": [(0, -size), (0, size)]}
    )
    shader.uniform_float("color", prefs.color_y_axis)
    batch_y.draw(shader)

def draw_callback_px(self, context):
    # Fallback to bpy.context if the provided context is restricted
    if not hasattr(context, "scene"):
        context = bpy.context
    
    # If it's still restricted, skip drawing
    if not hasattr(context, "scene") or context.scene is None:
        return

    # Only draw if the current node tree is a KanvasNodeTree
    if not hasattr(context, "space_data") or not hasattr(context.space_data, "edit_tree"):
        return
    if context.space_data.edit_tree is None or context.space_data.edit_tree.bl_idname != 'KanvasNodeTree':
        return

    settings = context.scene.kanvas_settings
    
    # Draw Axes first (below images)
    if settings.show_debug_grid:
        draw_axes()

    if not settings.show_all:
        return
    
    # We are in POST_VIEW, coordinates are in 2D space of the Node Editor
    for img_item in context.scene.kanvas_settings.images:
        if not img_item.show_in_editor or not img_item.image_data:
            continue
            
        tex = get_kanvas_texture(img_item.image_data)
        tex.draw(
            img_item.location, 
            img_item.scale, 
            img_item.rotation, 
            img_item.opacity, 
            img_item.color_tint,
            img_item.use_color_correction
        )
        
        if img_item.is_selected:
            tex.draw_outline(img_item.location, img_item.scale, img_item.rotation)
            if settings.show_gizmos:
                tex.draw_gizmos(img_item.location, img_item.scale, img_item.rotation, settings.gizmo_size)

class KanvasDrawHandler:
    _handler = None
    
    @classmethod
    def add_handler(cls):
        if cls._handler is None:
            # Add to Node Editor
            cls._handler = bpy.types.SpaceNodeEditor.draw_handler_add(
                draw_callback_px, (None, bpy.context), 'WINDOW', 'POST_VIEW'
            )

    @classmethod
    def remove_handler(cls):
        if cls._handler is not None:
            bpy.types.SpaceNodeEditor.draw_handler_remove(cls._handler, 'WINDOW')
            cls._handler = None

def register():
    KanvasDrawHandler.add_handler()

def unregister():
    KanvasDrawHandler.remove_handler()
    _texture_cache.clear()
