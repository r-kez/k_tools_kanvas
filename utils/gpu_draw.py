import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Image shader
# ---------------------------------------------------------------------------
#
# gpu.texture.from_image() sempre entrega a textura em Scene Linear,
# independente do colorspace configurado pelo usuário na imagem.
# O Blender aplica a conversão OCIO internamente ao fazer o upload para GPU.
#
# O builtin IMAGE_SCENE_LINEAR_TO_REC709_SRGB (Blender 5.0+) converte
# Scene Linear -> Rec.709/sRGB na saída, que é o espaço correto para o
# framebuffer do Node Editor — sem shader GLSL manual e sem tocar no
# colorspace da imagem do usuário.

def get_kanvas_shader():
    """Return the builtin shader that handles Scene Linear -> Rec.709 conversion.

    IMAGE_COLOR_SCENE_LINEAR_TO_REC709_SRGB:
      - Uniforms: sampler2D image, vec4 color  (tint + opacity via color.a)
      - Expects texture in Scene Linear (gpu.texture.from_image guarantees this)
      - Converts Scene Linear -> Rec.709/sRGB on output for the Node Editor framebuffer
    """
    return gpu.shader.from_builtin('IMAGE_COLOR_SCENE_LINEAR_TO_REC709_SRGB')


# ---------------------------------------------------------------------------
# Texture wrapper
# ---------------------------------------------------------------------------

class KanvasTexture:
    """Manages the GPU texture for a single Blender Image."""

    def __init__(self, image: bpy.types.Image):
        self.image_name = image.name
        self.texture = None
        self.update(image)

    def update(self, image: bpy.types.Image):
        """(Re-)upload image pixels to the GPU."""
        # Always re-upload so external edits to the image are reflected.
        self.texture = gpu.texture.from_image(image)

    # ------------------------------------------------------------------
    # Draw calls
    # ------------------------------------------------------------------

    def draw(self, location, scale, rotation, opacity, color_tint):
        """Draw the texture centered and rotated at *location*.

        gpu.texture.from_image() uploads the texture in Scene Linear space
        (Blender handles the OCIO conversion internally).
        IMAGE_SCENE_LINEAR_TO_REC709_SRGB then converts to Rec.709 on output,
        which matches the Node Editor framebuffer — no manual GLSL needed.
        The user's image colorspace setting is never touched.
        """
        if not self.texture:
            return

        w = self.texture.width  * scale
        h = self.texture.height * scale

        pts = [
            (location[0] - w/2, location[1] - h/2),
            (location[0] + w/2, location[1] - h/2),
            (location[0] + w/2, location[1] + h/2),
            (location[0] - w/2, location[1] + h/2),
        ]
        rotated_pts = [rotate_point(p, location, rotation) for p in pts]

        shader = get_kanvas_shader()
        batch = batch_for_shader(
            shader, 'TRI_FAN',
            {
                "pos":      rotated_pts,
                "texCoord": [(0, 0), (1, 0), (1, 1), (0, 1)],
            },
        )

        gpu.state.blend_set('ALPHA')
        shader.bind()
        shader.uniform_sampler("image", self.texture)
        shader.uniform_float("color", (color_tint[0], color_tint[1], color_tint[2], opacity))
        batch.draw(shader)
        gpu.state.blend_set('NONE')

    def draw_outline(self, location, scale, rotation):
        """Draw a selection border around the image."""
        if not self.texture:
            return

        prefs = get_prefs()
        if prefs is None:
            return

        w = self.texture.width  * scale
        h = self.texture.height * scale

        pts = [
            (location[0] - w/2, location[1] - h/2),
            (location[0] + w/2, location[1] - h/2),
            (location[0] + w/2, location[1] + h/2),
            (location[0] - w/2, location[1] + h/2),
        ]
        rotated_pts = [rotate_point(p, location, rotation) for p in pts]
        # Close the loop manually for LINES primitive
        line_pts = rotated_pts + [rotated_pts[0]]

        # Blender 4.5+/5.0: use POLYLINE_UNIFORM_COLOR for width-aware lines
        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        batch  = batch_for_shader(shader, 'LINE_STRIP', {"pos": line_pts})

        shader.bind()
        shader.uniform_float("color", prefs.color_selection)
        # POLYLINE_UNIFORM_COLOR requires viewportSize and lineWidth
        viewport = gpu.state.viewport_get()
        shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
        shader.uniform_float("lineWidth", prefs.selection_thickness)
        batch.draw(shader)

    def draw_gizmos(self, location, scale, rotation, gizmo_size_px):
        """Draw interactive scale handles around the image."""
        if not self.texture:
            return

        w = self.texture.width  * scale
        h = self.texture.height * scale
        x_mid, y_mid = location[0], location[1]

        handles = [
            (location[0] - w/2, location[1] - h/2),
            (x_mid,             location[1] - h/2),
            (location[0] + w/2, location[1] - h/2),
            (location[0] - w/2, y_mid),
            (location[0] + w/2, y_mid),
            (location[0] - w/2, location[1] + h/2),
            (x_mid,             location[1] + h/2),
            (location[0] + w/2, location[1] + h/2),
        ]

        fill_shader    = gpu.shader.from_builtin('UNIFORM_COLOR')
        outline_shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        viewport       = gpu.state.viewport_get()
        s = gizmo_size_px

        for h_pos in handles:
            rh_pos = rotate_point(h_pos, location, rotation)

            h_pts = [
                (rh_pos[0] - s/2, rh_pos[1] - s/2),
                (rh_pos[0] + s/2, rh_pos[1] - s/2),
                (rh_pos[0] + s/2, rh_pos[1] + s/2),
                (rh_pos[0] - s/2, rh_pos[1] + s/2),
            ]
            rh_pts = [rotate_point(p, rh_pos, rotation) for p in h_pts]

            # Filled quad
            fill_batch = batch_for_shader(fill_shader, 'TRI_FAN', {"pos": rh_pts})
            fill_shader.bind()
            fill_shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
            fill_batch.draw(fill_shader)

            # Outline — POLYLINE_UNIFORM_COLOR (Blender 4.5+/5.0)
            outline_pts   = rh_pts + [rh_pts[0]]   # close the loop
            outline_batch = batch_for_shader(outline_shader, 'LINE_STRIP', {"pos": outline_pts})
            outline_shader.bind()
            outline_shader.uniform_float("color", (0.0, 0.0, 0.0, 1.0))
            outline_shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
            outline_shader.uniform_float("lineWidth", 1.0)
            outline_batch.draw(outline_shader)


# ---------------------------------------------------------------------------
# Texture cache
# ---------------------------------------------------------------------------

# Keyed by (image.name, image.users) — detects renames and reloads.
# For a more robust solution you could key by id(image), but names are
# stable enough in most workflows.
_texture_cache: dict[str, KanvasTexture] = {}


def get_kanvas_texture(image: bpy.types.Image) -> KanvasTexture:
    """Return a cached KanvasTexture, refreshing it when the image changes."""
    entry = _texture_cache.get(image.name)
    if entry is None:
        entry = KanvasTexture(image)
        _texture_cache[image.name] = entry
    else:
        # Re-upload if the image was modified since last draw
        entry.update(image)
    return entry


def invalidate_texture_cache():
    """Remove stale entries whose source image no longer exists in bpy.data."""
    stale = [name for name in _texture_cache if name not in bpy.data.images]
    for name in stale:
        del _texture_cache[name]


# ---------------------------------------------------------------------------
# Axis helper
# ---------------------------------------------------------------------------

def draw_axes(size=10000.0):
    """Draw X and Y axis lines for orientation."""
    prefs = get_prefs()
    if prefs is None:
        return

    # Axes are thin decorative lines — POLYLINE_UNIFORM_COLOR for 5.0 compat
    shader  = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    viewport = gpu.state.viewport_get()

    shader.bind()
    shader.uniform_float("viewportSize", (viewport[2], viewport[3]))
    shader.uniform_float("lineWidth", 1.0)

    batch_x = batch_for_shader(shader, 'LINES', {"pos": [(-size, 0), (size, 0)]})
    shader.uniform_float("color", prefs.color_x_axis)
    batch_x.draw(shader)

    batch_y = batch_for_shader(shader, 'LINES', {"pos": [(0, -size), (0, size)]})
    shader.uniform_float("color", prefs.color_y_axis)
    batch_y.draw(shader)


# ---------------------------------------------------------------------------
# Draw callback
# ---------------------------------------------------------------------------

def draw_callback_px():
    """SpaceNodeEditor POST_VIEW draw callback."""
    context = bpy.context

    if not hasattr(context, "scene") or context.scene is None:
        return

    if (not hasattr(context, "space_data")
            or not hasattr(context.space_data, "edit_tree")
            or context.space_data.edit_tree is None
            or context.space_data.edit_tree.bl_idname != 'KanvasNodeTree'):
        return

    settings = context.scene.kanvas_settings

    if settings.show_debug_grid:
        draw_axes()

    if not settings.show_all:
        return

    # Periodically evict dead textures
    invalidate_texture_cache()

    for img_item in settings.images:
        if not img_item.show_in_editor or not img_item.image_data:
            continue

        tex = get_kanvas_texture(img_item.image_data)
        tex.draw(
            img_item.location,
            img_item.scale,
            img_item.rotation,
            img_item.opacity,
            img_item.color_tint,
        )

        if img_item.is_selected:
            tex.draw_outline(img_item.location, img_item.scale, img_item.rotation)
            if settings.show_gizmos:
                tex.draw_gizmos(
                    img_item.location,
                    img_item.scale,
                    img_item.rotation,
                    settings.gizmo_size,
                )


# ---------------------------------------------------------------------------
# Handler management
# ---------------------------------------------------------------------------

class KanvasDrawHandler:
    _handler = None

    @classmethod
    def add_handler(cls):
        if cls._handler is None:
            # Pass an empty tuple — the callback uses bpy.context internally.
            cls._handler = bpy.types.SpaceNodeEditor.draw_handler_add(
                draw_callback_px, (), 'WINDOW', 'POST_VIEW'
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