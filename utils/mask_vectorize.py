"""Turn a boolean mask into simplified polygons (outer contours and holes).

Pure NumPy, no OpenCV. Contours follow pixel edges, so they match the raster the
mask/markup systems rebuild from polygons exactly, before simplification.
"""

import numpy as np


def resize_mask(mask, height, width):
    """Nearest-neighbour resample of a boolean mask to (height, width)."""
    src_h, src_w = mask.shape
    if (src_h, src_w) == (height, width):
        return mask
    ys = np.minimum(((np.arange(height) + 0.5) * src_h / height).astype(int), src_h - 1)
    xs = np.minimum(((np.arange(width) + 0.5) * src_w / width).astype(int), src_w - 1)
    return mask[ys][:, xs]


def _boundary_loops(mask):
    """Closed loops of pixel-corner vertices, with the inside on their left.

    Outer boundaries come out counter-clockwise (positive area) and holes
    clockwise (negative area).
    """
    padded = np.pad(mask, 1)
    inner = padded[1:-1, 1:-1]
    below, above = padded[:-2, 1:-1], padded[2:, 1:-1]
    left, right = padded[1:-1, :-2], padded[1:-1, 2:]
    edges = {}

    def add(ys, xs, dx0, dy0, dx1, dy1):
        for y, x in zip(ys.tolist(), xs.tolist()):
            edges.setdefault((x + dx0, y + dy0), []).append((x + dx1, y + dy1))

    ys, xs = np.nonzero(inner & ~below)   # bottom edge, heading +x
    add(ys, xs, 0, 0, 1, 0)
    ys, xs = np.nonzero(inner & ~right)   # right edge, heading +y
    add(ys, xs, 1, 0, 1, 1)
    ys, xs = np.nonzero(inner & ~above)   # top edge, heading -x
    add(ys, xs, 1, 1, 0, 1)
    ys, xs = np.nonzero(inner & ~left)    # left edge, heading -y
    add(ys, xs, 0, 1, 0, 0)

    loops = []
    while edges:
        start = next(iter(edges))
        loop = [start]
        current = start
        while True:
            targets = edges[current]
            following = targets.pop()
            if not targets:
                del edges[current]
            if following == start:
                break
            loop.append(following)
            current = following
            if current not in edges:
                break
        loops.append(loop)
    return loops


def _signed_area(points):
    total = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return total * 0.5


def _drop_collinear(points):
    if len(points) < 4:
        return points
    result = []
    count = len(points)
    for index, point in enumerate(points):
        previous = points[index - 1]
        following = points[(index + 1) % count]
        cross = ((point[0] - previous[0]) * (following[1] - point[1])
                 - (point[1] - previous[1]) * (following[0] - point[0]))
        if cross != 0:
            result.append(point)
    return result


def _simplify_open(points, tolerance):
    """Iterative Douglas-Peucker for an open polyline."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x0, y0), (x1, y1) = points[first], points[last]
        dx, dy = x1 - x0, y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        farthest, index = -1.0, -1
        for i in range(first + 1, last):
            px, py = points[i]
            if length == 0:
                distance = ((px - x0) ** 2 + (py - y0) ** 2) ** 0.5
            else:
                distance = abs(dy * px - dx * py + x1 * y0 - y1 * x0) / length
            if distance > farthest:
                farthest, index = distance, i
        if farthest > tolerance:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [point for point, kept in zip(points, keep) if kept]


def _simplify_closed(points, tolerance):
    if len(points) < 5:
        return points
    # Split at the two points farthest apart so neither end is arbitrary.
    anchor = max(range(len(points)),
                 key=lambda i: (points[i][0] - points[0][0]) ** 2
                 + (points[i][1] - points[0][1]) ** 2)
    first = _simplify_open(points[:anchor + 1], tolerance)
    second = _simplify_open(points[anchor:] + [points[0]], tolerance)
    return first[:-1] + second[:-1]


def mask_to_polygons(mask, min_area=12.0, tolerance=0.7):
    """Polygons for every connected area in `mask`.

    Returns a list of dicts: `points` as (x, y) pixel-corner coordinates where
    x grows with the column and y with the row index, `hole` marking interior
    boundaries, and `area` in pixels. Areas below `min_area` are dropped.
    """
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return []
    polygons = []
    for loop in _boundary_loops(mask):
        area = _signed_area(loop)
        if abs(area) < min_area:
            continue
        points = _simplify_closed(_drop_collinear(loop), tolerance)
        if len(points) < 3 or abs(_signed_area(points)) < min_area * 0.5:
            continue
        polygons.append({'points': points, 'hole': area < 0, 'area': abs(area)})
    return polygons


def polygons_to_uv(polygons, width, height):
    """Same polygons with vertices as UV coordinates (0..1)."""
    return [{'uv': [(x / width, y / height) for x, y in polygon['points']],
             'hole': polygon['hole'], 'area': polygon['area']}
            for polygon in polygons]
