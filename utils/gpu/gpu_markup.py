"""Color markup composited over an image without changing its visibility mask."""

import gpu
import numpy as np

from .gpu_mask import mask_dimensions, rasterize_mask


_markup_cache = {}
_pattern_cache = {}


def linked_card_ids(settings):
    """Checklist cards linked to at least one image (memoized per draw pass)."""
    from .gpu_common import pass_cache
    cache = pass_cache()
    if cache is not None and 'linked_cards' in cache:
        return cache['linked_cards']
    linked = {link.card_id for image in settings.images if image.item_type == 'IMAGE'
              for link in image.checklist_associations}
    if cache is not None:
        cache['linked_cards'] = linked
    return linked


def isolated_index(item):
    """Index of the isolated region, or -1 when every region is shown."""
    region_id = item.markup_isolate_id
    if not region_id:
        return -1
    return next((index for index, region in enumerate(item.markup_regions)
                 if region.region_id == region_id), -1)


def checklist_cards(settings):
    """Checklist cards by item_id, memoized for the current draw pass."""
    from .gpu_common import pass_cache
    cache = pass_cache()
    if cache is not None and 'checklist_cards' in cache:
        return cache['checklist_cards']
    cards = {item.item_id: item for item in settings.images
             if item.item_type == 'TEXT' and item.text_checklist}
    if cache is not None:
        cache['checklist_cards'] = cards
    return cards


def _task_done(cards, region):
    card = cards.get(region.checklist_card_id)
    if card is None:
        return False
    line = next((line for line in card.text_lines
                 if line.line_id == region.checklist_line_id), None)
    return bool(line.done) if line is not None else False


def done_line_opacities(item):
    """Per-region line opacity; 0 where no lines should be drawn.

    Lines only appear for regions linked to a checklist task that is done.
    """
    if not item.markup_show_done_lines or item.markup_done_line_opacity <= 0:
        return ()
    if not any(region.checklist_card_id for region in item.markup_regions):
        return ()
    settings = getattr(item.id_data, 'kanvas_settings', None)
    if settings is None:
        return ()
    cards = checklist_cards(settings)
    return tuple(item.markup_done_line_opacity
                 if region.checklist_card_id and _task_done(cards, region) else 0.0
                 for region in item.markup_regions)


def _done_pattern(width, height):
    """Diagonal lines, spaced relative to the image so they scale with it."""
    key = (width, height)
    pattern = _pattern_cache.get(key)
    if pattern is None:
        period = max(6, round(max(width, height) / 40))
        yy, xx = np.mgrid[0:height, 0:width]
        pattern = (((xx + yy) % period) < max(2, period // 3)).astype(np.float32)
        if len(_pattern_cache) > 16:
            _pattern_cache.clear()
        _pattern_cache[key] = pattern
    return pattern
# Masks for images whose composite texture is not (currently) cached, e.g.
# off-screen images queried by checklist links. Without this they were
# re-rasterized on every redraw.
_mask_cache = {}


def _masks_for_item(real_item, regions, width, height):
    id_data = getattr(real_item, 'id_data', None)
    pointer = id_data.as_pointer() if id_data and hasattr(id_data, 'as_pointer') else id(real_item)
    key = (pointer, real_item.item_id)
    signature = (real_item.markup_revision, width, height,
                 tuple(_region_signature(r) for r in regions))
    cached = _markup_cache.get(key)
    if cached and cached.get('signature') == signature and 'region_masks' in cached:
        return cached['region_masks']
    side = _mask_cache.get(key)
    if side and side['signature'] == signature:
        return side['region_masks']
    base = cached if cached and 'region_masks' in cached else side
    masks = _region_masks(regions, width, height, base)
    _mask_cache[key] = {'signature': signature, 'region_masks': masks}
    return masks


def _effective(region, pixels):
    """Coverage as displayed: the complement when the region is inverted."""
    return 1.0 - pixels if region.inverse else pixels


def rasterize_markup(regions, width, height):
    """Return premultiplied RGBA for the visible, ordered color regions."""
    rgba = np.zeros((height, width, 4), dtype=np.float32)
    for region in regions:
        if not region.visible or region.opacity <= 0:
            continue
        if not region.dabs and not region.polygons:
            continue
        coverage = _effective(region, rasterize_mask(
            region.dabs, width, height, polygons=region.polygons))
        source_alpha = coverage * region.opacity
        remaining = 1.0 - source_alpha
        rgba[:, :, :3] *= remaining[:, :, None]
        rgba[:, :, :3] += source_alpha[:, :, None] * np.asarray(
            region.color[:3], dtype=np.float32)
        rgba[:, :, 3] = rgba[:, :, 3] * remaining + source_alpha
    return rgba


def _region_signature(region):
    return (region.region_id, region.visible, region.inverse,
            tuple(region.color), region.opacity, region.revision, len(region.dabs), len(region.polygons))


def _region_masks(regions, width, height, cached=None):
    old_masks = cached['region_masks'] if cached else ()
    masks = []
    for index, region in enumerate(regions):
        old = old_masks[index] if index < len(old_masks) else None
        dab_count = len(region.dabs)
        polygon_count = len(region.polygons)
        if (old and old['region_id'] == region.region_id
                and old['revision'] == region.revision
                and old['dab_count'] == dab_count
                and old['polygon_count'] == polygon_count):
            pixels = old['pixels']
        elif (old and old['region_id'] == region.region_id
              and polygon_count == old['polygon_count'] == 0
              and dab_count > old['dab_count']
              and region.revision - old['revision'] == dab_count - old['dab_count']):
            pixels = rasterize_mask(region.dabs, width, height,
                                    old['pixels'], start=old['dab_count'])
        else:
            pixels = rasterize_mask(region.dabs, width, height,
                                    polygons=region.polygons)
        masks.append({'region_id': region.region_id,
                      'revision': region.revision, 'dab_count': dab_count,
                      'polygon_count': polygon_count, 'pixels': pixels})
    return masks


def _composite_regions(regions, masks, width, height, lines=(), only=-1):
    rgba = np.zeros((height, width, 4), dtype=np.float32)
    for index, (region, mask) in enumerate(zip(regions, masks)):
        if not region.visible or region.opacity <= 0:
            continue
        if only >= 0 and index != only:
            continue
        coverage = _effective(region, mask['pixels'])
        source_alpha = coverage * region.opacity
        remaining = 1.0 - source_alpha
        rgba[:, :, :3] *= remaining[:, :, None]
        rgba[:, :, :3] += source_alpha[:, :, None] * np.asarray(
            region.color[:3], dtype=np.float32)
        rgba[:, :, 3] = rgba[:, :, 3] * remaining + source_alpha
        if index < len(lines) and lines[index] > 0:
            # Dark diagonal lines inside the painted island, over its color.
            line_alpha = coverage * _done_pattern(width, height) * lines[index]
            rgba[:, :, :3] *= (1.0 - line_alpha)[:, :, None]
            rgba[:, :, 3] = rgba[:, :, 3] * (1.0 - line_alpha) + line_alpha
    return rgba


def _drop_cached(key):
    _markup_cache.pop(key, None)


def markup_texture_for_item(item, force=False):
    """The color markup texture of an image; None when the markup is hidden on the board,
    unless `force` (the 3D View shows it whatever the board does)."""
    if not item.image_data or not (item.markup_visible or force):
        return None
    key = (item.id_data.as_pointer(), item.item_id)
    width, height = mask_dimensions(item.image_data)
    lines = done_line_opacities(item)
    only = isolated_index(item)
    signature = (item.markup_revision, width, height,
                 tuple(_region_signature(region) for region in item.markup_regions),
                 lines, only)
    cached = _markup_cache.get(key)
    if cached and cached['signature'] == signature:
        return cached['texture']
    if not any(region.visible and region.opacity > 0
               and (region.dabs or region.polygons)
               and (only < 0 or index == only)
               for index, region in enumerate(item.markup_regions)):
        _drop_cached(key)
        return None
    same_size = cached and cached['size'] == (width, height)
    masks = _region_masks(item.markup_regions, width, height,
                          cached if same_size else None)
    rgba = _composite_regions(item.markup_regions, masks, width, height, lines, only)
    if not same_size:
        _drop_cached(key)
    # A plain GPU texture, not a bpy image: Blender would flag an image like
    # that as unsaved and ask about it on every save / quit.
    texture = gpu.types.GPUTexture(
        (width, height), format='RGBA8',   # 8 bits a channel is plenty for paint
        data=gpu.types.Buffer('FLOAT', width * height * 4, rgba.ravel()))
    texture.filter_mode(True)
    _markup_cache[key] = {'signature': signature, 'size': (width, height),
                          'texture': texture, 'region_masks': masks}
    return texture


def clear_markup_cache():
    _mask_cache.clear()
    _pattern_cache.clear()
    for key in tuple(_markup_cache):
        _drop_cached(key)


def region_index_at_uv(item, uv, radius=2):
    """Return the index of the top-most visible markup region at (u, v), or None."""
    if uv is None:
        return None
    real_item = getattr(item, '_item', item)
    if not real_item or not getattr(real_item, 'image_data', None):
        return None
    regions = getattr(real_item, 'markup_regions', None)
    if not regions:
        return None
    u, v = uv
    if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
        return None

    width, height = mask_dimensions(real_item.image_data)
    masks = _masks_for_item(real_item, regions, width, height)

    px = int(np.clip(u * width, 0, width - 1))
    py = int(np.clip(v * height, 0, height - 1))

    # Exact pixel match from top-most region down to bottom
    for index in range(len(regions) - 1, -1, -1):
        region = regions[index]
        if not region.visible or region.opacity <= 0:
            continue
        if (index < len(masks)
                and _effective(region, masks[index]['pixels'][py, px]) > 0.05):
            return index

    # Neighborhood match for thin strokes
    if radius > 0:
        y0 = max(0, py - radius)
        y1 = min(height, py + radius + 1)
        x0 = max(0, px - radius)
        x1 = min(width, px + radius + 1)
        for index in range(len(regions) - 1, -1, -1):
            region = regions[index]
            if not region.visible or region.opacity <= 0:
                continue
            if (index < len(masks)
                    and np.any(_effective(region, masks[index]['pixels'][y0:y1, x0:x1]) > 0.05)):
                return index

def region_active_mask(item, region):
    """Return the rasterized 2D float coverage array for a region, or None."""
    real_item = getattr(item, '_item', item)
    if not real_item or not getattr(real_item, 'image_data', None):
        return None
    regions = getattr(real_item, 'markup_regions', None)
    if not regions:
        return None
    width, height = mask_dimensions(real_item.image_data)
    masks = _masks_for_item(real_item, regions, width, height)

    target_id = getattr(region, 'region_id', None)
    for m in masks:
        if m['region_id'] == target_id:
            if not region.inverse:
                return m['pixels']
            # Keep one array per mask version so downstream caches stay valid.
            if 'inverse_pixels' not in m:
                m['inverse_pixels'] = 1.0 - m['pixels']
            return m['inverse_pixels']
    return None
