"""The picture of one image item as it looks on the board, upright and at the image's
own resolution: brightness, contrast, tint, flip and mask kept (color markup if asked),
its place, rotation and scale on the board left out. Stretch and shear are left out
too, unless asked to keep them (they can be edits of the image itself, like a fixed
aspect ratio). Used to send an image to the 3D View as a reference and to export it.

The item is drawn by the canvas code itself, with a model matrix that undoes its
transform: nothing on the item changes, so no frame is resized and no update runs.
The picture can be cropped to what the mask leaves visible, so a masked cutout has no
transparent margin.

Coordinates. "Image space" is the image in pixels as shown (after any flip), centered:
(0, 0) is the middle of the image. The board draws it as
    canvas = location + T @ image_point,   T = rotate @ shear @ stretch * scale.
"Picture space" is the output before scaling: picture = K @ image_point, with K the
part of T the picture keeps (nothing, or stretch and shear), so
    canvas = location + O @ picture,       O = T @ inverse(K).
"""

import math

from .board_render import MAX_SIDE, TILE, _isolated, _render_tile, tiles, unpremultiply

ALPHA_THRESHOLD = 1.0 / 255.0   # mask coverage that still shows in an 8-bit picture
CROP_SIDE = 2048                # resolution the crop is measured at, at most


# --- Geometry --------------------------------------------------------------------------

def _mirrored(item):
    """Whether the shown image is mirrored across x and y: a flip or a negative stretch,
    not both."""
    return (bool(item.flip_h) != (item.scale_xy[0] < 0.0),
            bool(item.flip_v) != (item.scale_xy[1] < 0.0))


def _multiply(m, n):
    return ((m[0][0] * n[0][0] + m[0][1] * n[1][0], m[0][0] * n[0][1] + m[0][1] * n[1][1]),
            (m[1][0] * n[0][0] + m[1][1] * n[1][0], m[1][0] * n[0][1] + m[1][1] * n[1][1]))


def _inverse(m):
    determinant = m[0][0] * m[1][1] - m[0][1] * m[1][0]
    if abs(determinant) < 1e-12:
        return None
    return ((m[1][1] / determinant, -m[0][1] / determinant),
            (-m[1][0] / determinant, m[0][0] / determinant))


def _apply(m, point):
    return (m[0][0] * point[0] + m[0][1] * point[1], m[1][0] * point[0] + m[1][1] * point[1])


def _kept(item, keep_stretch):
    """K: the stretch and shear the picture keeps, in image pixels (identity without)."""
    if not keep_stretch:
        return ((1.0, 0.0), (0.0, 1.0))
    a, b = abs(item.scale_xy[0]), abs(item.scale_xy[1])
    shear_x, shear_y = item.shear_xy
    return ((a, shear_x * b), (shear_y * a, b))


def image_to_canvas(item):
    """T: image space to the canvas (around the item's location). Mirroring is part of
    the image as shown, so only the size of the stretch is used here."""
    a = abs(item.scale_xy[0] * item.scale_master)
    b = abs(item.scale_xy[1] * item.scale_master)
    shear_x, shear_y = item.shear_xy
    angle = math.radians(item.rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    # Stretch, then shear, then rotate: the same order as the canvas drawing.
    return _multiply(((cos_a, -sin_a), (sin_a, cos_a)),
                     ((a, shear_x * b), (shear_y * a, b)))


def uv_to_image(item, u, v):
    """A point of the image (UV, as masks store them) in image space."""
    from .item_crop import stored_crop
    width, height = item.image_data.size
    u0, v0, u1, v1 = stored_crop(item)
    mirror_x, mirror_y = _mirrored(item)
    return (((u0 + u1 - u if mirror_x else u) - (u0 + u1) * 0.5) * width,
            ((v0 + v1 - v if mirror_y else v) - (v0 + v1) * 0.5) * height)


def _mask_coverage(item):
    """The item's mask as a (height, width) float array, rows from the bottom, at the
    texture size the canvas draws (or CROP_SIDE, if smaller): the cached texture
    pixels when they are there, rasterized otherwise."""
    from .gpu import gpu_mask
    side = min(CROP_SIDE, gpu_mask.display_side(item.image_data))
    width, height = gpu_mask._fit(item.image_data, side)
    cached = gpu_mask._mask_cache.get((item.id_data.as_pointer(), item.item_id))
    if cached is not None:
        pixels = cached['pixels']
        signature = cached['signature']
        if signature[:3] == (item.mask_revision, len(item.mask_dabs), len(item.mask_polygons)):
            return pixels
    return gpu_mask.rasterize_mask(item.mask_dabs, width, height, polygons=item.mask_polygons)


def visible_uv_rect(item):
    """(u0, v0, u1, v1) of the part of the image the mask leaves visible: the texels
    with any coverage, soft edge included. The whole image without a mask, None when
    the mask hides everything."""
    if not item.mask_enabled:
        return 0.0, 0.0, 1.0, 1.0
    import numpy as np
    pixels = _mask_coverage(item)
    height, width = pixels.shape[:2]
    columns = np.flatnonzero((pixels > ALPHA_THRESHOLD).any(axis=0))
    if columns.size == 0:
        return None
    rows = np.flatnonzero((pixels > ALPHA_THRESHOLD).any(axis=1))
    return (columns[0] / width, rows[0] / height,
            (columns[-1] + 1) / width, (rows[-1] + 1) / height)


def picture_uv_rect(item, crop_to_mask=True):
    """(u0, v0, u1, v1) of what a picture of the item shows: its crop (the whole image
    without one), narrowed to what the mask leaves visible with `crop_to_mask`. None when
    the mask hides everything of it."""
    from .item_crop import stored_crop
    base = stored_crop(item)
    if not crop_to_mask:
        return base
    mask = visible_uv_rect(item)
    if mask is None:
        return None
    u0, v0 = max(base[0], mask[0]), max(base[1], mask[1])
    u1, v1 = min(base[2], mask[2]), min(base[3], mask[3])
    if u1 - u0 < 1e-6 or v1 - v0 < 1e-6:
        return None
    return u0, v0, u1, v1


def _visible_corners(item, crop_to_mask=True):
    """The four corners, in image space, of what the picture shows: the item's crop, or
    the part of it the mask leaves visible. None when the mask hides everything."""
    uv = picture_uv_rect(item, crop_to_mask)
    if uv is None:
        return None
    return [uv_to_image(item, u, v)
            for u, v in ((uv[0], uv[1]), (uv[2], uv[1]), (uv[2], uv[3]), (uv[0], uv[3]))]


def _bounds(points):
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def quad_from_uv(item, uv, keep_stretch=False):
    """(corners, uvs, bounds) of the picture of a UV rectangle (see `picture_quad`)."""
    uvs = [(uv[0], uv[1]), (uv[2], uv[1]), (uv[2], uv[3]), (uv[0], uv[3])]
    kept = _kept(item, keep_stretch)
    corners = [_apply(kept, uv_to_image(item, u, v)) for u, v in uvs]
    return corners, uvs, _bounds(corners)


def picture_quad(item, crop_to_mask=True, keep_stretch=False):
    """What a live reference draws: (corners, uvs, bounds). `corners` are the four
    corners of what shows, in picture space (image pixels around the middle, stretch and
    shear applied when kept), `uvs` the image coordinates at those corners, `bounds`
    (x0, y0, x1, y1) around the corners. None when the mask hides everything."""
    uv = picture_uv_rect(item, crop_to_mask)
    if uv is None:
        return None
    return quad_from_uv(item, uv, keep_stretch)


def visible_canvas_bounds(item):
    """Canvas rectangle around what the mask leaves visible of an image item (the whole
    image without a mask), None when the mask hides everything."""
    corners = _visible_corners(item)
    if corners is None:
        return None
    matrix = image_to_canvas(item)
    x, y = item.location
    return _bounds([(x + c[0], y + c[1]) for c in (_apply(matrix, p) for p in corners)])


def _pixel_rect(item, scale, crop_to_mask, keep_stretch):
    """What the picture shows, in output pixels around the middle of the image, grown
    to whole pixels."""
    corners = _visible_corners(item, crop_to_mask)
    if corners is None:
        return None
    kept = _kept(item, keep_stretch)
    x0, y0, x1, y1 = _bounds([_apply(kept, p) for p in corners])
    x0, y0 = math.floor(x0 * scale + 1e-6), math.floor(y0 * scale + 1e-6)
    x1, y1 = math.ceil(x1 * scale - 1e-6), math.ceil(y1 * scale - 1e-6)
    return x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)


def picture_size(item, scale=1.0, crop_to_mask=True, keep_stretch=False):
    """(width, height) in pixels of the picture `render_item` makes, None when the mask
    hides everything."""
    rect = _pixel_rect(item, scale, crop_to_mask, keep_stretch)
    return None if rect is None else (rect[2] - rect[0], rect[3] - rect[1])


def is_picture_item(item):
    return (item is not None and getattr(item, 'item_type', 'IMAGE') == 'IMAGE'
            and item.image_data is not None
            and item.image_data.size[0] > 0 and item.image_data.size[1] > 0)


# --- Rendering -------------------------------------------------------------------------

def render_item(settings, item, scale=1.0, crop_to_mask=True, include_markup=False,
                keep_stretch=False, bit_depth=8):
    """The picture as a NumPy array (height, width, 4) of uint8, straight alpha, top
    row first (ready for PNG). `scale` is output pixels per image pixel. Full opacity:
    the item's opacity on the board is left out. `keep_stretch` keeps the item's stretch
    and shear (a sheared image comes out as a slanted shape with clear corners). Raises
    ValueError when the mask hides everything or the picture would be larger than
    MAX_SIDE. `bit_depth` 16 gives a uint16 picture (see `board_render._render_tile`)."""
    import numpy as np
    from mathutils import Matrix
    from .item_geometry import item_bounds
    if not is_picture_item(item):
        raise ValueError('Not an image item')
    rect = _pixel_rect(item, scale, crop_to_mask, keep_stretch)
    if rect is None:
        raise ValueError('The mask hides the whole image')
    x0, y0, x1, y1 = rect
    width, height = x1 - x0, y1 - y0
    if max(width, height) > MAX_SIDE:
        raise ValueError(f'{width} x {height} px is larger than {MAX_SIDE} px on a side')

    kept_inverse = _inverse(_kept(item, keep_stretch))
    board = _multiply(image_to_canvas(item), kept_inverse) if kept_inverse else None
    to_picture = _inverse(board) if board else None
    if to_picture is None:
        raise ValueError('The image has no area on the board')
    # Canvas -> output pixels: undo the board part of the transform, then scale.
    (i00, i01), (i10, i11) = [[value * scale for value in row] for row in to_picture]
    lx, ly = item.location
    model = Matrix(((i00, i01, 0.0, -i00 * lx - i01 * ly),
                    (i10, i11, 0.0, -i10 * lx - i11 * ly),
                    (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
    (m00, m01), (m10, m11) = board
    view_bounds = item_bounds(item)
    stretch = min(math.hypot(m00, m10), math.hypot(m01, m11))
    pixel_size = max(1e-9, stretch / scale)   # canvas units under one output pixel

    picture = np.zeros((height, width, 4), dtype=np.uint16 if bit_depth == 16 else np.uint8)
    item_id = item.item_id
    saved = (item.opacity, item.markup_visible)
    with _isolated(settings, ([item], [])):
        item = next(i for i in settings.images if i.item_id == item_id)
        item.opacity = 1.0
        item.markup_visible = bool(include_markup and item.markup_regions)
        try:
            for x, y, w, h in tiles(width, height, TILE):
                left, bottom = x0 + x, y0 + y
                projection = Matrix(((2.0 / w, 0, 0, -1 - 2.0 * left / w),
                                     (0, 2.0 / h, 0, -1 - 2.0 * bottom / h),
                                     (0, 0, 1, 0), (0, 0, 0, 1)))
                picture[y:y + h, x:x + w] = _render_tile(
                    settings, None, 0, view_bounds, pixel_size, w, h, (0.0, 0.0, 0.0, 0.0),
                    projection, model, labels=False, bit_depth=bit_depth)
        finally:
            item = next(i for i in settings.images if i.item_id == item_id)
            item.opacity, item.markup_visible = saved
    return unpremultiply(picture[::-1])
