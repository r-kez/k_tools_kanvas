"""Cropping an image item to part of its image (Fit Bounds to Mask).

An item can show only a rectangle of its image, in image coordinates (UV, as masks store
them): `crop_uv` = (u0, v0, u1, v1) when `crop_enabled`. The item is that rectangle: its
bounds, selection box, handles, snapping, alignment, frames and arrows all see the cropped
size, and its place (`location`), rotation and scale are those of the rectangle. The
rectangle's middle is the **pivot**: the point of the image that sits at `location`.

The texture, the mask, the color markup and the marks stay in the coordinates of the whole
image, so nothing in them needs converting: the drawing just reads another part of the
same textures.

While the mask or the color markup is edited, the whole image is drawn around the same
pivot (nothing moves), so strokes can reach what the crop hides. The box of the item stays
the crop's.

The same mapping carries the **perspective correction** (`utils/perspective.py`): an item
with its perspective corrected is the straightened rectangle, so `box_size`, `box_scale`,
`local_from_uv` and `uv_from_local` answer for that rectangle instead. It excludes a crop.

Plain Python over the item's properties, usable from the drawing code and the tests.
"""

FULL = (0.0, 0.0, 1.0, 1.0)
MIN_SIDE = 1e-4        # a crop narrower than this share of the image is refused


def stored_crop(item):
    """The crop of an item: its rectangle of the image, the whole image without one."""
    if getattr(item, 'item_type', 'IMAGE') != 'IMAGE' or not getattr(item, 'crop_enabled', False):
        return FULL
    return tuple(item.crop_uv)


def corrected(item):
    """The straightened rectangle of an item whose perspective is corrected (see
    `perspective.state`), else None."""
    if getattr(item, 'item_type', 'IMAGE') != 'IMAGE' or not getattr(item, 'persp_enabled', False):
        return None
    from . import perspective
    return perspective.state(item)


def shown_crop(item):
    """What is drawn: the crop, or the whole image while the mask or the color markup is
    being edited."""
    if corrected(item) is not None:
        return FULL
    if getattr(item, 'mask_editing', False) or getattr(item, 'markup_editing', False):
        return FULL
    return stored_crop(item)


def pivot_uv(item):
    """The point of the image that sits at the item's location: the middle of its crop (of
    the rectangle when the perspective is corrected: then it is a point of the straightened
    plane, not of the image)."""
    rectangle = corrected(item)
    if rectangle is not None:
        return rectangle.pivot
    u0, v0, u1, v1 = stored_crop(item)
    return (u0 + u1) * 0.5, (v0 + v1) * 0.5


def box_size(item, width, height):
    """Size, in pixels, of the box of the item: the crop of an image `width` x `height`, or
    the straightened rectangle."""
    rectangle = corrected(item)
    if rectangle is not None:
        from . import perspective
        return perspective.box_size(rectangle)
    u0, v0, u1, v1 = stored_crop(item)
    return width * (u1 - u0), height * (v1 - v0)


def box_scale(item):
    """(sx, sy) that turns the pixels of the whole image into the size of the box on the
    canvas: the item's scales times the share of the image the crop keeps."""
    rectangle = corrected(item)
    if rectangle is not None:
        from . import perspective
        width, height = item.image_data.size
        box_w, box_h = perspective.box_size(rectangle)
        return (item.scale_xy[0] * item.scale_master * box_w / width,
                item.scale_xy[1] * item.scale_master * box_h / height)
    u0, v0, u1, v1 = stored_crop(item)
    return (item.scale_xy[0] * item.scale_master * (u1 - u0),
            item.scale_xy[1] * item.scale_master * (v1 - v0))


def local_from_uv(item, uv, width, height):
    """Offset in pixels of an image point from the pivot, as the item shows it (flips
    mirror the crop in place). Stretch, shear, rotation and place come after."""
    rectangle = corrected(item)
    if rectangle is not None:
        from . import perspective
        point = perspective.uv_to_rect(rectangle, uv)
        if point is None:
            return 0.0, 0.0
        r_u, r_v = perspective.mirrored(rectangle, point, item.flip_h, item.flip_v)
        return (r_u - rectangle.pivot[0]) * rectangle.width, (r_v - rectangle.pivot[1]) * rectangle.height
    u0, v0, u1, v1 = stored_crop(item)
    cu, cv = (u0 + u1) * 0.5, (v0 + v1) * 0.5
    u = (u0 + u1) - uv[0] if item.flip_h else uv[0]
    v = (v0 + v1) - uv[1] if item.flip_v else uv[1]
    return (u - cu) * width, (v - cv) * height


def uv_from_local(item, x, y, width, height):
    """The opposite of `local_from_uv`: the image point `x`, `y` pixels from the pivot."""
    rectangle = corrected(item)
    if rectangle is not None:
        from . import perspective
        r_u = x / rectangle.width + rectangle.pivot[0]
        r_v = y / rectangle.height + rectangle.pivot[1]
        point = perspective.rect_to_uv(
            rectangle, perspective.mirrored(rectangle, (r_u, r_v), item.flip_h, item.flip_v))
        return (0.0, 0.0) if point is None else point
    u0, v0, u1, v1 = stored_crop(item)
    cu, cv = (u0 + u1) * 0.5, (v0 + v1) * 0.5
    u, v = x / width + cu, y / height + cv
    return ((u0 + u1) - u if item.flip_h else u,
            (v0 + v1) - v if item.flip_v else v)


def box_corners_uv(item):
    """The four corners of the box of an item as points of the image (UV): the corners of
    its crop, or the four corners of the rectangle that is straightened."""
    rectangle = corrected(item)
    if rectangle is not None:
        from . import perspective
        u0, v0, u1, v1 = rectangle.bounds
        return [perspective.rect_to_uv(rectangle, p) for p in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
    return corners_uv(stored_crop(item))


def inside_box(item, local_x, local_y):
    """Whether a point `local_x`, `local_y` pixels from the pivot (as `uv_from_local` takes
    it) is inside the box of an item with its perspective corrected, edges included. None
    when the item is not one."""
    rectangle = corrected(item)
    if rectangle is None:
        return None
    from . import perspective
    box_w, box_h = perspective.box_size(rectangle)
    eps = 1e-6
    return abs(local_x) <= box_w * (0.5 + eps) and abs(local_y) <= box_h * (0.5 + eps)


def corners_uv(rect):
    """The four corners of a UV rectangle, from the bottom left, counterclockwise."""
    u0, v0, u1, v1 = rect
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def clamp_rect(rect):
    """A UV rectangle held inside the image, None if it is too small to keep."""
    u0, v0, u1, v1 = rect
    u0, u1 = max(0.0, min(u0, u1)), min(1.0, max(u0, u1))
    v0, v1 = max(0.0, min(v0, v1)), min(1.0, max(v0, v1))
    if u1 - u0 < MIN_SIDE or v1 - v0 < MIN_SIDE:
        return None
    return u0, v0, u1, v1


def set_crop(item, rect):
    """Crop an item to a UV rectangle (None clears the crop) without moving what it
    shows: its location goes to the new middle, wherever that is on the canvas now.
    Returns False when the rectangle is too small or the image has no size."""
    from .arrow_geometry import image_point_from_uv
    if rect is not None and getattr(item, 'persp_enabled', False):
        return False         # a straightened image cannot be cropped
    if rect is not None:
        rect = clamp_rect(rect)
        if rect is None:
            return False
        if all(abs(a - b) < 1e-6 for a, b in zip(rect, FULL)):
            rect = None
    pivot = (0.5, 0.5) if rect is None else ((rect[0] + rect[2]) * 0.5, (rect[1] + rect[3]) * 0.5)
    point = image_point_from_uv(item, pivot)      # under the crop the item has now
    if point is None:
        return False
    from ..properties import suspend_frame_geometry_updates, update_frame_geometry
    import bpy
    with suspend_frame_geometry_updates():
        if rect is None:
            item.crop_enabled = False
            item.crop_uv = FULL
        else:
            item.crop_uv = rect
            item.crop_enabled = True
        item.location = point
    update_frame_geometry(item, bpy.context)       # a frame around it fits the new box
    return True
