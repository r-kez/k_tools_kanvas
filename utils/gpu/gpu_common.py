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

# Per-draw-pass memo. Draw callbacks call get_prefs() hundreds of times per
# redraw (once per text run); resolving it once per pass keeps redraws cheap.
_pass_cache = None


def begin_draw_pass():
    global _pass_cache
    _pass_cache = {}


def end_draw_pass():
    global _pass_cache
    _pass_cache = None


def pass_cache():
    """Dict valid only during a draw pass, or None outside of one."""
    return _pass_cache


def get_prefs():
    """Return addon preferences, or None if the addon is not found."""
    cache = _pass_cache
    if cache is None:
        return _lookup_prefs()
    if 'prefs' not in cache:
        cache['prefs'] = _lookup_prefs()
    return cache['prefs']


def _lookup_prefs():
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

# ---------------------------------------------------------------------------
# Shader management
# ---------------------------------------------------------------------------

_custom_shader = None

# FIX: use a module-level integer counter instead of time.time() % 10000.
#
# The old approach had two problems:
#   1. If the addon was reloaded twice within the same second, both reloads
#      produced the same unique_id, so the second GPUStageInterfaceInfo()
#      call tried to register a name already in Blender's internal registry
#      and crashed with "Interface name already used".
#   2. Every reload leaked an interface-name slot in the GPU driver's registry
#      because registered interface names are never freed during a session.
#      With time.time() % 10000 there are only 10 000 possible slots, so after
#      10 000 reloads (trivial during active development) the registry wraps
#      and collides. A monotonically increasing counter avoids the wrap and
#      makes each name unique for the lifetime of the process.
_shader_iface_counter = 0

# The value-check code (grayscale / posterize) is optional. If a driver rejects
# the extended shader, it is rebuilt without it so images are always drawn.
_value_view_supported = True


def shader_supports_value_view():
    return _value_view_supported and _custom_shader is not None


def value_view_uniforms(item):
    """(mode, levels) for the shader: 0 normal, 1 grayscale, 2 posterized."""
    levels = item.value_levels
    if levels >= 2:
        return 2.0, float(levels)
    return (1.0 if item.value_gray else 0.0), 0.0


def get_kanvas_shader():
    global _custom_shader, _shader_iface_counter, _value_view_supported
    with_value_view = _value_view_supported

    if _custom_shader is not None:
        try:
            # GPUShader objects become invalid after a context loss or addon
            # reload. Accessing .program raises an exception on a dead shader.
            if hasattr(_custom_shader, "program"):
                return _custom_shader
        except Exception:
            _custom_shader = None

    # Increment BEFORE building so that every call that reaches this point
    # gets a name that has never been used in this process session.
    _shader_iface_counter += 1
    iface_name = f"kanvas_iface_{_shader_iface_counter}"

    try:
        vert_out = gpu.types.GPUStageInterfaceInfo(iface_name)
        vert_out.smooth('VEC2', "v_TexCoord")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.push_constant('VEC4', "color")
        shader_info.push_constant('FLOAT', "brightness")
        shader_info.push_constant('FLOAT', "contrast")
        shader_info.push_constant('FLOAT', "saturation")
        shader_info.push_constant('FLOAT', "use_color_correction")
        shader_info.push_constant('FLOAT', "mask_enabled")
        shader_info.push_constant('FLOAT', "markup_enabled")
        if with_value_view:
            shader_info.push_constant('FLOAT', "value_mode")
            shader_info.push_constant('FLOAT', "value_levels")

        shader_info.sampler(0, 'FLOAT_2D', "image")
        shader_info.sampler(1, 'FLOAT_2D', "mask_image")
        shader_info.sampler(2, 'FLOAT_2D', "markup_image")

        shader_info.vertex_in(0, 'VEC2', "pos")
        shader_info.vertex_in(1, 'VEC2', "texCoord")

        shader_info.vertex_out(vert_out)

        shader_info.fragment_out(0, 'VEC4', "fragColor")

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
            + (
            "  if (value_mode > 0.5) {"
            "    float g = dot(c, vec3(0.2126, 0.7152, 0.0722));"
            # Black and White weighs the colors in linear light, as the eye does; the
            # board encodes to gamma itself, the 3D View does it later.
            "    if (value_mode < 1.5 && use_color_correction > 0.5) {"
            "      g = pow(dot(pow(c, vec3(2.2)), vec3(0.2126, 0.7152, 0.0722)), 1.0 / 2.2);"
            "    }"
            "    if (value_mode > 1.5) {"
            "      float steps = max(value_levels, 2.0);"
            "      g = floor(clamp(g, 0.0, 0.9999) * steps) / (steps - 1.0);"
            "    }"
            "    c = vec3(clamp(g, 0.0, 1.0));"
            "  }" if with_value_view else "") +
            "  float mask_alpha = mask_enabled > 0.5 ? texture(mask_image, v_TexCoord).r : 1.0;"
            "  if (markup_enabled > 0.5) {"
            "    vec4 markup = texture(markup_image, v_TexCoord);"
            "    c = c * (1.0 - markup.a) + markup.rgb;"
            "  }"
            "  fragColor = vec4(c, tex.a * mask_alpha) * color;"
            "}"
        )

        _custom_shader = gpu.shader.create_from_info(shader_info)
        return _custom_shader

    except Exception as e:
        if with_value_view:
            print(f"Kanvas: value-check shader failed ({e}); using the basic shader")
            _value_view_supported = False
            _custom_shader = None
            return get_kanvas_shader()
        print(f"Kanvas: CRITICAL Error creating shader: {e}")
        return None

def clear_kanvas_shader():
    global _custom_shader
    _custom_shader = None
    # Note: _shader_iface_counter is intentionally NOT reset here.
    # It must keep incrementing across reloads so interface names
    # remain unique for the entire lifetime of the Blender process.

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
