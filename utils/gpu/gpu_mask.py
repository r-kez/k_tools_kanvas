"""GPU mask textures built from UV brush marks stored on image instances."""

import bpy
import gpu
import math
import numpy as np
from ..hidden_datablocks import hidden_name
from itertools import islice


_mask_cache = {}


def _apply_coverage(pixels, coverage, erase):
    if erase:
        np.minimum(pixels, 1.0 - coverage, out=pixels)
    else:
        np.maximum(pixels, coverage, out=pixels)


def mask_dimensions(image):
    width, height = max(1, image.size[0]), max(1, image.size[1])
    scale = min(1.0, 512.0 / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


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
    width, height = mask_dimensions(item.image_data)
    signature = (item.mask_revision, len(item.mask_dabs),
                 len(item.mask_polygons), width, height)
    cached = _mask_cache.get(key)
    if cached and cached['signature'] == signature:
        return cached['texture']

    same_size = cached and cached['signature'][3:] == (width, height)
    if same_size:
        old_revision, old_count, old_polygon_count = cached['signature'][:3]
        append_only = (len(item.mask_dabs) > old_count
                       and not item.mask_polygons and not old_polygon_count
                       and item.mask_revision - old_revision == len(item.mask_dabs) - old_count)
        pixels = rasterize_mask(item.mask_dabs, width, height,
                                cached['pixels'] if append_only else None,
                                old_count if append_only else 0,
                                polygons=() if append_only else item.mask_polygons)
        image = cached['image']
        rgba = cached['rgba']
    else:
        if cached:
            old_image = cached['image']
            if old_image.name in bpy.data.images:
                bpy.data.images.remove(old_image)
        pixels = rasterize_mask(item.mask_dabs, width, height,
                                polygons=item.mask_polygons)
        rgba = np.empty((height, width, 4), dtype=np.float32)
        rgba[:, :, 3] = 1.0
        image = bpy.data.images.new(
            hidden_name(f"Kanvas Mask {item.item_id[:8]}"), width=width, height=height,
            alpha=True, float_buffer=True,
        )
        image.colorspace_settings.name = 'Non-Color'
    rgba[:, :, :3] = pixels[:, :, None]
    image.pixels.foreach_set(rgba.ravel())
    image.update()
    texture = gpu.texture.from_image(image)
    texture.filter_mode(True)
    _mask_cache[key] = {'signature': signature, 'image': image,
                        'texture': texture, 'pixels': pixels, 'rgba': rgba}
    return texture


def clear_mask_cache():
    for cached in tuple(_mask_cache.values()):
        image = cached['image']
        try:
            if image.name in bpy.data.images:
                bpy.data.images.remove(image)
        except (ReferenceError, RuntimeError):
            pass
    _mask_cache.clear()
