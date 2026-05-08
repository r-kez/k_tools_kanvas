import bpy
import gpu
import math
import os

def rotate_point(point, center, angle_deg):
    angle_rad = math.radians(angle_deg)
    px, py = point
    cx, cy = center
    qx = cx + math.cos(angle_rad) * (px - cx) - math.sin(angle_rad) * (py - cy)
    qy = cy + math.sin(angle_rad) * (px - cx) + math.cos(angle_rad) * (py - cy)
    return qx, qy

def get_prefs():
    """Return addon preferences, or None if the addon is not found."""
    pkg_parts = __package__.split('.')
    for i in range(len(pkg_parts), 0, -1):
        test_name = ".".join(pkg_parts[:i])
        if test_name in bpy.context.preferences.addons:
            return bpy.context.preferences.addons[test_name].preferences

    # Fuzzy fallback
    for addon_name in bpy.context.preferences.addons.keys():
        if 'k_toolskanvas' in addon_name or 'k_tools_kanvas' in addon_name:
            return bpy.context.preferences.addons[addon_name].preferences

    return None

_custom_shader = None

def get_kanvas_shader():
    global _custom_shader

    # FIX: In Blender 5.x, cached GPU objects become invalid after context loss
    # or addon reload. We validate strictly before reusing.
    if _custom_shader is not None:
        try:
            # GPUShader objects are fragile. If the shader is 'dead', 
            # accessing any property like .name or .program will raise an error.
            if hasattr(_custom_shader, "program"):
                return _custom_shader
        except Exception:
            _custom_shader = None

    # Use a unique interface name to avoid "Interface name already used" errors
    # during rapid addon reloads which can crash Blender.
    import time
    unique_id = int(time.time()) % 10000
    iface_name = f"kanvas_iface_{unique_id}"

    try:
        vert_out = gpu.types.GPUStageInterfaceInfo(iface_name)
        vert_out.smooth('VEC2', "v_TexCoord")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.push_constant('VEC4', "color")
        shader_info.push_constant('FLOAT', "brightness")
        shader_info.push_constant('FLOAT', "contrast")
        shader_info.push_constant('FLOAT', "saturation")
        shader_info.push_constant('FLOAT', "use_color_correction")

        shader_info.sampler(0, 'FLOAT_2D', "image")

        shader_info.vertex_in(0, 'VEC2', "pos")
        shader_info.vertex_in(1, 'VEC2', "texCoord")

        shader_info.vertex_out(vert_out)

        # Declare fragColor output
        shader_info.fragment_out(0, 'VEC4', "fragColor")

        # Declare MVP matrix push constant
        shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")

        shader_info.vertex_source(
            "void main() {"
            "  v_TexCoord = texCoord;"
            "  gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0);"
            "}"
        )

        shader_info.fragment_source(
            "void main() {"
            "  vec4 tex = texture(image, v_TexCoord);"
            "  vec3 c = tex.rgb;"
            "  c = max(c * brightness, vec3(0.0));"
            "  c = clamp((c - 0.5) * contrast + 0.5, 0.0, 1.0);"
            "  float gray = dot(c, vec3(0.2126, 0.7152, 0.0722));"
            "  c = clamp(mix(vec3(gray), c, saturation), 0.0, 1.0);"
            "  if (use_color_correction > 0.5) {"
                "    c = pow(c, vec3(1.0 / 2.2));"
            "  }"
            "  fragColor = vec4(c, tex.a) * color;"
            "}"
        )

        _custom_shader = gpu.shader.create_from_info(shader_info)
        return _custom_shader
    except Exception as e:
        print(f"Kanvas: CRITICAL Error creating shader: {e}")
        return None

def clear_kanvas_shader():
    global _custom_shader
    _custom_shader = None

def get_collective_bounding_box(data_list):
    """Calculates the AABB of all provided image data in view space."""
    all_points = []
    for loc, s_xy, s_m, shear, rot, w, h in data_list:
        fw = w * s_xy[0] * s_m
        fh = h * s_xy[1] * s_m

        pts = [(-fw/2, -fh/2), (fw/2, -fh/2), (fw/2, fh/2), (-fw/2, fh/2)]
        for p in pts:
            ps = (p[0] + p[1] * shear[0], p[1] + p[0] * shear[1])
            pf = rotate_point((ps[0] + loc[0], ps[1] + loc[1]), loc, rot)
            all_points.append(pf)

    if not all_points:
        return None

    min_x = min(p[0] for p in all_points)
    max_x = max(p[0] for p in all_points)
    min_y = min(p[1] for p in all_points)
    max_y = max(p[1] for p in all_points)

    return (min_x, min_y, max_x, max_y)