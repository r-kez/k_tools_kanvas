"""Task / region names drawn at the center of each painted island."""

import math

import blf
import numpy as np

from ..arrow_geometry import image_point_from_uv
from .gpu_markup import checklist_cards, isolated_index, region_active_mask
from .gpu_mask import mask_dimensions
from .gpu_theme import disable_soft_text_shadow, enable_soft_text_shadow
from .gpu_visibility import image_intersects_view

MIN_ISLAND_FRACTION = 0.003   # of the mask area; ignores brush specks
MIN_ISLAND_PIXELS = 30
MAX_FONT_SIZE = 18.0
MIN_FONT_SIZE = 8.0
MIN_IMAGE_SCREEN_SIZE = 40.0

# (item_id, region_id) -> (mask array the islands were computed from, islands)
_island_cache = {}


def label_islands(mask, threshold=0.05):
    """Connected painted areas as dicts with a center and the text space there.

    Row runs are merged with union-find, so no SciPy is needed.
    """
    solid = mask > threshold
    height, width = solid.shape
    parent = []

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    runs = []
    previous = []
    for y in range(height):
        row = solid[y]
        if not row.any():
            previous = []
            continue
        edges = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
        current = []
        cursor = 0
        for start, end in zip(np.flatnonzero(edges == 1).tolist(),
                              np.flatnonzero(edges == -1).tolist()):
            run_id = len(runs)
            runs.append((y, start, end))
            parent.append(run_id)
            while cursor < len(previous) and previous[cursor][1] <= start:
                cursor += 1
            scan = cursor
            while scan < len(previous) and previous[scan][0] < end:
                a, b = find(run_id), find(previous[scan][2])
                if a != b:
                    parent[max(a, b)] = min(a, b)
                scan += 1
            current.append((start, end, run_id))
        previous = current
    if not runs:
        return []

    labels = np.zeros((height, width), dtype=np.int32)
    names = {}
    stats = {}
    for run_id, (y, start, end) in enumerate(runs):
        root = find(run_id)
        label = names.setdefault(root, len(names) + 1)
        labels[y, start:end] = label
        entry = stats.get(label)
        if entry is None:
            stats[label] = [end - start, y, y + 1, start, end]
        else:
            entry[0] += end - start
            entry[1] = min(entry[1], y)
            entry[2] = max(entry[2], y + 1)
            entry[3] = min(entry[3], start)
            entry[4] = max(entry[4], end)

    minimum = max(MIN_ISLAND_PIXELS, MIN_ISLAND_FRACTION * width * height)
    islands = []
    for label, (area, y0, y1, x0, x1) in stats.items():
        if area < minimum:
            continue
        island = _island_center(labels[y0:y1, x0:x1] == label, x0, y0, width, height)
        if island is not None:
            islands.append(island)
    return islands


def _island_center(sub, x0, y0, width, height):
    """Point deepest inside the island (not the centroid, which can fall outside)."""
    step = max(1, max(sub.shape) // 128)
    coarse = np.pad(sub[::step, ::step], 1)
    deepest = coarse
    while True:
        eroded = (coarse[1:-1, 1:-1] & coarse[:-2, 1:-1] & coarse[2:, 1:-1]
                  & coarse[1:-1, :-2] & coarse[1:-1, 2:])
        eroded = np.pad(eroded, 1)
        if not eroded.any():
            break
        deepest = coarse = eroded
    ys, xs = np.nonzero(deepest)
    if len(ys) == 0:
        return None
    all_y, all_x = np.nonzero(sub)
    centroid_y, centroid_x = all_y.mean(), all_x.mean()
    best = int(np.argmin((ys * step - step - centroid_y) ** 2
                         + (xs * step - step - centroid_x) ** 2))
    py = int(min(sub.shape[0] - 1, max(0, (ys[best] - 1) * step)))
    px = int(min(sub.shape[1] - 1, max(0, (xs[best] - 1) * step)))
    if not sub[py, px]:
        # Subsampling can land on a hole; fall back to the nearest painted pixel.
        nearest = int(np.argmin((all_y - py) ** 2 + (all_x - px) ** 2))
        py, px = int(all_y[nearest]), int(all_x[nearest])
    row, column = sub[py], sub[:, px]
    left = right = px
    while left > 0 and row[left - 1]:
        left -= 1
    while right < len(row) - 1 and row[right + 1]:
        right += 1
    top = bottom = py
    while top > 0 and column[top - 1]:
        top -= 1
    while bottom < len(column) - 1 and column[bottom + 1]:
        bottom += 1
    return {
        'uv': ((x0 + px + 0.5) / width, (y0 + py + 0.5) / height),
        'chord_u': (right - left + 1) / width,
        'chord_v': (bottom - top + 1) / height,
    }


def _islands_for(item, region):
    mask = region_active_mask(item, region)
    if mask is None:
        return []
    key = (item.item_id, region.region_id)
    cached = _island_cache.get(key)
    if cached is not None and cached[0] is mask:
        return cached[1]
    if len(_island_cache) > 512:
        _island_cache.clear()
    islands = label_islands(mask)
    _island_cache[key] = (mask, islands)
    return islands


def region_label_text(cards, region):
    if region.checklist_card_id:
        card = cards.get(region.checklist_card_id)
        if card is not None:
            line = next((line for line in card.text_lines
                         if line.line_id == region.checklist_line_id), None)
            if line is not None and line.value.strip():
                return line.value.strip()
    return region.name.strip()


def _screen_length(view, item, uv_a, uv_b):
    a = view.view_to_region(*image_point_from_uv(item, uv_a), clip=False)
    b = view.view_to_region(*image_point_from_uv(item, uv_b), clip=False)
    return math.hypot(b[0] - a[0], b[1] - a[1])


def draw_markup_labels(settings, region, occluders=()):
    view = region.view2d
    corner_a = view.region_to_view(0, 0)
    corner_b = view.region_to_view(region.width, region.height)
    view_bounds = (min(corner_a[0], corner_b[0]), min(corner_a[1], corner_b[1]),
                   max(corner_a[0], corner_b[0]), max(corner_a[1], corner_b[1]))
    cards = None
    shadow = None
    try:
        for item in settings.images:
            if (item.item_type != 'IMAGE' or not item.image_data
                    or not item.show_in_editor or not item.markup_visible
                    or not item.markup_show_names or item.markup_editing
                    or not item.markup_regions
                    or not image_intersects_view(item, view_bounds)):
                continue
            image_w = _screen_length(view, item, (0.0, 0.5), (1.0, 0.5))
            image_h = _screen_length(view, item, (0.5, 0.0), (0.5, 1.0))
            if min(image_w, image_h) < MIN_IMAGE_SCREEN_SIZE:
                continue
            only = isolated_index(item)
            for index, paint in enumerate(item.markup_regions):
                if (not paint.visible or paint.opacity <= 0
                        or not (paint.dabs or paint.polygons)
                        or (only >= 0 and index != only)):
                    continue
                if cards is None:
                    cards = checklist_cards(settings)
                text = region_label_text(cards, paint)
                if not text:
                    continue
                for island in _islands_for(item, paint):
                    chord_w = island['chord_u'] * image_w
                    chord_h = island['chord_v'] * image_h
                    blf.size(0, 12)
                    base_w, base_h = blf.dimensions(0, text)
                    if base_w <= 0 or base_h <= 0:
                        continue
                    size = min(MAX_FONT_SIZE, 12 * 0.9 * chord_w / base_w,
                               12 * 0.8 * chord_h / base_h)
                    if size < MIN_FONT_SIZE:
                        continue
                    x, y = view.view_to_region(
                        *image_point_from_uv(item, island['uv']), clip=False)
                    if not (0 <= x <= region.width and 0 <= y <= region.height):
                        continue
                    if any(l <= x <= r and b <= y <= t for l, b, r, t in occluders):
                        continue
                    blf.size(0, size)
                    width, height = blf.dimensions(0, text)
                    if shadow is None:
                        shadow = enable_soft_text_shadow((1.0, 1.0, 1.0))
                    blf.color(0, 1.0, 1.0, 1.0, 0.95)
                    blf.position(0, x - width * 0.5, y - height * 0.5, 0)
                    blf.draw(0, text)
    finally:
        if shadow:
            disable_soft_text_shadow()


def clear_label_cache():
    _island_cache.clear()
