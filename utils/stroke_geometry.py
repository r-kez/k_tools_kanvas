"""Stroke geometry for shape outlines: joins, caps and offset outlines.

Pure Python (no bpy, no gpu), so it can be tested anywhere. Points are canvas points.

A stroke is built from pieces that may overlap: one strip per edge (a curved edge is a
single strip, so it stays smooth), one join piece at each vertex between two edges and
a cap at each end of an open path. Every piece comes with its own closed contour for
the anti-aliasing fringe; the fringes of inner seams are drawn first and hidden by the
opaque stroke drawn over them.
"""

import math

JOINS = (
    ('ROUND', 'Round', 'Rounded corners'),
    ('MITER', 'Miter', 'Sharp corners; very sharp ones are cut off (miter limit 4)'),
    ('BEVEL', 'Bevel', 'Corners cut off straight'),
)
CAPS = (
    ('ROUND', 'Round', 'Rounded ends'),
    ('FLAT', 'Flat', 'Ends cut off square at the end point'),
    ('SQUARE', 'Square', 'Ends cut off square, half the line width past the end point'),
)
ALIGNS = (
    ('CENTER', 'Center', 'The line is centered on the outline'),
    ('INSIDE', 'Inside', 'The line lies inside the outline'),
    ('OUTSIDE', 'Outside', 'The line lies outside the outline'),
)
MITER_LIMIT = 4.0
ARC_STEPS = 8


def _unit(dx, dy):
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return None
    return dx / length, dy / length


def _dedupe(points, closed=False):
    result = [p for i, p in enumerate(points) if i == 0 or math.dist(p, points[i - 1]) > 1e-6]
    if closed and len(result) > 1 and math.dist(result[0], result[-1]) <= 1e-6:
        result.pop()
    return result


def signed_area(points):
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1]
                     for a, b in zip(points, points[1:] + points[:1]))


def strip(points, radius):
    """(triangles, contour) of a polyline swept with half width `radius`, flat ends.

    Interior points use the averaged direction, which keeps a flattened curve smooth.
    """
    points = _dedupe(points)
    if len(points) < 2 or radius <= 0:
        return [], []
    left, right = [], []
    for i, point in enumerate(points):
        before = points[max(0, i - 1)]
        after = points[min(len(points) - 1, i + 1)]
        direction = _unit(after[0] - before[0], after[1] - before[1]) or (1.0, 0.0)
        nx, ny = -direction[1], direction[0]
        left.append((point[0] + nx * radius, point[1] + ny * radius))
        right.append((point[0] - nx * radius, point[1] - ny * radius))
    triangles = []
    for i in range(len(points) - 1):
        triangles.extend((left[i], right[i], right[i + 1], left[i], right[i + 1], left[i + 1]))
    return triangles, left + list(reversed(right))


def _arc(center, start, end, radius, sweep_sign):
    """Points from `start` to `end` around `center` (both at `radius`), turning the
    short way in the direction `sweep_sign` (+1 counter-clockwise)."""
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    delta = a1 - a0
    if sweep_sign > 0 and delta < 0:
        delta += math.tau
    elif sweep_sign < 0 and delta > 0:
        delta -= math.tau
    steps = max(1, int(math.ceil(abs(delta) / (math.pi / ARC_STEPS))))
    return [(center[0] + radius * math.cos(a0 + delta * i / steps),
             center[1] + radius * math.sin(a0 + delta * i / steps)) for i in range(steps + 1)]


def join(vertex, incoming, outgoing, radius, kind):
    """(triangles, contour) filling the outer corner where two strips meet at `vertex`.

    `incoming` and `outgoing` are unit directions. Nothing for a straight continuation.
    """
    cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
    dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
    if abs(cross) < 1e-9 and dot > 0:
        return [], []
    side = -1.0 if cross > 0 else 1.0       # the outer side: right of a left turn
    n1 = (-incoming[1] * side, incoming[0] * side)
    n2 = (-outgoing[1] * side, outgoing[0] * side)
    a = (vertex[0] + n1[0] * radius, vertex[1] + n1[1] * radius)
    b = (vertex[0] + n2[0] * radius, vertex[1] + n2[1] * radius)
    if kind == 'ROUND':
        arc = _arc(vertex, a, b, radius, -side)
        triangles = [p for p, q in zip(arc, arc[1:]) for p in (vertex, p, q)]
        return triangles, [vertex] + arc
    if kind == 'MITER':
        bisector = _unit(n1[0] + n2[0], n1[1] + n2[1])
        if bisector is not None:
            cosine = bisector[0] * n1[0] + bisector[1] * n1[1]
            if cosine > 1e-9 and 1.0 / cosine <= MITER_LIMIT:
                reach = radius / cosine
                tip = (vertex[0] + bisector[0] * reach, vertex[1] + bisector[1] * reach)
                return [vertex, a, tip, vertex, tip, b], [vertex, a, tip, b]
    return [vertex, a, b], [vertex, a, b]


def cap(end, direction, radius, kind):
    """(triangles, contour) past the end of an open stroke; `direction` points outwards."""
    if kind == 'FLAT':
        return [], []
    nx, ny = -direction[1], direction[0]
    a = (end[0] + nx * radius, end[1] + ny * radius)
    b = (end[0] - nx * radius, end[1] - ny * radius)
    if kind == 'SQUARE':
        c = (b[0] + direction[0] * radius, b[1] + direction[1] * radius)
        d = (a[0] + direction[0] * radius, a[1] + direction[1] * radius)
        return [a, b, c, a, c, d], [a, b, c, d]
    arc = _arc(end, a, b, radius, -1.0)
    triangles = [p for p, q in zip(arc, arc[1:]) for p in (end, p, q)]
    return triangles, [end] + arc


def edge_pieces(points, edges, closed):
    """Split a contour's points into one polyline per edge (`edges[i]` is the edge of
    point i), each ending on the first point of the next edge."""
    loop = list(points) + ([points[0]] if closed else [])
    labels = list(edges) + ([None] if closed else [])
    pieces, current = [], [loop[0]]
    for i in range(1, len(loop)):
        current.append(loop[i])
        if i == len(loop) - 1 or labels[i] != labels[i - 1]:
            pieces.append(current)
            current = [loop[i]]
    return [piece for piece in pieces if len(piece) >= 2]


def contour_stroke(points, edges, closed, width, join_kind='ROUND', cap_kind='ROUND'):
    """Every (triangles, contour) piece of a solid stroke along one contour."""
    radius = width * 0.5
    pieces = edge_pieces(points, edges, closed)
    parts = [strip(piece, radius) for piece in pieces]
    parts = [part for part in parts if part[0]]

    def direction(a, b):
        return _unit(b[0] - a[0], b[1] - a[1])

    ends = []
    for piece in pieces:
        clean = _dedupe(piece)
        if len(clean) >= 2:
            ends.append((clean, direction(clean[0], clean[1]), direction(clean[-2], clean[-1])))
    count = len(ends)
    for i in range(count if closed else count - 1):
        current, following = ends[i], ends[(i + 1) % count]
        if current[2] is None or following[1] is None:
            continue
        piece = join(current[0][-1], current[2], following[1], radius, join_kind)
        if piece[0]:
            parts.append(piece)
    if not closed and ends:
        first, last = ends[0], ends[-1]
        for point, outward in ((first[0][0], first[1] and (-first[1][0], -first[1][1])),
                               (last[0][-1], last[2])):
            if outward:
                piece = cap(point, outward, radius, cap_kind)
                if piece[0]:
                    parts.append(piece)
    return parts


def dash_stroke(polylines, width, cap_kind='ROUND'):
    """Pieces of a dashed stroke: each dash is a strip with a cap at both ends."""
    radius = width * 0.5
    parts = []
    for dash in polylines:
        clean = _dedupe(dash)
        if len(clean) < 2:
            continue
        body = strip(clean, radius)
        if body[0]:
            parts.append(body)
        start = _unit(clean[0][0] - clean[1][0], clean[0][1] - clean[1][1])
        end = _unit(clean[-1][0] - clean[-2][0], clean[-1][1] - clean[-2][1])
        for point, outward in ((clean[0], start), (clean[-1], end)):
            if outward:
                piece = cap(point, outward, radius, cap_kind)
                if piece[0]:
                    parts.append(piece)
    return parts


def offset_contour(points, distance, closed=True, limit=MITER_LIMIT):
    """The contour moved sideways by `distance` (positive: to the left of its direction).

    Each point moves along the bisector of its two edges, as far as keeps both edges at
    `distance` (a mitered offset), limited to `limit` times the distance. The result has
    exactly one point per input point, so per-point labels still apply.
    """
    points = list(points)
    count = len(points)
    if count < 2:
        return list(points)
    result = []
    for i, point in enumerate(points):
        if closed:
            before, after = points[i - 1], points[(i + 1) % count]
        else:
            before, after = points[max(0, i - 1)], points[min(count - 1, i + 1)]
        d1 = _unit(point[0] - before[0], point[1] - before[1]) if before != point else None
        d2 = _unit(after[0] - point[0], after[1] - point[1]) if after != point else None
        d1, d2 = d1 or d2, d2 or d1
        if d1 is None:
            result.append(point)
            continue
        n1, n2 = (-d1[1], d1[0]), (-d2[1], d2[0])
        bisector = _unit(n1[0] + n2[0], n1[1] + n2[1]) or n1
        cosine = bisector[0] * n1[0] + bisector[1] * n1[1]
        reach = distance / max(cosine, 1.0 / limit)
        result.append((point[0] + bisector[0] * reach, point[1] + bisector[1] * reach))
    return result
