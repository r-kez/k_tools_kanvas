"""Boolean operations between filled outlines: union, difference, intersection and
exclusion.

Pure Python, no bpy. Each operand is a list of closed rings (lists of (x, y) points)
filled with the even-odd rule, so holes come in and go out as rings like any other.

How it works: every edge of both operands is cut where it meets another edge, so the
pieces only touch at their ends; overlapping pieces become one. Each piece is then kept
when the result is filled on exactly one of its two sides, turned so the filled side is
on its left, and the kept pieces are chained into rings. The rings come out counter-
clockwise around filled areas and clockwise around holes, never crossing, so even-odd
and nonzero fill agree on them. Curves must be flattened first: the result is made of
straight edges.
"""

import math

OPERATIONS = {
    'UNION': lambda a, b: a or b,
    'DIFFERENCE': lambda a, b: a and not b,
    'INTERSECT': lambda a, b: a and b,
    'EXCLUDE': lambda a, b: a != b,
}


def _inside(point, rings):
    x, y = point
    inside = False
    for ring in rings:
        count = len(ring)
        for i in range(count):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % count]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def _clean(rings):
    result = []
    for ring in rings:
        ring = [tuple(map(float, p)) for i, p in enumerate(ring)
                if i == 0 or math.dist(p, ring[i - 1]) > 0.0]
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring.pop()
        if len(ring) >= 3:
            result.append(ring)
    return result


def _span(rings):
    xs = [p[0] for ring in rings for p in ring]
    ys = [p[1] for ring in rings for p in ring]
    return max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)


def _segments(rings, owner):
    return [(ring[i], ring[(i + 1) % len(ring)], owner)
            for ring in rings for i in range(len(ring))]


def _split_parameters(segments, tolerance):
    """For each segment, the parameters (0..1) where other segments meet it."""
    cuts = [{0.0, 1.0} for _ in segments]
    order = sorted(range(len(segments)),
                   key=lambda i: min(segments[i][0][0], segments[i][1][0]))
    active = []
    for i in order:
        a, b, _ = segments[i]
        min_x = min(a[0], b[0])
        active = [j for j in active if max(segments[j][0][0], segments[j][1][0]) >= min_x - tolerance]
        for j in active:
            _intersect(segments, cuts, i, j, tolerance)
        active.append(i)
    return cuts


def _intersect(segments, cuts, i, j, tolerance):
    p, p2, _ = segments[i]
    q, q2, _ = segments[j]
    if (min(p[1], p2[1]) > max(q[1], q2[1]) + tolerance
            or min(q[1], q2[1]) > max(p[1], p2[1]) + tolerance):
        return
    r = (p2[0] - p[0], p2[1] - p[1])
    s = (q2[0] - q[0], q2[1] - q[1])
    rr, ss = r[0] * r[0] + r[1] * r[1], s[0] * s[0] + s[1] * s[1]
    if rr < 1e-30 or ss < 1e-30:
        return
    denominator = r[0] * s[1] - r[1] * s[0]
    qp = (q[0] - p[0], q[1] - p[1])
    length_r, length_s = math.sqrt(rr), math.sqrt(ss)
    if abs(denominator) <= 1e-12 * length_r * length_s:
        # Parallel: only collinear overlaps matter.
        if abs(qp[0] * r[1] - qp[1] * r[0]) / length_r > tolerance:
            return
        for point, target, base, direction, squared in (
                (q, i, p, r, rr), (q2, i, p, r, rr), (p, j, q, s, ss), (p2, j, q, s, ss)):
            t = ((point[0] - base[0]) * direction[0] + (point[1] - base[1]) * direction[1]) / squared
            if -1e-12 < t < 1.0 + 1e-12:
                cuts[target].add(min(1.0, max(0.0, t)))
        return
    t = (qp[0] * s[1] - qp[1] * s[0]) / denominator
    u = (qp[0] * r[1] - qp[1] * r[0]) / denominator
    slack_t, slack_u = tolerance / length_r, tolerance / length_s
    if -slack_t <= t <= 1.0 + slack_t and -slack_u <= u <= 1.0 + slack_u:
        cuts[i].add(min(1.0, max(0.0, t)))
        cuts[j].add(min(1.0, max(0.0, u)))


def boolean(subject, clip, operation):
    """Rings of `operation` ('UNION', 'DIFFERENCE', 'INTERSECT' or 'EXCLUDE') applied to
    two even-odd filled sets of rings. DIFFERENCE is subject minus clip."""
    keep = OPERATIONS[operation]
    subject, clip = _clean(subject), _clean(clip)
    if not subject and not clip:
        return []
    span = _span(subject + clip)
    tolerance = span * 1e-9
    grid = span * 1e-7
    segments = _segments(subject, 0) + _segments(clip, 1)
    cuts = _split_parameters(segments, tolerance)

    points = {}

    def key(point):
        k = (round(point[0] / grid), round(point[1] / grid))
        points.setdefault(k, point)
        return k

    pieces = {}
    for (a, b, _owner), parameters in zip(segments, cuts):
        previous = None
        for t in sorted(parameters):
            k = key((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            if previous is not None and k != previous:
                pieces.setdefault((min(previous, k), max(previous, k)), None)
            previous = k

    offset = span * 1e-6
    directed = []
    for ka, kb in pieces:
        a, b = points[ka], points[kb]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length <= 0.0:
            continue
        step = min(offset, length * 0.25)
        nx, ny = -dy / length * step, dx / length * step
        mx, my = (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5
        left, right = (mx + nx, my + ny), (mx - nx, my - ny)
        filled_left = keep(_inside(left, subject), _inside(left, clip))
        filled_right = keep(_inside(right, subject), _inside(right, clip))
        if filled_left == filled_right:
            continue
        directed.append((ka, kb) if filled_left else (kb, ka))
    return _chain(directed, points)


def _chain(edges, points):
    """Join directed edges (filled side on the left) into rings. Where several edges
    leave one point, the ring takes the sharpest left turn, so rings that only touch at
    a point stay apart."""
    outgoing = {}
    for index, (start, _end) in enumerate(edges):
        outgoing.setdefault(start, []).append(index)
    used = [False] * len(edges)
    rings = []

    def heading(index):
        a, b = points[edges[index][0]], points[edges[index][1]]
        return math.atan2(b[1] - a[1], b[0] - a[0])

    for first in range(len(edges)):
        if used[first]:
            continue
        ring_keys = []
        current = first
        while True:
            used[current] = True
            start, end = edges[current]
            ring_keys.append(start)
            if end == edges[first][0]:
                break
            candidates = [i for i in outgoing.get(end, ()) if not used[i]]
            if not candidates:
                ring_keys = []   # an open chain: numerical trouble, drop it
                break
            incoming = heading(current)

            def turn(index):
                angle = heading(index) - incoming
                angle = (angle + math.pi) % math.tau - math.pi
                return angle if angle > -math.pi + 1e-12 else -math.pi  # going back: last

            current = max(candidates, key=turn)
        ring = _drop_collinear([points[k] for k in ring_keys])
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def _drop_collinear(ring):
    if len(ring) < 3:
        return ring
    span = _span([ring])
    result = []
    count = len(ring)
    for i, point in enumerate(ring):
        a, b = ring[i - 1], ring[(i + 1) % count]
        cross = (point[0] - a[0]) * (b[1] - a[1]) - (point[1] - a[1]) * (b[0] - a[0])
        length = math.dist(a, b)
        if length > 0 and abs(cross) / length <= span * 1e-9:
            dot = (point[0] - a[0]) * (b[0] - a[0]) + (point[1] - a[1]) * (b[1] - a[1])
            if 0.0 <= dot <= length * length:
                continue   # on the straight line between its neighbours
        result.append(point)
    return result


def rings_cross(rings):
    """True when any two edges of the rings cross, overlap or touch, other than two
    neighbouring edges of one ring meeting at their shared vertex. Sharing a vertex
    between rings, or a ring touching itself, counts as crossing too."""
    segments = []
    for number, ring in enumerate(rings):
        count = len(ring)
        for i in range(count):
            segments.append((ring[i], ring[(i + 1) % count], number, i, count))
    order = sorted(range(len(segments)), key=lambda k: min(segments[k][0][0], segments[k][1][0]))

    def orient(a, b, c):
        value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(value) < 1e-18 else (1 if value > 0 else -1)

    def on_segment(a, b, c):
        return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
                and min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

    active = []
    for k in order:
        p, p2, ring_k, index_k, count_k = segments[k]
        min_x = min(p[0], p2[0])
        active = [j for j in active if max(segments[j][0][0], segments[j][1][0]) >= min_x]
        for j in active:
            q, q2, ring_j, index_j, count_j = segments[j]
            if max(p[1], p2[1]) < min(q[1], q2[1]) or max(q[1], q2[1]) < min(p[1], p2[1]):
                continue
            neighbours = ring_k == ring_j and (
                (index_k - index_j) % count_k in (1, count_k - 1))
            o1, o2 = orient(p, p2, q), orient(p, p2, q2)
            o3, o4 = orient(q, q2, p), orient(q, q2, p2)
            if neighbours:
                # Only folding back onto each other counts.
                if o1 == o2 == o3 == o4 == 0:
                    shared = p if p in (q, q2) else p2
                    far_k = p2 if shared == p else p
                    far_j = q2 if shared == q else q
                    dot = ((far_k[0] - shared[0]) * (far_j[0] - shared[0])
                           + (far_k[1] - shared[1]) * (far_j[1] - shared[1]))
                    if dot > 0:
                        return True
                continue
            if o1 * o2 < 0 and o3 * o4 < 0:
                return True
            if ((o1 == 0 and on_segment(p, p2, q)) or (o2 == 0 and on_segment(p, p2, q2))
                    or (o3 == 0 and on_segment(q, q2, p)) or (o4 == 0 and on_segment(q, q2, p2))):
                return True
        active.append(k)
    return False


def combine(rings_list, operation):
    """Apply an operation across several operands, in order: union, intersection and
    exclusion of all of them, or the first one minus all the others."""
    if not rings_list:
        return []
    result = _clean(rings_list[0])
    for rings in rings_list[1:]:
        result = boolean(result, rings, operation)
    return result


def area(rings):
    """Filled area of even-odd rings (as `boolean` returns them, signed areas add up)."""
    total = 0.0
    for ring in rings:
        total += 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1]))
    return total
