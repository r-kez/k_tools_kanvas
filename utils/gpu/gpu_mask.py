"""GPU mask textures built from UV brush marks stored on image instances."""

import gpu
import math
import numpy as np
from itertools import islice


_mask_cache = {}


def _apply_coverage(pixels, coverage, erase):
    if erase:
        np.minimum(pixels, 1.0 - coverage, out=pixels)
    else:
        np.maximum(pixels, coverage, out=pixels)


ANALYSIS_SIZE = 512      # masks read on the CPU: color names, checklist arrows, Auto Select
PREVIEW_SIZE = 1024      # the mask shown while it is being painted
MAX_DISPLAY_SIZE = 4096


def _fit(image, side):
    width, height = max(1, image.size[0]), max(1, image.size[1])
    scale = min(1.0, side / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def mask_dimensions(image):
    """Size of the masks the add-on reads on the CPU (and of color markup for now):
    512 on the longer side, which is plenty for finding islands and picking."""
    return _fit(image, ANALYSIS_SIZE)


def display_side(image):
    """Longer side of the mask texture drawn on the canvas, from the Mask Resolution
    preference ('IMAGE': the image itself, up to MAX_DISPLAY_SIZE)."""
    from .gpu_common import get_prefs
    prefs = get_prefs()
    choice = getattr(prefs, 'mask_resolution', 'IMAGE') if prefs else 'IMAGE'
    if choice == 'IMAGE':
        return min(MAX_DISPLAY_SIZE, max(1, image.size[0], image.size[1]))
    return int(choice)


def display_dimensions(item):
    """Size of an item's mask texture: the preference, or the lighter preview while
    the mask is being painted (it is rebuilt at full size when you leave)."""
    side = display_side(item.image_data)
    if getattr(item, 'mask_editing', False):
        side = min(side, PREVIEW_SIZE)
    return _fit(item.image_data, side)


def _rasterize_polygon(polygon, pixels, width, height):
    vertices = [(vertex.uv[0] * width, vertex.uv[1] * height)
                for vertex in polygon.vertices]
    if len(vertices) < 3:
        return
    x0 = max(0, math.floor(min(point[0] for point in vertices)) - 1)
    x1 = min(width, math.ceil(max(point[0] for point in vertices)) + 1)
    y0 = max(0, math.floor(min(point[1] for point in vertices)) - 1)
    y1 = min(height, math.ceil(max(point[1] for point in vertices)) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    xx, yy = xx + 0.5, yy + 0.5
    inside = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    edge_distance_squared = np.full(inside.shape, np.inf, dtype=np.float32)
    for start, end in zip(vertices, vertices[1:] + vertices[:1]):
        ax, ay = start
        bx, by = end
        edge_x, edge_y = bx - ax, by - ay
        edge_length_squared = edge_x * edge_x + edge_y * edge_y
        if edge_length_squared > 1e-12:
            projection = np.clip(((xx - ax) * edge_x + (yy - ay) * edge_y)
                                 / edge_length_squared, 0.0, 1.0)
            distance_squared = ((xx - ax - projection * edge_x) ** 2
                                + (yy - ay - projection * edge_y) ** 2)
            np.minimum(edge_distance_squared, distance_squared,
                       out=edge_distance_squared)
        if ay == by:
            continue
        inside ^= ((ay > yy) != (by > yy)) & (
            xx < (bx - ax) * (yy - ay) / (by - ay) + ax)
    distance = np.sqrt(edge_distance_squared)
    coverage = np.clip(np.where(inside, distance, -distance) + 0.5,
                       0.0, 1.0)
    _apply_coverage(pixels[y0:y1, x0:x1], coverage, polygon.erase)


def rasterize_mask(dabs, width, height, pixels=None, start=0, polygons=()):
    """Rasterize reveal/erase marks; the first array row is the bottom UV row."""
    if pixels is None:
        pixels = np.zeros((height, width), dtype=np.float32)
    operations = ([(dab.sequence, index, False, dab)
                   for index, dab in enumerate(islice(dabs, start, None))]
                  + [(polygon.sequence, index, True, polygon)
                     for index, polygon in enumerate(polygons)])
    for _, _, is_polygon, dab in sorted(operations):
        if is_polygon:
            _rasterize_polygon(dab, pixels, width, height)
            continue
        cx, cy = dab.uv[0] * width, dab.uv[1] * height
        axis_x = (dab.uv_axis_x[0] * width, dab.uv_axis_x[1] * height)
        axis_y = (dab.uv_axis_y[0] * width, dab.uv_axis_y[1] * height)
        determinant = axis_x[0] * axis_y[1] - axis_x[1] * axis_y[0]
        affine = abs(determinant) > 1e-8
        if affine:
            rx = math.hypot(axis_x[0], axis_y[0])
            ry = math.hypot(axis_x[1], axis_y[1])
            # The mask texture is capped at 512px. Preserve a visible dab
            # when a small brush becomes smaller than one texel there.
            minimum = min(rx, ry)
            if minimum < 0.75:
                factor = 0.75 / max(minimum, 1e-8)
                axis_x = (axis_x[0] * factor, axis_x[1] * factor)
                axis_y = (axis_y[0] * factor, axis_y[1] * factor)
                determinant *= factor * factor
                rx *= factor
                ry *= factor
        else:
            # Masks saved before round brushes have axis-aligned UV radii.
            rx = max(0.5, dab.radius_uv[0] * width)
            ry = max(0.5, dab.radius_uv[1] * height)
        x0, x1 = max(0, int(cx - rx - 1)), min(width, int(cx + rx + 2))
        y0, y1 = max(0, int(cy - ry - 1)), min(height, int(cy + ry + 2))
        if x0 >= x1 or y0 >= y1:
            continue
        yy, xx = np.ogrid[y0:y1, x0:x1]
        dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
        if affine:
            inv00, inv01 = axis_y[1] / determinant, -axis_y[0] / determinant
            inv10, inv11 = -axis_x[1] / determinant, axis_x[0] / determinant
            local_x = dx * inv00 + dy * inv01
            local_y = dx * inv10 + dy * inv11
            radius_squared = local_x * local_x + local_y * local_y
            gradient_x = 2.0 * (local_x * inv00 + local_y * inv10)
            gradient_y = 2.0 * (local_x * inv01 + local_y * inv11)
        else:
            radius_squared = (dx / rx) ** 2 + (dy / ry) ** 2
            gradient_x = 2.0 * dx / (rx * rx)
            gradient_y = 2.0 * dy / (ry * ry)
        signed_distance = (1.0 - radius_squared) / np.maximum(
            np.hypot(gradient_x, gradient_y), 1e-6)
        coverage = np.clip(signed_distance + 0.5, 0.0, 1.0)
        _apply_coverage(pixels[y0:y1, x0:x1], coverage, dab.erase)
    return pixels


def mask_texture_for_item(item):
    if not item.image_data:
        return None
    key = (item.id_data.as_pointer(), item.item_id)
    width, height = display_dimensions(item)
    signature = (item.mask_revision, len(item.mask_dabs),
                 len(item.mask_polygons), width, height)
    cached = _mask_cache.get(key)
    if cached and cached['signature'] == signature:
        return cached['texture']

    same_size = cached and cached['signature'][3:] == (width, height)
    if same_size:
        old_revision, old_count, old_polygon_count = cached['signature'][:3]
        # New dabs are the newest marks, above every polygon already there, so they
        # can be painted over the old pixels as long as no polygon changed.
        append_only = (len(item.mask_dabs) > old_count
                       and len(item.mask_polygons) == old_polygon_count
                       and item.mask_revision - old_revision == len(item.mask_dabs) - old_count)
        pixels = rasterize_mask(item.mask_dabs, width, height,
                                cached['pixels'] if append_only else None,
                                old_count if append_only else 0,
                                polygons=() if append_only else item.mask_polygons)
    else:
        pixels = rasterize_mask(item.mask_dabs, width, height,
                                polygons=item.mask_polygons)
    # One channel (the shader reads .r): 1 byte a pixel instead of 16. A plain GPU
    # texture, not a bpy image: Blender would flag an image like that as unsaved and
    # ask about it on every save / quit.
    texture = gpu.types.GPUTexture(
        (width, height), format='R8',
        data=gpu.types.Buffer('FLOAT', width * height, pixels.ravel()))
    texture.filter_mode(True)
    _mask_cache[key] = {'signature': signature, 'texture': texture, 'pixels': pixels}
    return texture


def clear_mask_cache():
    _mask_cache.clear()
