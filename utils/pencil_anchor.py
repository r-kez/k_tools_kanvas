"""Pencil Drawings stuck to an image.

A drawing can ride on the image it was drawn over: it moves, rotates and scales with it.
Rather than hook every way an image can be transformed (the modal gestures, the panel,
Align, frames, Pack...), the drawing keeps its pose relative to the image and `sync`
brings it back in line whenever the image has moved since the last look:

* the image's pose (location, rotation, overall scale) changed: the drawing follows;
* the drawing's own pose changed (the user moved it, or a stroke refit its box): the
  relative pose is taken again from where things are now. That also covers moving both
  together, and leaves the drawing free to be placed by hand.

The image's stretch, shear and flips are not carried over: only a similarity (move,
rotate, uniform scale) is. Everything is derived from two stored poses, so undo needs
nothing special.
"""

import math

from . import item_geometry

TOLERANCE = 1e-3


def is_drawing(item):
    return item.item_type == 'SHAPE' and item.shape_kind == 'PENCIL'


def _pose(item):
    return (float(item.location[0]), float(item.location[1]),
            float(item.rotation), float(item.scale_master))


def _same(a, b):
    return all(abs(p - q) <= TOLERANCE * (1.0 + 1e-3 * abs(p)) for p, q in zip(a, b))


def _scale(value):
    return value if abs(value) > 1e-6 else 1e-6


def _capture(drawing, image):
    """Take the drawing's pose relative to the image from where both are now."""
    px, py, prot, pscale = _pose(image)
    x, y, rot, scale = _pose(drawing)
    angle = math.radians(-prot)
    c, s = math.cos(angle), math.sin(angle)
    dx, dy = (x - px) / _scale(pscale), (y - py) / _scale(pscale)
    drawing.anchor_offset = (dx * c - dy * s, dx * s + dy * c)
    drawing.anchor_rotation = rot - prot
    drawing.anchor_scale = scale / _scale(pscale)
    drawing.anchor_parent_seen = _pose(image)
    drawing.anchor_self_seen = _pose(drawing)


def attach(drawing, image):
    """Stick `drawing` to `image` where it lies now."""
    drawing.anchor_item_id = image.item_id
    _capture(drawing, image)


def detach(drawing):
    drawing.anchor_item_id = ''


def parent_of(settings, drawing):
    """The image a drawing is stuck to, or None."""
    if not drawing.anchor_item_id:
        return None
    return next((item for item in settings.images
                 if item.item_id == drawing.anchor_item_id and item.item_type == 'IMAGE'), None)


def drawings_of(settings, image):
    """Pencil Drawings stuck to `image`, shown ones only."""
    return [item for item in settings.images
            if is_drawing(item) and item.anchor_item_id == image.item_id
            and item.show_in_editor]


def sync(settings):
    """Bring every stuck drawing in line with its image (see the module doc). Cheap when
    nothing moved; safe to call from a draw callback."""
    from ..properties import suspend_frame_geometry_updates
    for drawing in settings.images:
        if not drawing.anchor_item_id or not is_drawing(drawing):
            continue
        image = parent_of(settings, drawing)
        if image is None:
            detach(drawing)             # the image is gone
            continue
        pose = _pose(image)
        if not _same(_pose(drawing), tuple(drawing.anchor_self_seen)):
            with suspend_frame_geometry_updates():
                _capture(drawing, image)
            continue
        if _same(pose, tuple(drawing.anchor_parent_seen)):
            continue
        px, py, prot, pscale = pose
        angle = math.radians(prot)
        c, s = math.cos(angle), math.sin(angle)
        ox, oy = drawing.anchor_offset
        with suspend_frame_geometry_updates():
            drawing.location = (px + pscale * (ox * c - oy * s),
                                py + pscale * (ox * s + oy * c))
            drawing.rotation = prot + drawing.anchor_rotation
            drawing.scale_master = pscale * drawing.anchor_scale
            drawing.anchor_parent_seen = pose
            drawing.anchor_self_seen = _pose(drawing)    # as stored, not as computed


def image_under_point(settings, point):
    """The top image (shown, unlocked) that covers a canvas point, or None."""
    from .item_crop import box_size
    from .gpu.gpu_common import rotate_point
    for index in reversed(list(item_geometry.layer_draw_indices(settings))):
        item = settings.images[index]
        if item.item_type != 'IMAGE' or not item.image_data or not item.show_in_editor:
            continue
        if item.is_locked:
            continue
        width, height = box_size(item, *item.image_data.size)
        if width <= 0 or height <= 0:
            continue
        rel = rotate_point(point, item.location, -item.rotation)
        dx, dy = rel[0] - item.location[0], rel[1] - item.location[1]
        shear_x, shear_y = item.shear_xy
        denominator = 1.0 - shear_x * shear_y
        if abs(denominator) < 1e-4:
            denominator = 1e-4
        raw_y = (dy - dx * shear_y) / denominator
        raw_x = dx - raw_y * shear_x
        half_w = abs(width * item.scale_xy[0] * item.scale_master) * 0.5
        half_h = abs(height * item.scale_xy[1] * item.scale_master) * 0.5
        if -half_w <= raw_x <= half_w and -half_h <= raw_y <= half_h:
            return item
    return None
