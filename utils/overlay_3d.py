"""Kanvas images drawn over the 3D View, live: the canvas shader draws the image with its
mask and adjustments straight from the board, so an edit in Kanvas shows at once.

An overlay is a `scene.kanvas_references` entry of kind 'OVERLAY'. Its rectangle comes
from `overlay_rect`, in the pixels of the 3D View's whole area (so opening the toolbar or
the sidebar never moves it): a height that is a fraction of the area's height, placed at
an anchor (the middle or a corner) and moved by an offset, or fitted inside the camera
frame when looking through the camera.

The drawing never writes to Blender data (that is not allowed while drawing). When the
board changes something an overlay shows, the board's own redraw tags the 3D Views
(`notify_board_drawn`), only when that something changed.
"""

import bpy

from . import measure as measure_math

ANCHOR_ITEMS = (
    ('CENTER', 'Center', 'In the middle of the view'),
    ('TOP_LEFT', 'Top Left', 'In the top left corner of the view'),
    ('TOP_RIGHT', 'Top Right', 'In the top right corner of the view'),
    ('BOTTOM_LEFT', 'Bottom Left', 'In the bottom left corner of the view'),
    ('BOTTOM_RIGHT', 'Bottom Right', 'In the bottom right corner of the view'),
)
HANDLE_SIZE = 12.0          # the corner square that scales an overlay, in pixels

_handle = None
_crop_cache = {}
_last_signature = None


# --- Geometry (plain Python) ---------------------------------------------------------------

def overlay_rect(area_width, area_height, aspect, size, anchor, offset, frame=None):
    """(left, bottom, right, top) in pixels of the 3D View's area. `aspect` is width /
    height of what is shown, `size` its height as a fraction of the area's height. The
    whole area is used, so opening the toolbar or the sidebar never moves an overlay.
    With `frame` (a camera frame rectangle in area pixels), the overlay is fitted inside
    it, centered."""
    aspect = max(1e-6, aspect)
    if frame is not None:
        left, bottom, right, top = frame
        width, height = right - left, top - bottom
        if width / max(height, 1e-6) > aspect:
            width = height * aspect
        else:
            height = width / aspect
        cx, cy = (left + right) * 0.5, (bottom + top) * 0.5
        return cx - width * 0.5, cy - height * 0.5, cx + width * 0.5, cy + height * 0.5
    height = max(1.0, size * area_height)
    width = height * aspect
    if anchor == 'CENTER':
        left, bottom = (area_width - width) * 0.5, (area_height - height) * 0.5
    else:
        left = 0.0 if anchor.endswith('LEFT') else area_width - width
        bottom = 0.0 if anchor.startswith('BOTTOM') else area_height - height
    left, bottom = left + offset[0], bottom + offset[1]
    return left, bottom, left + width, bottom + height


def hit_part(rect, point):
    """'SCALE' on the corner handle (top right), 'MOVE' inside, None outside."""
    left, bottom, right, top = rect
    x, y = point
    if abs(x - right) <= HANDLE_SIZE and abs(y - top) <= HANDLE_SIZE:
        return 'SCALE'
    if left <= x <= right and bottom <= y <= top:
        return 'MOVE'
    return None


# --- What an overlay shows ---------------------------------------------------------------

def _visible_uv(item, crop_to_mask):
    """The UV rectangle the overlay shows (cropped to the mask), cached per mask state:
    finding the crop reads the whole mask."""
    from .item_picture import visible_uv_rect
    if not (crop_to_mask and item.mask_enabled):
        return 0.0, 0.0, 1.0, 1.0
    key = (item.id_data.as_pointer(), item.item_id)
    state = (item.mask_revision, len(item.mask_dabs), len(item.mask_polygons))
    cached = _crop_cache.get(key)
    if cached is None or cached[0] != state:
        cached = (state, visible_uv_rect(item))
        _crop_cache[key] = cached
    return cached[1]


def shown_part(item, entry):
    """(uv_rect, aspect) of an overlay: `uv_rect` is (u, v) at the left/bottom then at
    the right/top of its rectangle (mirrored when flipped), `aspect` the width / height
    of what shows. None when the mask hides everything."""
    from .item_picture import _mirrored
    uv = _visible_uv(item, entry.crop_to_mask)
    if uv is None:
        return None
    u0, v0, u1, v1 = uv
    width, height = item.image_data.size
    aspect = ((u1 - u0) * width) / max(1e-6, (v1 - v0) * height)
    mirror_x, mirror_y = _mirrored(item)
    if mirror_x != bool(entry.flip_h):
        u0, u1 = u1, u0
    if mirror_y:
        v0, v1 = v1, v0
    return (u0, v0, u1, v1), aspect


def camera_frame(context):
    """The camera frame in region pixels when the view looks through the camera."""
    space = context.space_data
    region_3d = getattr(space, 'region_3d', None)
    scene = context.scene
    if region_3d is None or region_3d.view_perspective != 'CAMERA' or scene.camera is None:
        return None
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    camera = scene.camera
    points = [location_3d_to_region_2d(context.region, region_3d, camera.matrix_world @ corner)
              for corner in camera.data.view_frame(scene=scene)]
    if any(point is None for point in points):
        return None
    return (min(p.x for p in points), min(p.y for p in points),
            max(p.x for p in points), max(p.y for p in points))


def entry_layout(context, entry):
    """(item, rect, uv_rect) of an overlay in this 3D View, None when it does not show
    here."""
    from .item_picture import is_picture_item
    from .reference_3d import board_item
    item = board_item(entry.board, entry.item_id)
    if not is_picture_item(item):
        return None
    frame = camera_frame(context) if (entry.fit_camera or entry.only_camera) else None
    if entry.only_camera and frame is None:
        return None
    shown = shown_part(item, entry)
    if shown is None:
        return None
    uv_rect, aspect = shown
    region, area = context.region, context.area
    # Placed in the area, drawn in the region: shift by where the region starts.
    dx, dy = (region.x - area.x, region.y - area.y) if area else (0, 0)
    width, height = (area.width, area.height) if area else (region.width, region.height)
    if frame is not None:
        frame = (frame[0] + dx, frame[1] + dy, frame[2] + dx, frame[3] + dy)
    left, bottom, right, top = overlay_rect(width, height, aspect, entry.size, entry.anchor,
                                            entry.offset, frame if entry.fit_camera else None)
    return item, (left - dx, bottom - dy, right - dx, top - dy), uv_rect


def overlays(scene):
    return [entry for entry in scene.kanvas_references if entry.kind == 'OVERLAY']


# --- Drawing -----------------------------------------------------------------------------

def draw_overlays():
    context = bpy.context
    scene = getattr(context, 'scene', None)
    if scene is None or scene.kanvas_overlays_hidden or not hasattr(scene, 'kanvas_references'):
        return
    entries = [entry for entry in overlays(scene) if entry.show]
    if not entries:
        return
    from .gpu.gpu_common import value_view_uniforms
    from .gpu.gpu_image import get_kanvas_texture
    for entry in entries:
        try:
            layout = entry_layout(context, entry)
            if layout is None:
                continue
            item, rect, uv_rect = layout
            mask = markup = None
            if item.mask_enabled:
                from .gpu.gpu_mask import mask_texture_for_item
                mask = mask_texture_for_item(item)
            if entry.include_markup and item.markup_visible and item.markup_regions:
                from .gpu.gpu_markup import markup_texture_for_item
                markup = markup_texture_for_item(item)
            value_mode, value_levels = value_view_uniforms(item)
            get_kanvas_texture(item.image_data).draw_rect(
                rect, uv_rect, opacity=entry.opacity, color_tint=item.color_tint,
                brightness=item.brightness, contrast=item.contrast,
                saturation=item.saturation, use_color_correction=False,   # the 3D View encodes to sRGB itself
                mask_texture=mask, markup_texture=markup,
                value_mode=value_mode, value_levels=value_levels)
        except Exception as exc:   # one broken overlay must not stop the 3D View
            print(f'Kanvas: could not draw an overlay: {exc}')


def _item_signature(item):
    return (item.image_data.name if item.image_data else '', item.mask_enabled,
            item.mask_revision, len(item.mask_dabs), len(item.mask_polygons),
            item.brightness, item.contrast, item.saturation, tuple(item.color_tint),
            item.flip_h, item.flip_v, tuple(item.scale_xy), item.value_gray,
            item.value_levels, item.markup_visible, item.markup_revision,
            item.use_color_correction, tuple(item.shear_xy), measure_math.signature(item))


def notify_board_drawn(settings):
    """Called after the board is drawn: redraw the 3D Views when something an overlay
    or a live reference shows has changed since the last time (and resize the live
    references' placeholders, from a timer)."""
    global _last_signature
    scene = getattr(bpy.context, 'scene', None)
    if scene is None or not hasattr(scene, 'kanvas_references'):
        return
    from .live_reference_3d import live_entries, schedule_sync, synced_entries
    entries = [] if scene.kanvas_overlays_hidden else [e for e in overlays(scene) if e.show]
    live = synced_entries(scene)
    entries += [entry for entry in live_entries(scene) if entry not in live]
    entries += live
    if not entries:
        _last_signature = None
        return
    from .reference_3d import board_item
    signature = []
    for entry in entries:
        item = board_item(entry.board, entry.item_id)
        signature.append(None if item is None else _item_signature(item))
    signature = tuple(signature)
    if signature == _last_signature:
        return
    _last_signature = signature
    if live:
        schedule_sync()
    tag_3d_views()


def tag_3d_views():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def register():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(draw_overlays, (), 'WINDOW',
                                                         'POST_PIXEL')


def unregister():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    _crop_cache.clear()
