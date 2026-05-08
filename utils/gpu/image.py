import bpy
import gpu
import os
from gpu_extras.batch import batch_for_shader
from .common import rotate_point, get_prefs, get_kanvas_shader

# ---------------------------------------------------------------------------
# Icon management
# ---------------------------------------------------------------------------

_icon_cache: dict[str, gpu.types.GPUTexture] = {}

def get_icon_texture(name):
    if name in _icon_cache:
        return _icon_cache[name]

    addon_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    icon_path = os.path.join(addon_dir, "assets", "icons", f"{name}.png")

    if not os.path.exists(icon_path):
        return None

    try:
        img = bpy.data.images.load(icon_path, check_existing=True)
        img.colorspace_settings.name = 'Non-Color'
        tex = gpu.texture.from_image(img)
        _icon_cache[name] = tex
        return tex
    except Exception as e:
        print(f"Kanvas: Error loading icon {name}: {e}")
        return None

def draw_icon(texture, center, size, rotation=0, color=(1,1,1,1)):
    if not texture: return
    s = size
    pts = [(-s/2, -s/2), (s/2, -s/2), (s/2, s/2), (-s/2, s/2)]
    rotated_pts = [rotate_point(p, (0,0), rotation) for p in pts]
    final_pts = [(p[0] + center[0], p[1] + center[1]) for p in rotated_pts]

    shader = gpu.shader.from_builtin('IMAGE_COLOR')
    batch = batch_for_shader(
        shader, 'TRI_FAN',
        {"pos": final_pts, "texCoord": [(0, 0), (1, 0), (1, 1), (0, 1)]},
    )
    shader.bind()
    shader.uniform_sampler("image", texture)
    shader.uniform_float("color", color)
    batch.draw(shader)

# ---------------------------------------------------------------------------
# Texture wrapper
# ---------------------------------------------------------------------------

class KanvasTexture:
    def __init__(self, image: bpy.types.Image):
        self.image_name = image.name
        self.texture: gpu.types.GPUTexture | None = None
        # FIX: track the image's pixels_version (or a hash) so we only
        # rebuild the GPU texture when the pixel data actually changed,
        # instead of rebuilding every single frame.
        self._last_update_tag: int = -1
        self.update(image)

    def update(self, image: bpy.types.Image):
        # FIX: bpy.types.Image has an internal 'update_tag' counter that
        # increments whenever pixel data changes.
        current_tag = getattr(image, 'update_tag', None)

        if current_tag is None:
            current_tag = int(getattr(image, 'is_dirty', True))

        if self.texture is not None and current_tag == self._last_update_tag:
            return  # texture is still valid, skip rebuild

        try:
            # Ensure pixels are loaded in memory before creating GPU texture.
            # This prevents crashes if the image was just loaded or replaced.
            if image.size[0] > 0 and image.size[1] > 0:
                image.gl_load()
                self.texture = gpu.texture.from_image(image)
            else:
                self.texture = None
        except Exception as e:
            print(f"Kanvas: Error creating texture for {image.name}: {e}")
            self.texture = None

        self._last_update_tag = current_tag

    def draw(self, location, scale, shear, rotation, opacity, color_tint,
             brightness=1.0, contrast=1.0, saturation=1.0,
             flip_h=False, flip_v=False, use_color_correction=True):
        if not self.texture: return
        w = self.texture.width  * scale[0]
        h = self.texture.height * scale[1]
        pts = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
        sheared_pts = [(p[0] + p[1] * shear[0], p[1] + p[0] * shear[1]) for p in pts]
        final_pts = [rotate_point((p[0] + location[0], p[1] + location[1]), location, rotation) for p in sheared_pts]

        # Handle Flips via UVs
        u0, u1 = (1, 0) if flip_h else (0, 1)
        v0, v1 = (1, 0) if flip_v else (0, 1)
        tex_coords = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]

        shader = get_kanvas_shader()
        if not shader:
            return

        try:
            batch = batch_for_shader(
                shader, 'TRI_FAN',
                {"pos": final_pts, "texCoord": tex_coords},
            )
            
            gpu.state.blend_set('ALPHA')
            gpu.matrix.push()
            shader.bind()
            shader.uniform_sampler("image", self.texture)
            shader.uniform_float("color", (color_tint[0], color_tint[1], color_tint[2], opacity))
            shader.uniform_float("brightness", brightness)
            shader.uniform_float("contrast", contrast)
            shader.uniform_float("saturation", saturation)
            shader.uniform_float("use_color_correction", float(use_color_correction))
            
            batch.draw(shader)
            
            gpu.matrix.pop()
            gpu.state.blend_set('NONE')
        except Exception as e:
            print(f"Kanvas: Draw error: {e}")
            # If batch.draw or shader.bind failed, try to recover
            try: gpu.matrix.pop()
            except: pass

    def draw_outline(self, location, scale, shear, rotation):
        if not self.texture: return
        prefs = get_prefs()
        if not prefs: return
        w = self.texture.width  * scale[0]
        h = self.texture.height * scale[1]
        pts = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
        sheared_pts = [(p[0] + p[1] * shear[0], p[1] + p[0] * shear[1]) for p in pts]
        final_pts = [rotate_point((p[0] + location[0], p[1] + location[1]), location, rotation) for p in sheared_pts]
        line_pts = final_pts + [final_pts[0]]

        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        if not shader: return
        
        try:
            batch  = batch_for_shader(shader, 'LINE_STRIP', {"pos": line_pts})
            gpu.state.blend_set('ALPHA')
            shader.bind()
            shader.uniform_float("color", prefs.color_selection)
            viewport = gpu.state.viewport_get()
            shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
            shader.uniform_float("lineWidth", prefs.selection_thickness)
            batch.draw(shader)
            gpu.state.blend_set('NONE')
        except Exception as e:
            print(f"Kanvas: Outline Draw error: {e}")

    def draw_gizmos(self, location, scale, shear, rotation, gizmo_size_px):
        if not self.texture: return
        settings = bpy.context.scene.kanvas_settings
        w = self.texture.width  * scale[0]
        h = self.texture.height * scale[1]
        corners_rel = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
        mids_rel    = [(0, -h/2), (w/2, 0), (0, h/2), (-w/2, 0)]
        apply_sh = lambda p: (p[0] + p[1] * shear[0], p[1] + p[0] * shear[1])
        corners_sh = [apply_sh(p) for p in corners_rel]
        mids_sh    = [apply_sh(p) for p in mids_rel]

        gpu.state.blend_set('ALPHA')
        if settings.show_scale_handles:
            tex_scale = get_icon_texture("gizmo-scale-corner")
            for i, p in enumerate(corners_sh):
                pos = rotate_point((p[0] + location[0], p[1] + location[1]), location, rotation)
                draw_icon(tex_scale, pos, gizmo_size_px, rotation + (i * 90), (1, 1, 1, 1))

            prefs = get_prefs()
            shear_mod = prefs.key_shear_mod if prefs else 'ALT'

            is_shear_held = False
            if shear_mod == 'ALT':   is_shear_held = settings.alt_is_held
            elif shear_mod == 'SHIFT': is_shear_held = settings.shift_is_held
            elif shear_mod == 'CTRL':  is_shear_held = settings.ctrl_is_held

            tex_mid = get_icon_texture("gizmo-sheer") if is_shear_held else get_icon_texture("gizmo-stretch")
            color = (0.8, 1, 0.8, 1) if is_shear_held else (1, 0.8, 0.8, 1)
            for i, p in enumerate(mids_sh):
                pos = rotate_point((p[0] + location[0], p[1] + location[1]), location, rotation)
                draw_icon(tex_mid, pos, gizmo_size_px, rotation + (i * 90), color)

        if settings.show_rotate_handles:
            tex_rotate = get_icon_texture("gizmo-rotate")
            off = gizmo_size_px * 1.5
            for i, p in enumerate(corners_sh):
                mag = (p[0]**2 + p[1]**2)**0.5
                if mag > 0:
                    po = (p[0] + (p[0]/mag)*off, p[1] + (p[1]/mag)*off)
                    pos = rotate_point((po[0] + location[0], po[1] + location[1]), location, rotation)
                    draw_icon(tex_rotate, pos, gizmo_size_px, rotation + (i * 90), (0.8, 1, 0.8, 1))
        gpu.state.blend_set('NONE')

# ---------------------------------------------------------------------------
# Texture cache
# ---------------------------------------------------------------------------

# FIX: cache keyed by (image.name, id(image)) so that if the user removes
# and re-adds an image with the same name, we don't serve a stale texture.
_texture_cache: dict[tuple[str, int], KanvasTexture] = {}

def get_kanvas_texture(image: bpy.types.Image) -> KanvasTexture:
    key = (image.name, id(image))
    entry = _texture_cache.get(key)
    if entry is None:
        entry = KanvasTexture(image)
        _texture_cache[key] = entry
    else:
        entry.update(image)
    return entry

def invalidate_texture_cache():
    # FIX: check against bpy.data.images by name only (id() changes on reload)
    live_names = {img.name for img in bpy.data.images}
    stale = [k for k in _texture_cache if k[0] not in live_names]
    for k in stale:
        del _texture_cache[k]

def clear_texture_cache():
    _texture_cache.clear()
    _icon_cache.clear()

def draw_collective_outline(bbox, color, thickness):
    min_x, min_y, max_x, max_y = bbox
    pts = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    line_pts = pts + [pts[0]]

    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    batch  = batch_for_shader(shader, 'LINE_STRIP', {"pos": line_pts})
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    viewport = gpu.state.viewport_get()
    shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
    shader.uniform_float("lineWidth", thickness)
    batch.draw(shader)
    gpu.state.blend_set('NONE')

def draw_collective_gizmos(bbox, gizmo_size_px):
    min_x, min_y, max_x, max_y = bbox
    mid_x = (min_x + max_x) / 2
    mid_y = (min_y + max_y) / 2

    settings = bpy.context.scene.kanvas_settings

    corners = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    mids = [(mid_x, min_y), (max_x, mid_y), (mid_x, max_y), (min_x, mid_y)]

    gpu.state.blend_set('ALPHA')
    if settings.show_scale_handles:
        tex_scale = get_icon_texture("gizmo-scale-corner")
        for i, pos in enumerate(corners):
            draw_icon(tex_scale, pos, gizmo_size_px, (i * 90), (1, 1, 1, 1))

    if settings.show_rotate_handles:
        tex_rotate = get_icon_texture("gizmo-rotate")
        off = gizmo_size_px * 1.5
        for i, p in enumerate(corners):
            dx = p[0] - mid_x
            dy = p[1] - mid_y
            mag = (dx**2 + dy**2)**0.5
            if mag > 0:
                pos = (p[0] + (dx/mag)*off, p[1] + (dy/mag)*off)
                draw_icon(tex_rotate, pos, gizmo_size_px, (i * 90), (0.8, 1, 0.8, 1))
    gpu.state.blend_set('NONE')