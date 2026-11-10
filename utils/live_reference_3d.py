"""Live reference images: an image empty in the scene whose picture Kanvas draws itself,
straight from the GPU textures of the board, so an edit in Kanvas shows in the 3D View
at once and the colors are the board's (Blender's view transform, such as AgX, is not
applied to it as it is to an image file on an empty).

The empty holds a placeholder: a generated, fully transparent image with the proportions
of the picture. Blender draws nothing visible from it, but keeps doing everything else
for the empty (selecting, outlining, transforming, the Size and Offset of the image).
A generated image stores no pixels, so it never asks to be saved. Kanvas then draws the
picture on the same plane (in linear color: the 3D View turns what add-ons draw into
sRGB itself, so the canvas shader's own sRGB step is left out, or the picture would look
washed out), following Blender's rules for image empties: orthographic and
perspective visibility, Only Axis Aligned, the side it shows from, depth (Default,
Front, Back) and opacity.

Writing to Blender data is not allowed while drawing, so a placeholder whose proportions
must change (a new mask) is resized from a timer (`schedule_sync`).
"""

import bpy
import gpu

PLACEHOLDER_SIDE = 1024     # longer side of a placeholder: its proportions, to 1/1024
_handles = []
_quad_cache = {}
_sync_scheduled = False


# --- Placeholder -----------------------------------------------------------------------

def placeholder_size(aspect):
    aspect = max(1e-4, aspect)
    if aspect >= 1.0:
        return PLACEHOLDER_SIDE, max(1, round(PLACEHOLDER_SIDE / aspect))
    return max(1, round(PLACEHOLDER_SIDE * aspect)), PLACEHOLDER_SIDE


def is_placeholder(image):
    return image is not None and bool(image.get('kanvas_placeholder'))


def ensure_placeholder(obj, name, aspect):
    """Give `obj` a transparent placeholder image of the right proportions."""
    width, height = placeholder_size(aspect)
    image = obj.data if is_placeholder(obj.data) else None
    if image is None:
        image = bpy.data.images.new(f'.Kanvas Ref {name}', width, height, alpha=True)
        image.generated_color = (0.0, 0.0, 0.0, 0.0)
        image['kanvas_placeholder'] = True
        obj.data = image
    elif tuple(image.size) != (width, height):
        image.generated_width, image.generated_height = width, height
    return image


# --- What a live reference shows ----------------------------------------------------------

def _quad(item, entry):
    """`picture_quad` of an entry, cached while the item and options stay the same:
    finding the crop reads the whole mask."""
    from .item_picture import picture_quad
    key = (item.id_data.as_pointer(), item.item_id)
    state = (item.mask_enabled, item.mask_revision, len(item.mask_dabs),
             len(item.mask_polygons), item.flip_h, item.flip_v, tuple(item.scale_xy),
             tuple(item.shear_xy), tuple(item.image_data.size), entry.crop_to_mask,
             entry.keep_stretch, item.crop_enabled, tuple(item.crop_uv), item.persp_enabled,
             tuple(item.persp_corners), item.persp_auto, item.persp_aspect, item.persp_editing,
             item.persp_whole)
    cached = _quad_cache.get(key)
    if cached is None or cached[0] != state:
        cached = (state, picture_quad(item, entry.crop_to_mask, entry.keep_stretch))
        _quad_cache[key] = cached
    return cached[1]


def quad_aspect(quad):
    x0, y0, x1, y1 = quad[2]
    return (x1 - x0) / max(1e-6, y1 - y0)


def plane_corners(obj, quad):
    """The quad's corners on the empty's image plane, in the empty's own space: the
    picture spans the image of an empty, Size on its longer side, moved by Offset."""
    corners, _, (x0, y0, x1, y1) = quad
    width, height = x1 - x0, y1 - y0
    size = obj.empty_display_size
    if width >= height:
        plane_w, plane_h = size, size * height / max(width, 1e-6)
    else:
        plane_w, plane_h = size * width / max(height, 1e-6), size
    ox, oy = obj.empty_image_offset
    return [(ox * plane_w + (x - x0) / max(width, 1e-6) * plane_w,
             oy * plane_h + (y - y0) / max(height, 1e-6) * plane_h) for x, y in corners]


def shows_in_view(obj, space, region_3d):
    """Blender's rules for drawing an image empty in this 3D View."""
    if not obj.visible_get(viewport=space):
        return False
    if not space.overlay.show_overlays or not space.show_object_viewport_empty:
        return False
    if region_3d.is_perspective:
        if not obj.show_empty_image_perspective:
            return False
    elif not obj.show_empty_image_orthographic:
        return False
    normal = obj.matrix_world.to_3x3().col[2].normalized()
    view_inverse = region_3d.view_matrix.inverted()
    if obj.show_empty_image_only_axis_aligned:
        view_axis = view_inverse.col[2].xyz.normalized()
        if abs(normal.dot(view_axis)) < 0.9999:
            return False
    if obj.empty_image_side != 'DOUBLE_SIDED':
        if region_3d.is_perspective:
            toward = obj.matrix_world.translation - view_inverse.translation
        else:
            toward = -view_inverse.col[2].xyz
        facing_front = normal.dot(toward) < 0.0
        if facing_front != (obj.empty_image_side == 'FRONT'):
            return False
    return True


def live_entries(scene):
    return [entry for entry in getattr(scene, 'kanvas_references', ())
            if entry.kind == 'EMPTY' and entry.live and entry.object is not None
            and entry.object.users_collection]


def synced_entries(scene):
    """The reference images Kanvas keeps in step with the board: live ones (their
    placeholder follows the picture's proportions) and those that follow the real size
    of the image."""
    return [entry for entry in getattr(scene, 'kanvas_references', ())
            if entry.kind == 'EMPTY' and (entry.live or entry.real_scale)
            and entry.object is not None and entry.object.users_collection]


# --- Drawing -----------------------------------------------------------------------------

def _far_projection(projection):
    """The projection with every point pushed to the far plane (depth 1): drawn with a
    LESS_EQUAL depth test, it shows only where nothing else was drawn, behind
    everything, as Blender's Background image empties."""
    from mathutils import Matrix
    rows = [list(row) for row in projection]
    rows[2] = list(rows[3])          # z_clip = w_clip, so z / w = 1
    return Matrix(rows)


def xray_alpha(space):
    """How solid the meshes are in this 3D View while X-ray is on (0 clear, 1 solid), None
    when it is off. Wireframe has its own switch and its own alpha."""
    shading = getattr(space, 'shading', None)
    if shading is None:
        return None
    if shading.type == 'WIREFRAME':
        return shading.xray_alpha_wireframe if shading.show_xray_wireframe else None
    return shading.xray_alpha if shading.show_xray else None


def draw_references():
    """Draw the live references, after the scene: Default ones tested against the
    scene's depth, In Front ones over it, Background ones at the far plane."""
    context = bpy.context
    scene = getattr(context, 'scene', None)
    space = getattr(context, 'space_data', None)
    if scene is None or space is None or space.type != 'VIEW_3D':
        return
    entries = live_entries(scene)
    if not entries:
        return
    region_3d = space.region_3d
    from .gpu.gpu_common import value_view_uniforms
    from .item_crop import corrected
    from .gpu.gpu_image import get_kanvas_texture
    from .item_picture import is_picture_item
    from .reference_3d import board_item
    for entry in entries:
        obj = entry.object
        try:
            item = board_item(entry.board, entry.item_id)
            if not is_picture_item(item) or not shows_in_view(obj, space, region_3d):
                continue
            quad = _quad(item, entry)
            if quad is None:
                continue
            mask = markup = None
            if item.mask_enabled:
                from .gpu.gpu_mask import mask_texture_for_item
                mask = mask_texture_for_item(item)
            if entry.include_markup and item.markup_regions:
                from .gpu.gpu_markup import markup_texture_for_item
                markup = markup_texture_for_item(item, force=True)
            value_mode, value_levels = value_view_uniforms(item)
            opacity = obj.color[3] if obj.use_empty_image_alpha else 1.0
            front = obj.empty_image_depth == 'FRONT'
            # Pass 1: what no mesh covers (all of it, for In Front). In X-ray a second pass
            # shows the part behind meshes through them, as faintly as the meshes are solid.
            passes = [('NONE' if front else 'LESS_EQUAL', opacity)]
            see_through = xray_alpha(space)
            if see_through is not None and not front:
                passes.append(('GREATER', opacity * (1.0 - see_through)))
            gpu.state.depth_mask_set(False)
            for depth, pass_opacity in passes:
                gpu.state.depth_test_set(depth)
                with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                    if obj.empty_image_depth == 'BACK':
                        gpu.matrix.load_projection_matrix(
                            _far_projection(gpu.matrix.get_projection_matrix()))
                    gpu.matrix.multiply_matrix(obj.matrix_world)
                    get_kanvas_texture(item.image_data).draw_quad(
                        plane_corners(obj, quad), quad[1], opacity=pass_opacity,
                        color_tint=item.color_tint, brightness=item.brightness,
                        contrast=item.contrast, saturation=item.saturation,
                        use_color_correction=False,   # the 3D View encodes to sRGB itself
                        mask_texture=mask, markup_texture=markup,
                        value_mode=value_mode, value_levels=value_levels,
                        nearest=item.sampling == 'NEAREST', warp=corrected(item))
            gpu.state.depth_test_set('NONE')
        except Exception as exc:   # one broken reference must not stop the 3D View
            print(f'Kanvas: could not draw a live reference: {exc}')


# --- Keeping placeholders in proportion ------------------------------------------------------

def sync_entry(entry, scene=None):
    """Bring a reference in step with its image: a live one's placeholder takes the
    proportions of the picture, and one that follows the real size takes the Size the
    scale of the image gives. Not from a draw function."""
    from .item_picture import is_picture_item
    from .reference_3d import board_item, real_size_scene
    if entry.object is None or not (entry.live or entry.real_scale):
        return
    item = board_item(entry.board, entry.item_id)
    if not is_picture_item(item):
        return
    if entry.live:
        quad = _quad(item, entry)
        if quad is not None:
            ensure_placeholder(entry.object, entry.name or item.name, quad_aspect(quad))
    if entry.real_scale:
        size = real_size_scene(item, entry, scene or bpy.context.scene)
        if size is not None and abs(entry.object.empty_display_size - size) > 1e-9:
            entry.object.empty_display_size = size


def _sync_all():
    global _sync_scheduled
    _sync_scheduled = False
    for scene in bpy.data.scenes:
        for entry in synced_entries(scene):
            try:
                sync_entry(entry, scene)
            except Exception as exc:
                print(f'Kanvas: could not resize a live reference: {exc}')
    return None


def schedule_sync():
    """Resize the placeholders soon, outside of drawing."""
    global _sync_scheduled
    if not _sync_scheduled:
        _sync_scheduled = True
        bpy.app.timers.register(_sync_all, first_interval=0.0)


@bpy.app.handlers.persistent
def _after_load(*_args):
    from .reference_3d import migrate_references
    migrate_references()


def _migrate_open_file():
    from .reference_3d import migrate_references
    try:
        migrate_references()
    except Exception as exc:    # bpy.data may not be ready yet: the load handler retries
        print(f'Kanvas: could not update the references: {exc}')
    return None


def register():
    if _after_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_after_load)
    bpy.app.timers.register(_migrate_open_file, first_interval=0.5)
    if not _handles:
        _handles.append(('POST_VIEW', bpy.types.SpaceView3D.draw_handler_add(
            draw_references, (), 'WINDOW', 'POST_VIEW')))


def unregister():
    global _sync_scheduled
    if _after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_after_load)
    if bpy.app.timers.is_registered(_migrate_open_file):
        bpy.app.timers.unregister(_migrate_open_file)
    for _, handle in _handles:
        bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
    _handles.clear()
    _quad_cache.clear()
    if bpy.app.timers.is_registered(_sync_all):
        bpy.app.timers.unregister(_sync_all)
    _sync_scheduled = False
