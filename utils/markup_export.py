"""Write Color Markup regions to disk as mask images (and an optional ID map)."""

import os
import re

import bpy
import numpy as np

from .gpu.gpu_markup import _effective
from .gpu.gpu_mask import mask_dimensions, rasterize_mask

MAX_EXPORT_EDGE = 4096


def export_dimensions(image, resolution):
    """Pixel size of the exported masks: the capped mask size or the source size."""
    if resolution == 'MASK':
        return mask_dimensions(image)
    width, height = max(1, image.size[0]), max(1, image.size[1])
    scale = min(1.0, MAX_EXPORT_EDGE / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def _safe_name(text):
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', text).strip('_')
    return cleaned or 'region'


def _save_gray(path, width, height, values):
    """Save a (height, width) 0..1 array, first row at the bottom, as an 8-bit PNG."""
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = values[:, :, None]
    _save_rgba(path, width, height, rgba)


def _save_rgba(path, width, height, rgba):
    image = bpy.data.images.new('.kanvas_export', width, height, alpha=True)
    try:
        image.colorspace_settings.name = 'Non-Color'   # keep the stored values exact
        image.pixels.foreach_set(rgba.ravel())
        image.filepath_raw = path
        image.file_format = 'PNG'
        image.save()
    finally:
        bpy.data.images.remove(image)


def export_markup_masks(item, directory, resolution='SOURCE', id_map=True):
    """Export every painted region of `item`; returns the paths written.

    Each region becomes `<image>_<region>.png`: white where the region is painted
    (Inverse is applied) and black elsewhere. With `id_map`, `<image>_ids.png`
    shows every region in its own color, later regions over earlier ones.
    """
    width, height = export_dimensions(item.image_data, resolution)
    os.makedirs(directory, exist_ok=True)
    base = _safe_name(item.name)
    written, used = [], set()
    ids = np.zeros((height, width, 4), dtype=np.float32)
    for region in item.markup_regions:
        if not (region.dabs or region.polygons):
            continue
        coverage = _effective(region, rasterize_mask(
            region.dabs, width, height, polygons=region.polygons))
        name = f'{base}_{_safe_name(region.name)}'
        if name in used:
            suffix = 2
            while f'{name}_{suffix}' in used:
                suffix += 1
            name = f'{name}_{suffix}'
        used.add(name)
        path = os.path.join(directory, name + '.png')
        _save_gray(path, width, height, coverage)
        written.append(path)
        painted = coverage > 0.5
        ids[painted, :3] = region.color[:3]
        ids[painted, 3] = 1.0
    if id_map and written:
        path = os.path.join(directory, f'{base}_ids.png')
        _save_rgba(path, width, height, ids)
        written.append(path)
    return written
