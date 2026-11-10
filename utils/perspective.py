"""Perspective correction: an image item whose four chosen corners are straightened into a
rectangle.

The user marks the four corners of something that is a rectangle in the real world (a wall,
a sheet, a screen) as it appears in the photo: `persp_corners` = four points of the image in
UV (as masks store them), in the order bottom left, bottom right, top right, top left of the
*real* rectangle. The corrected item is that rectangle: a box of `width` x `height` pixels
(see `corrected_size`) whose point (r_u, r_v), both from 0 to 1, shows the image at
`H(r_u, r_v)`, with `H` the homography that sends the unit square onto the four corners.

Nothing of the image changes: the texture, the mask, the color markup and the marks stay in
the UV of the original photo, and the shader reads them at `H(r)`. So everything that
already goes through the mapping of `item_crop` (hit tests, snapping, painting a mask,
arrows, frames, the pictures for export and the 3D View) sees the straightened rectangle
by changing that one mapping.

Pure Python: usable from the drawing code and the tests.
"""

import math
from collections import namedtuple

MIN_AREA = 1e-5        # a quadrilateral smaller than this share of the image is no rectangle
MIN_SIDE_PIXELS = 2.0

Corrected = namedtuple('Corrected', 'forward inverse width height')


# --- Homographies ----------------------------------------------------------------------------

def apply(matrix, point):
    """A 3 x 3 matrix (nine floats, row by row) on a point; None at infinity."""
    a, b, c, d, e, f, g, h, i = matrix
    w = g * point[0] + h * point[1] + i
    if abs(w) < 1e-12:
        return None
    return (a * point[0] + b * point[1] + c) / w, (d * point[0] + e * point[1] + f) / w


def invert(matrix):
    """The inverse of a 3 x 3 matrix, None when it has none."""
    a, b, c, d, e, f, g, h, i = matrix
    cofactors = (e * i - f * h, c * h - b * i, b * f - c * e,
                 f * g - d * i, a * i - c * g, c * d - a * f,
                 d * h - e * g, b * g - a * h, a * e - b * d)
    determinant = a * cofactors[0] + b * cofactors[3] + c * cofactors[6]
    if abs(determinant) < 1e-18:
        return None
    return tuple(value / determinant for value in cofactors)


def square_to_quad(quad):
    """The homography that sends (0, 0), (1, 0), (1, 1), (0, 1) to the four points of
    `quad` (Heckbert's closed form). None when the points are degenerate."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    dx1, dx2, dx3 = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, dy3 = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    if abs(dx3) < 1e-12 and abs(dy3) < 1e-12:
        return (x1 - x0, x2 - x1, x0, y1 - y0, y2 - y1, y0, 0.0, 0.0, 1.0)
    determinant = dx1 * dy2 - dx2 * dy1
    if abs(determinant) < 1e-18:
        return None
    g = (dx3 * dy2 - dx2 * dy3) / determinant
    h = (dx1 * dy3 - dx3 * dy1) / determinant
    return (x1 - x0 + g * x1, x3 - x0 + h * x3, x0,
            y1 - y0 + g * y1, y3 - y0 + h * y3, y0,
            g, h, 1.0)


def is_valid_quad(quad, width=1.0, height=1.0):
    """Whether four points (UV) make a convex quadrilateral of some size in an image
    `width` x `height` pixels: no crossed sides, no three points on a line."""
    signs = []
    for index in range(4):
        ax, ay = quad[index]
        bx, by = quad[(index + 1) % 4]
        cx, cy = quad[(index + 2) % 4]
        cross = (bx - ax) * width * (cy - by) * height - (by - ay) * height * (cx - bx) * width
        signs.append(cross)
    if not (all(s > 0 for s in signs) or all(s < 0 for s in signs)):
        return False
    area = 0.0
    for index in range(4):
        ax, ay = quad[index]
        bx, by = quad[(index + 1) % 4]
        area += ax * by - bx * ay
    if abs(area) * 0.5 < MIN_AREA:
        return False
    return min(math.dist((quad[i][0] * width, quad[i][1] * height),
                         (quad[(i + 1) % 4][0] * width, quad[(i + 1) % 4][1] * height))
               for i in range(4)) >= MIN_SIDE_PIXELS


# --- The shape of the rectangle ---------------------------------------------------------------

def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def estimate_ratio(quad, width, height):
    """The width / height of the real rectangle whose picture is `quad` (four UV points,
    bottom left, bottom right, top right, top left), for an image `width` x `height`
    pixels taken by a camera looking at the middle of the image, with square pixels.

    Zhang and He's method ("Whiteboard scanning and image enhancement"): the rectangle
    fixes the focal length of the camera, and with it the proportions. When the picture
    does not allow it (the sides come out parallel, or no camera fits) the proportions of
    the quadrilateral itself are used. None for a degenerate quadrilateral."""
    if not is_valid_quad(quad, width, height):
        return None
    pixels = [(u * width, v * height) for u, v in quad]
    bottom_left, bottom_right, top_right, top_left = pixels
    plain = ((math.dist(bottom_left, bottom_right) + math.dist(top_left, top_right))
             / max(1e-9, math.dist(bottom_left, top_left) + math.dist(bottom_right, top_right)))
    u0, v0 = width * 0.5, height * 0.5
    m1 = (top_left[0] - u0, top_left[1] - v0, 1.0)
    m2 = (top_right[0] - u0, top_right[1] - v0, 1.0)
    m3 = (bottom_left[0] - u0, bottom_left[1] - v0, 1.0)
    m4 = (bottom_right[0] - u0, bottom_right[1] - v0, 1.0)
    try:
        k2 = _dot(_cross(m1, m4), m3) / _dot(_cross(m2, m4), m3)
        k3 = _dot(_cross(m1, m4), m2) / _dot(_cross(m3, m4), m2)
    except ZeroDivisionError:
        return plain
    n2 = tuple(k2 * a - b for a, b in zip(m2, m1))
    n3 = tuple(k3 * a - b for a, b in zip(m3, m1))
    if abs(n2[2]) < 1e-9 or abs(n3[2]) < 1e-9:
        # The sides do not converge: no perspective in that direction, the image
        # proportions of the sides are the real ones.
        ratio = math.hypot(n2[0], n2[1]) / max(1e-9, math.hypot(n3[0], n3[1]))
        return ratio if math.isfinite(ratio) and ratio > 0 else plain
    focal_squared = -((n2[0] * n3[0] + n2[1] * n3[1]) / (n2[2] * n3[2]))
    if not math.isfinite(focal_squared) or focal_squared <= 1e-9:
        return plain
    focal = math.sqrt(focal_squared)
    # Lengths of the two sides in the camera's space: (x / f, y / f, 1) scaled by depth.
    def length_squared(n):
        return (n[0] / focal) ** 2 + (n[1] / focal) ** 2 + n[2] ** 2
    ratio = math.sqrt(length_squared(n2) / max(1e-18, length_squared(n3)))
    return ratio if math.isfinite(ratio) and 0.01 < ratio < 100.0 else plain


def corrected_size(quad, width, height, ratio):
    """(width, height) in pixels of the corrected rectangle: as wide as the quadrilateral's
    sides across are on average, as high as `ratio` (width / height) says."""
    pixels = [(u * width, v * height) for u, v in quad]
    across = (math.dist(pixels[0], pixels[1]) + math.dist(pixels[3], pixels[2])) * 0.5
    ratio = max(1e-3, ratio)
    return across, across / ratio


def build(quad, width, height, ratio=None):
    """Everything the item needs from its corners: `forward` (the rectangle's unit square
    to the image's UV), `inverse`, and the size of the rectangle in pixels. `ratio` is the
    width / height wanted, estimated from the corners when None. None when the corners are
    no good."""
    if width <= 0 or height <= 0 or not is_valid_quad(quad, width, height):
        return None
    if ratio is None:
        ratio = estimate_ratio(quad, width, height)
        if ratio is None:
            return None
    forward = square_to_quad(quad)
    inverse = None if forward is None else invert(forward)
    if forward is None or inverse is None:
        return None
    box_width, box_height = corrected_size(quad, width, height, ratio)
    return Corrected(forward, inverse, box_width, box_height)


# --- The item ------------------------------------------------------------------------------------

DEFAULT_CORNERS = (0.2, 0.2, 0.8, 0.2, 0.8, 0.8, 0.2, 0.8)
_cache = {}


def corner_points(item):
    values = tuple(item.persp_corners)
    return [(values[0], values[1]), (values[2], values[3]),
            (values[4], values[5]), (values[6], values[7])]


def tab_open(window_manager=None):
    import bpy
    window_manager = window_manager or bpy.context.window_manager
    tabs = getattr(window_manager, 'kanvas_tabs', None)
    return tabs is not None and tabs.image == 'PERSPECTIVE'


def editing(item):
    """Whether the corners of the image are being edited: the Perspective tab is open and
    **Edit Corners** is on. The image shows as it is in the photo, with its corners."""
    return (getattr(item, 'item_type', 'IMAGE') == 'IMAGE' and getattr(item, 'persp_editing', False)
            and tab_open())


def editing_item(settings, window_manager):
    """The image whose corners can be dragged on the canvas: the selected active image
    while the Perspective tab is open with **Edit Corners** on. None otherwise."""
    index = settings.active_image_index
    if not 0 <= index < len(settings.images) or not tab_open(window_manager):
        return None
    item = settings.images[index]
    if (item.item_type != 'IMAGE' or not item.is_selected or not item.image_data
            or not item.show_in_editor or not item.persp_editing):
        return None
    return item


HANDLE_PIXELS = 10.0         # how close a click must be to a corner, in screen pixels


def corner_canvas_points(item):
    """The four corners on the canvas (the image as it is in the photo)."""
    from .arrow_geometry import image_point_from_uv
    points = [image_point_from_uv(item, uv) for uv in corner_points(item)]
    return None if any(point is None for point in points) else points


def hit_corner(item, point, pixel_size):
    """Index (0 to 3) of the corner under a canvas point, the nearest one in reach."""
    points = corner_canvas_points(item)
    if points is None:
        return None
    best = min(range(4), key=lambda index: math.dist(point, points[index]))
    return best if math.dist(point, points[best]) <= HANDLE_PIXELS * pixel_size else None


def hit_editable(settings, window_manager, point, pixel_size):
    """(item_id, corner) of the corner of the editable image under a canvas point."""
    item = editing_item(settings, window_manager)
    if item is None:
        return None
    corner = hit_corner(item, point, pixel_size)
    return None if corner is None else (item.item_id, corner)


def set_straightened(item, on):
    """Show the image straightened (or as it is in the photo) without moving the middle of
    the rectangle: the item's location follows. Returns False when it cannot be done (the
    corners are no good, or the image is cropped)."""
    import bpy
    from .arrow_geometry import image_point_from_uv
    if bool(on) == bool(item.persp_enabled):
        item.persp_editing = False
        return True
    built = build_for(item)
    if on and (built is None or item.crop_enabled):
        return False
    from ..properties import suspend_frame_geometry_updates, update_frame_geometry
    middle = apply(built.forward, (0.5, 0.5)) if built is not None else (0.5, 0.5)
    here = tuple(item.location)
    with suspend_frame_geometry_updates():
        if on:
            item.persp_editing = False
            point = image_point_from_uv(item, middle)        # where the middle is in the photo
            item.persp_enabled = True
            if point is not None:
                item.location = point
        else:
            item.persp_enabled = False
            item.persp_editing = False
            point = image_point_from_uv(item, middle)        # where it lands, location unchanged
            if point is not None:
                item.location = (2 * here[0] - point[0], 2 * here[1] - point[1])
    update_frame_geometry(item, bpy.context)
    return True


def estimated_ratio(item):
    image = item.image_data
    if image is None or image.size[0] <= 0:
        return None
    return estimate_ratio(corner_points(item), image.size[0], image.size[1])


def ratio_of(item):
    """The width / height the corrected image has: the estimate, or the number typed."""
    if item.persp_auto:
        return estimated_ratio(item)
    return item.persp_aspect


def state(item):
    """`Corrected` of an item that has its perspective corrected and shown, else None.
    Not shown while its corners, its mask or its color markup are edited, or while it is
    cropped."""
    if getattr(item, 'item_type', 'IMAGE') != 'IMAGE' or not getattr(item, 'persp_enabled', False):
        return None
    if item.crop_enabled or item.mask_editing or item.markup_editing or editing(item):
        return None
    return build_for(item)


def build_for(item):
    """`Corrected` of the item's corners, whether or not it is shown (cached)."""
    image = item.image_data
    if image is None or image.size[0] <= 0 or image.size[1] <= 0:
        return None
    key = (tuple(item.persp_corners), image.size[0], image.size[1],
           bool(item.persp_auto), float(item.persp_aspect))
    pointer = (item.id_data.as_pointer(), item.item_id)
    cached = _cache.get(pointer)
    if cached is None or cached[0] != key:
        built = build(corner_points(item), key[1], key[2],
                      None if item.persp_auto else float(item.persp_aspect))
        cached = (key, built)
        _cache[pointer] = cached
    return cached[1]


def forget(item):
    _cache.pop((item.id_data.as_pointer(), item.item_id), None)


def rect_to_uv(corrected, point):
    """The image's UV at a point (0..1, 0..1) of the corrected rectangle."""
    return apply(corrected.forward, point)


def uv_to_rect(corrected, uv):
    """The point of the corrected rectangle at an image UV."""
    return apply(corrected.inverse, uv)
