"""GPU side of shape gradients: the shader and the ramp textures.

The shader reads the canvas position of each pixel and turns it into a place on the
ramp (see `shape_gradient.gradient_t`). A per-vertex `alpha` carries the anti-aliasing
fringe, so the soft edge has the gradient's colors too. If the shader cannot be built
(old driver, no GPU), `get_gradient_shader` returns None and shapes fall back to a flat
fill in the gradient's average color.
"""

import gpu

from ..shape_gradient import RAMP_SIZE

_shader = None
_shader_failed = False
_ramps = {}

_KINDS = {'LINEAR': 0.0, 'RADIAL': 1.0}
_SPREADS = {'PAD': 0.0, 'REFLECT': 1.0, 'REPEAT': 2.0}


def get_gradient_shader():
    global _shader, _shader_failed
    if _shader_failed:
        return None
    if _shader is not None:
        return _shader
    try:
        interface = gpu.types.GPUStageInterfaceInfo('kanvas_gradient_iface')
        interface.smooth('VEC2', 'canvas')
        interface.smooth('FLOAT', 'edge')
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', 'ModelViewProjectionMatrix')
        info.push_constant('VEC4', 'points')   # start.xy, end.xy on the canvas
        info.push_constant('VEC4', 'params')   # kind, spread, opacity, unused
        info.sampler(0, 'FLOAT_2D', 'ramp')
        info.vertex_in(0, 'VEC2', 'pos')
        info.vertex_in(1, 'FLOAT', 'alpha')
        info.vertex_out(interface)
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source(
            'void main() {'
            '  canvas = pos; edge = alpha;'
            '  gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0);'
            '}')
        info.fragment_source(
            'void main() {'
            '  vec2 d = points.zw - points.xy;'
            '  vec2 p = canvas - points.xy;'
            '  float t = params.x > 0.5 ? length(p) / max(length(d), 1e-6)'
            '                           : dot(p, d) / max(dot(d, d), 1e-12);'
            '  if (params.y > 1.5) { t = fract(t); }'
            '  else if (params.y > 0.5) { t = mod(abs(t), 2.0); if (t > 1.0) { t = 2.0 - t; } }'
            '  else { t = clamp(t, 0.0, 1.0); }'
            f'  float u = (t * {RAMP_SIZE - 1}.0 + 0.5) / {RAMP_SIZE}.0;'
            '  vec4 c = texture(ramp, vec2(u, 0.5));'
            '  fragColor = vec4(c.rgb, c.a * params.z * edge);'
            '}')
        _shader = gpu.shader.create_from_info(info)
        return _shader
    except Exception as exc:
        if 'gpu.init' in str(exc) or 'initialized' in str(exc):
            return None   # no GPU yet (background run): try again once there is one
        print(f'Kanvas: gradient shader failed ({exc}); gradients draw as a flat color')
        _shader_failed = True
        return None


def ramp_texture(key, values):
    """Ramp texture of RAMP_SIZE sampled colors, shared by every shape whose ramp has
    the same `key` (`shape_gradient.ramp_key`)."""
    texture = _ramps.get(key)
    if texture is None:
        if len(_ramps) > 256:
            _ramps.clear()
        texture = gpu.types.GPUTexture(
            (RAMP_SIZE, 1), format='RGBA32F',
            data=gpu.types.Buffer('FLOAT', RAMP_SIZE * 4, list(values)))
        texture.filter_mode(True)
        _ramps[key] = texture
    return texture


def draw_gradient(shader, batch, gradient):
    """Draw a batch (pos + alpha) with the gradient (kind, spread, start, end, ramp
    key, ramp samples, opacity) from `shape_draw_geometry`."""
    kind, spread, start, end, key, values, opacity = gradient
    shader.bind()
    shader.uniform_float('points', (start[0], start[1], end[0], end[1]))
    shader.uniform_float('params', (_KINDS[kind], _SPREADS[spread], opacity, 0.0))
    shader.uniform_sampler('ramp', ramp_texture(key, values))
    batch.draw(shader)
