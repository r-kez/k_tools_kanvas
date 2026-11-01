import bpy
from ..kanvas_data import get_settings
import gpu
import os
import time
from gpu_extras.batch import batch_for_shader
from .gpu_common import (rotate_point, get_prefs, get_kanvas_shader,
                         shader_supports_value_view)
from .gpu_theme import studio_enabled
from ..hidden_datablocks import hidden_name
from ..gizmo_geometry import handle_layout, collective_handle_layout

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
        img.name = hidden_name(img.name)
        img.colorspace_settings.name = 'Non-Color'
        # FIX: no gl_load() needed — from_image() handles the GPU upload by itself.
        tex = gpu.texture.from_image(img)
        _icon_cache[name] = tex
        return tex
    except Exception as e:
        print(f"Kanvas: Error loading icon {name}: {e}")
        return None

def draw_icon(texture, center, size, rotation=0, color=(1,1,1,1)):
    if not texture: return
    s = size
    prefs = get_prefs()
    if prefs and prefs.gizmo_background:
        radius = s * 0.53
        x, y = center
        background = [(x - radius, y - radius), (x + radius, y - radius),
                      (x + radius, y + radius), (x - radius, y - radius),
                      (x + radius, y + radius), (x - radius, y + radius)]
        bg_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        bg_shader.bind()
        bg_shader.uniform_float('color', (0.025, 0.03, 0.04, 0.58))
        batch_for_shader(bg_shader, 'TRIS', {'pos': background}).draw(bg_shader)
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


def _draw_transform_handle(center, size, border, pixel_size, *,
                           fill=(0.96, 0.97, 1.0, 0.96), round_handle=False):
    """Filled handle with a one-pixel transparent fringe around its contour."""
    import math
    x, y = center
    radius = size * 0.5

    def shape(shape_radius):
        if round_handle:
            return [(x + math.cos(i * math.tau / 20) * shape_radius,
                     y + math.sin(i * math.tau / 20) * shape_radius)
                    for i in range(20)]
        return [(x - shape_radius, y - shape_radius),
                (x + shape_radius, y - shape_radius),
                (x + shape_radius, y + shape_radius),
                (x - shape_radius, y + shape_radius)]

    points = shape(radius)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    prefs = get_prefs()
    if prefs and prefs.gizmo_background:
        shader.uniform_float('color', (0.025, 0.03, 0.04, 0.58))
        batch_for_shader(shader, 'TRI_FAN', {'pos': shape(radius * 1.35)}).draw(shader)
    shader.uniform_float('color', border)
    batch_for_shader(shader, 'TRI_FAN', {'pos': points}).draw(shader)
    shader.uniform_float('color', fill)
    batch_for_shader(shader, 'TRI_FAN', {
        'pos': shape(max(radius - pixel_size * 1.1, radius * 0.55)),
    }).draw(shader)

    outer = shape(radius + pixel_size)
    fringe_points = []
    fringe_colors = []
    transparent = (*border[:3], 0.0)
    for index in range(len(points)):
        following = (index + 1) % len(points)
        fringe_points.extend((points[index], points[following], outer[following],
                              points[index], outer[following], outer[index]))
        fringe_colors.extend((border, border, transparent,
                              border, transparent, transparent))
    smooth = gpu.shader.from_builtin('SMOOTH_COLOR')
    smooth.bind()
    batch_for_shader(smooth, 'TRIS', {
        'pos': fringe_points, 'color': fringe_colors,
    }).draw(smooth)


def _draw_rotation_stem(start, end, color):
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.bind()
    viewport = gpu.state.viewport_get()
    shader.uniform_float('viewportSize', (viewport[2], viewport[3]))
    shader.uniform_float('lineWidth', 1.5)
    shader.uniform_float('color', color)
    batch_for_shader(shader, 'LINES', {'pos': [start, end]}).draw(shader)

# ---------------------------------------------------------------------------
# Texture wrapper
# ---------------------------------------------------------------------------

class KanvasTexture:
    def __init__(self, image: bpy.types.Image):
        self.image = image
        self.image_name = image.name
        self.texture: gpu.types.GPUTexture | None = None
        self.last_used_at = time.monotonic()

        # We track a manual version counter instead of relying on
        # image.update_tag (which is a *method*, not an attribute, so
        # getattr always returns a truthy bound-method and the early-return
        # guard never fires).  Our own counter is incremented explicitly
        # via KanvasTexture.bump_version() whenever pixel data changes.
        self._version: int = -1

        # Cache outline batch so we don't allocate a new VAO every frame.
        # Invalidated whenever geometry (size/transform) changes.
        self._outline_batch = None
        self._outline_batch_key = None  # (w, h, shear, rotation, location)
        self._quad_batch = None
        self._quad_batch_key = None

        self.update(image)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def bump_version(self):
        """Call this after programmatically changing pixel data."""
        self._version += 1

    # ------------------------------------------------------------------
    # GPU texture management
    # ------------------------------------------------------------------

    def update(self, image: bpy.types.Image):
        # FIX: use image.is_dirty (bool attribute) instead of update_tag
        # (which is a callable method — getattr returns the bound method,
        # always truthy, so the cache check was silently disabled).
        # is_dirty is True when the user has edited pixels since the last
        # save/pack; combined with our manual _version bump it covers both
        # user edits and programmatic changes.
        dirty_flag = int(image.is_dirty) + self._version

        if self.texture is not None and dirty_flag == getattr(self, '_last_dirty', None):
            return  # texture still valid

        try:
            if image.size[0] > 0 and image.size[1] > 0:
                # FIX: removed image.gl_load().
                # gl_load() uploads the image to the internal Blender/OpenGL
                # texture slot AND from_image() creates a *second* GPUTexture
                # object on top of that — doubling VRAM usage per image.
                # gpu.texture.from_image() performs the upload by itself.
                self.texture = gpu.texture.from_image(image)
            else:
                self.texture = None
        except Exception as e:
            print(f"Kanvas: Error creating texture for {image.name}: {e}")
            self.texture = None

        self._last_dirty = dirty_flag
        # Geometry cache must be rebuilt after a texture swap.
        self._outline_batch = None
        self._outline_batch_key = None
        self._quad_batch = None
        self._quad_batch_key = None

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, location, scale, shear, rotation, opacity, color_tint,
             brightness=1.0, contrast=1.0, saturation=1.0,
             flip_h=False, flip_v=False, use_color_correction=True,
             mask_texture=None, mask_enabled=False,
             markup_texture=None, markup_enabled=False,
             value_mode=0.0, value_levels=0.0):
        if not self.texture: return
        shader = get_kanvas_shader()
        if not shader:
            return

        # The quad only changes when the item is transformed, so keep its VAO
        # between redraws instead of allocating one per image per frame.
        geom_key = (self.texture.width, self.texture.height, tuple(location),
                    tuple(scale), tuple(shear), rotation, flip_h, flip_v,
                    id(shader))
        batch = self._quad_batch
        if batch is None or self._quad_batch_key != geom_key:
            w = self.texture.width  * scale[0]
            h = self.texture.height * scale[1]
            pts = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
            sheared_pts = [(p[0] + p[1] * shear[0], p[1] + p[0] * shear[1]) for p in pts]
            final_pts = [rotate_point((p[0] + location[0], p[1] + location[1]), location, rotation) for p in sheared_pts]

            u0, u1 = (1, 0) if flip_h else (0, 1)
            v0, v1 = (1, 0) if flip_v else (0, 1)
            tex_coords = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            batch = batch_for_shader(
                shader, 'TRI_FAN',
                {"pos": final_pts, "texCoord": tex_coords},
            )
            self._quad_batch = batch
            self._quad_batch_key = geom_key

        try:
            gpu.state.blend_set('ALPHA')
            shader.bind()
            shader.uniform_sampler("image", self.texture)
            shader.uniform_sampler("mask_image", mask_texture or self.texture)
            shader.uniform_sampler("markup_image", markup_texture or self.texture)
            shader.uniform_float("color", (color_tint[0], color_tint[1], color_tint[2], opacity))
            shader.uniform_float("brightness", brightness)
            shader.uniform_float("contrast", contrast)
            shader.uniform_float("saturation", saturation)
            shader.uniform_float("use_color_correction", float(use_color_correction))
            shader.uniform_float("mask_enabled", float(mask_enabled and mask_texture is not None))
            shader.uniform_float("markup_enabled", float(markup_enabled and markup_texture is not None))
            if shader_supports_value_view():
                shader.uniform_float("value_mode", value_mode)
                shader.uniform_float("value_levels", value_levels)
            batch.draw(shader)
            gpu.state.blend_set('NONE')
        except Exception as e:
            print(f"Kanvas: Draw error: {e}")
            self._quad_batch = None

    def draw_rect(self, rect, uv_rect=(0.0, 0.0, 1.0, 1.0), opacity=1.0, color_tint=(1.0, 1.0, 1.0),
                  brightness=1.0, contrast=1.0, saturation=1.0, use_color_correction=True,
                  flip_h=False, flip_v=False):
        """Draw part of the image into an axis-aligned rectangle (region pixels in POST_PIXEL)."""
        if not self.texture:
            return
        shader = get_kanvas_shader()
        if not shader:
            return
        left, bottom, right, top = rect
        u0, v0, u1, v1 = uv_rect
        if flip_h:
            u0, u1 = 1.0 - u0, 1.0 - u1
        if flip_v:
            v0, v1 = 1.0 - v0, 1.0 - v1
        batch = batch_for_shader(shader, 'TRI_FAN', {
            'pos': [(left, bottom), (right, bottom), (right, top), (left, top)],
            'texCoord': [(u0, v0), (u1, v0), (u1, v1), (u0, v1)],
        })
        previous = gpu.state.blend_get()
        try:
            gpu.state.blend_set('ALPHA')
            shader.bind()
            shader.uniform_sampler('image', self.texture)
            shader.uniform_sampler('mask_image', self.texture)
            shader.uniform_sampler('markup_image', self.texture)
            shader.uniform_float('color', (color_tint[0], color_tint[1], color_tint[2], opacity))
            shader.uniform_float('brightness', brightness)
            shader.uniform_float('contrast', contrast)
            shader.uniform_float('saturation', saturation)
            shader.uniform_float('use_color_correction', float(use_color_correction))
            shader.uniform_float('mask_enabled', 0.0)
            shader.uniform_float('markup_enabled', 0.0)
            if shader_supports_value_view():
                shader.uniform_float('value_mode', 0.0)
                shader.uniform_float('value_levels', 0.0)
            batch.draw(shader)
        except Exception as exc:
            print(f'Kanvas: Draw error: {exc}')
        finally:
            gpu.state.blend_set(previous)

    def draw_outline(self, location, scale, shear, rotation, color=None, thickness=None):
        if not self.texture: return
        prefs = get_prefs()
        line_color = color if color is not None else (prefs.color_selection if prefs else (0.0, 0.8, 1.0, 1.0))
        line_width = thickness if thickness is not None else (prefs.selection_thickness if prefs else 2.0)

        w = self.texture.width  * scale[0]
        h = self.texture.height * scale[1]

        # FIX: cache the outline batch — only rebuild when geometry changes.
        # Previously a new GPUBatch (VAO) was allocated every redraw frame,
        # which adds unnecessary GPU allocations when many images are selected.
        geom_key = (w, h, tuple(shear), rotation, tuple(location))
        if self._outline_batch is None or self._outline_batch_key != geom_key:
            pts = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
            sheared_pts = [(p[0] + p[1] * shear[0], p[1] + p[0] * shear[1]) for p in pts]
            final_pts = [rotate_point((p[0] + location[0], p[1] + location[1]), location, rotation) for p in sheared_pts]
            line_pts = final_pts + [final_pts[0]]

            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            self._outline_batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": line_pts})
            self._outline_batch_key = geom_key

        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        if not shader: return

        try:
            gpu.state.blend_set('ALPHA')
            shader.bind()
            shader.uniform_float("color", line_color)
            viewport = gpu.state.viewport_get()
            shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
            shader.uniform_float("lineWidth", line_width)
            self._outline_batch.draw(shader)
            gpu.state.blend_set('NONE')
        except Exception as e:
            print(f"Kanvas: Outline Draw error: {e}")

    def draw_gizmos(self, location, scale, shear, rotation, gizmo_size_px):
        if not self.texture: return
        settings = get_settings(bpy.context)
        w = self.texture.width  * scale[0]
        h = self.texture.height * scale[1]
        corners, edges, stem, rotate = handle_layout(
            location, w, h, shear, rotation, gizmo_size_px)
        prefs = get_prefs()
        outline = tuple(prefs.color_selection) if prefs else (0.0, 0.8, 1.0, 1.0)
        modern = studio_enabled()
        pixel_size = gizmo_size_px / max(settings.gizmo_size, 1.0)

        gpu.state.blend_set('ALPHA')
        if settings.show_rotate_handles:
            _draw_rotation_stem(stem, rotate, outline)
        if settings.show_scale_handles:
            for pos in corners:
                _draw_transform_handle(pos, gizmo_size_px * 0.44,
                                       outline, pixel_size,
                                       fill=(0.06, 0.09, 0.12, 0.96) if modern
                                       else (0.96, 0.97, 1.0, 0.96),
                                       round_handle=modern)
            shear_mod = prefs.key_shear_mod if prefs else 'ALT'
            held = {'ALT': settings.alt_is_held,
                    'SHIFT': settings.shift_is_held,
                    'CTRL': settings.ctrl_is_held}[shear_mod]
            edge_color = (0.06, 0.3, 0.16, 1.0) if held else outline
            edge_fill = ((0.36, 1.0, 0.6, 1.0) if held
                         else (0.06, 0.09, 0.12, 0.96) if modern
                         else (0.96, 0.97, 1.0, 0.96))
            for pos in edges:
                _draw_transform_handle(pos, gizmo_size_px * 0.32,
                                       edge_color, pixel_size, fill=edge_fill,
                                       round_handle=modern)

        if settings.show_rotate_handles:
            _draw_transform_handle(rotate, gizmo_size_px * 0.5,
                                   outline, pixel_size,
                                   round_handle=True)
        gpu.state.blend_set('NONE')

    def draw_hitboxes(self, location, scale, shear, rotation, gizmo_size_px):
        if not self.texture: return
        w = self.texture.width  * scale[0]
        h = self.texture.height * scale[1]
        corners, edges, _, rotate = handle_layout(
            location, w, h, shear, rotation, gizmo_size_px)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        shader.bind()

        def box(center, color):
            x, y = center
            radius = gizmo_size_px * 0.4
            points = [(x - radius, y - radius), (x + radius, y - radius),
                      (x + radius, y + radius), (x - radius, y + radius)]
            shader.uniform_float('color', color)
            batch_for_shader(shader, 'LINE_LOOP', {'pos': points}).draw(shader)

        for point in corners:
            box(point, (1, 1, 0, 0.8))
        for point in edges:
            box(point, (0, 0.5, 1, 0.8))
        box(rotate, (1, 0, 1, 0.8))
        gpu.state.blend_set('NONE')

# ---------------------------------------------------------------------------
# Texture cache
# ---------------------------------------------------------------------------

_texture_cache: dict[tuple[str, int], KanvasTexture] = {}
_last_cache_prune_at = 0.0
_CACHE_PRUNE_INTERVAL = 0.5

def get_kanvas_texture(image: bpy.types.Image) -> KanvasTexture:
    key = (image.name, id(image))
    entry = _texture_cache.get(key)
    if entry is None:
        entry = KanvasTexture(image)
        _texture_cache[key] = entry
    else:
        entry.update(image)
    entry.last_used_at = time.monotonic()
    return entry

def get_cached_texture(image: bpy.types.Image) -> KanvasTexture | None:
    if not image:
        return None
    key = (image.name, id(image))
    return _texture_cache.get(key)

def invalidate_texture_cache():
    live_names = {img.name for img in bpy.data.images}
    stale = [k for k in _texture_cache if k[0] not in live_names]
    for k in stale:
        del _texture_cache[k]


def _release_cached_texture(key, entry):
    # from_image() shares memory with the Image datablock. Drop our Python
    # reference before asking Blender to release its GPU copy.
    entry.texture = None
    entry._outline_batch = None
    entry._quad_batch = None
    try:
        entry.image.gl_free()
    except (ReferenceError, RuntimeError):
        pass
    _texture_cache.pop(key, None)


def invalidate_image_texture(image):
    """Release the cached GPU texture for one Blender image."""
    key = (image.name, id(image))
    entry = _texture_cache.get(key)
    if entry is not None:
        _release_cached_texture(key, entry)


# Textures stay resident so zooming out over the whole board never has to
# re-upload every image at once (that burst was the zoom-out stutter). They are
# released only when truly idle or when the estimated VRAM budget is exceeded.
_IDLE_RELEASE_SECONDS = 180.0
_VRAM_BUDGET_BYTES = 2 * 1024 ** 3
_RECENT_SECONDS = 1.0


def _texture_bytes(entry):
    texture = entry.texture
    if texture is None:
        return 0
    # RGBA8 plus roughly one third extra for the mip chain.
    return int(texture.width * texture.height * 4 * 1.34)


def prune_texture_cache(idle_seconds=_IDLE_RELEASE_SECONDS,
                        budget_bytes=_VRAM_BUDGET_BYTES):
    """Release GPU textures that are long idle, then least-recently-used ones
    while the estimated total exceeds the budget."""
    global _last_cache_prune_at
    if not _texture_cache:
        return
    prefs = get_prefs()
    if prefs is not None and hasattr(prefs, 'texture_budget_mb'):
        budget_bytes = prefs.texture_budget_mb * 1024 ** 2
    now = time.monotonic()
    if now - _last_cache_prune_at < _CACHE_PRUNE_INTERVAL:
        return
    _last_cache_prune_at = now
    cutoff = now - idle_seconds
    for key, entry in list(_texture_cache.items()):
        if entry.last_used_at <= cutoff:
            _release_cached_texture(key, entry)
    total = sum(_texture_bytes(entry) for entry in _texture_cache.values())
    if total <= budget_bytes:
        return
    recent = now - _RECENT_SECONDS
    for key, entry in sorted(_texture_cache.items(), key=lambda kv: kv[1].last_used_at):
        if total <= budget_bytes or entry.last_used_at > recent:
            break
        total -= _texture_bytes(entry)
        _release_cached_texture(key, entry)

def clear_texture_cache():
    """Remove all GPU textures and purge Kanvas icon images from bpy.data."""
    for key, entry in list(_texture_cache.items()):
        _release_cached_texture(key, entry)
    # FIX: also remove icon images that were loaded into bpy.data so they
    # don't linger after an addon reload (they'd have stale GPUTexture refs).
    addon_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    icon_dir = os.path.join(addon_dir, "assets", "icons")
    for img in list(bpy.data.images):
        if img.filepath.startswith(icon_dir):
            try:
                bpy.data.images.remove(img)
            except Exception:
                pass

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
    settings = get_settings(bpy.context)
    corners, stem, rotate = collective_handle_layout(bbox, gizmo_size_px)
    prefs = get_prefs()
    outline = tuple(prefs.color_selection) if prefs else (0.0, 0.8, 1.0, 1.0)
    modern = studio_enabled()
    pixel_size = gizmo_size_px / max(settings.gizmo_size, 1.0)

    gpu.state.blend_set('ALPHA')
    if settings.show_rotate_handles:
        _draw_rotation_stem(stem, rotate, outline)
    if settings.show_scale_handles:
        for pos in corners:
            _draw_transform_handle(pos, gizmo_size_px * 0.44,
                                   outline, pixel_size,
                                   fill=(0.06, 0.09, 0.12, 0.96) if modern
                                   else (0.96, 0.97, 1.0, 0.96),
                                   round_handle=modern)

    if settings.show_rotate_handles:
        _draw_transform_handle(rotate, gizmo_size_px * 0.5,
                               outline, pixel_size,
                               round_handle=True)
    gpu.state.blend_set('NONE')
