"""Geometry of Kanvas shapes: presets, transforms, hit testing and triangulation.

A shape stores its vertices in a unit box (-0.5..0.5 on both axes). The canvas
position of a vertex is its unit position times the shape size, then the shape's
rotation, then its location. Every preset, and every hand-edited polygon, uses the
same representation, so the kind of a shape can change at any time.

Vertices can carry Bezier handles (see `handle_type`). The outline used to draw,
pick, triangulate, attach arrows and fit the box is the curve flattened into short
segments; a shape whose vertices are all Sharp has exactly its vertices as outline.

A shape can have several contours (a ring, the letter "O", an icon with holes). Each
vertex stores the number of its contour; the vertices of one contour are consecutive
and each contour is a closed loop of its own. The fill uses the even-odd rule: a
contour inside another one is a hole, one inside a hole is filled again, and so on.
A vertex record is (co, type, left, right, contour); four-item records belong to
contour 0.
"""

import math

KINDS = (
    ('RECTANGLE', 'Rectangle', 'Four straight sides', 'MESH_PLANE'),
    ('TRIANGLE', 'Triangle', 'Three straight sides', 'MESH_CONE'),
    ('DIAMOND', 'Diamond', 'Four corners on the middle of each side', 'MESH_CUBE'),
    ('ELLIPSE', 'Ellipse', 'Round shape that fills its box', 'MESH_CIRCLE'),
    ('PENTAGON', 'Pentagon', 'Five equal sides', 'MESH_ICOSPHERE'),
    ('HEXAGON', 'Hexagon', 'Six equal sides', 'MESH_ICOSPHERE'),
    ('STAR', 'Star', 'Five pointed star', 'SOLO_OFF'),
    ('POLYGON', 'Polygon', 'Free vertices; edit them with Edit Vertices', 'EDITMODE_HLT'),
)

DEFAULT_SIZE = (160.0, 120.0)
MIN_SIZE = 4.0
ELLIPSE_SEGMENTS = 48       # vertices of ellipses made before they became curves
# Handle length of a Bezier quarter circle, for a radius of 0.5 (the unit box).
ELLIPSE_HANDLE = 0.5522847498 * 0.5
MIN_VERTICES = 3
CURVE_STEPS = 16            # default segments per curved edge (shape_curve_resolution)
HANDLE_TYPES = (
    ('SHARP', 'Sharp', 'A corner with straight edges', 'HANDLE_VECTOR'),
    ('AUTO', 'Auto', 'A smooth curve worked out from the neighbouring vertices', 'HANDLE_AUTO'),
    ('ALIGNED', 'Aligned', 'A smooth curve: the two handles stay in line', 'HANDLE_ALIGNED'),
    ('MIRRORED', 'Mirrored', 'A smooth curve: the two handles mirror each other, same angle '
     'and same length', 'MOD_MIRROR'),
    ('FREE', 'Free', 'Each handle moves on its own, for a curved corner', 'HANDLE_FREE'),
)


def _regular(sides, start_angle=90.0):
    """Regular polygon stretched to fill the unit box exactly."""
    points = [(math.cos(math.radians(start_angle + 360.0 * i / sides)),
               math.sin(math.radians(start_angle + 360.0 * i / sides)))
              for i in range(sides)]
    return _fit_to_unit_box(points)


def _star(points=5, inner=0.4):
    result = []
    for i in range(points * 2):
        radius = 1.0 if i % 2 == 0 else inner
        angle = math.radians(90.0 + 180.0 * i / points)
        result.append((math.cos(angle) * radius, math.sin(angle) * radius))
    return _fit_to_unit_box(result)


def _fit_to_unit_box(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    cx = (max(xs) + min(xs)) * 0.5
    cy = (max(ys) + min(ys)) * 0.5
    return [((x - cx) / width, (y - cy) / height) for x, y in points]


def preset_records(kind):
    """Unit-box vertex records (co, type, left, right) for a preset kind, or None.

    The ellipse is four Mirrored vertices with Bezier handles: a real curve, so its
    smoothness follows the Curve Resolution and its vertices can be edited. The other
    presets are Sharp corners.
    """
    if kind == 'ELLIPSE':
        k = ELLIPSE_HANDLE
        return [((0.5, 0.0), 'MIRRORED', (0.5, -k), (0.5, k)),
                ((0.0, 0.5), 'MIRRORED', (k, 0.5), (-k, 0.5)),
                ((-0.5, 0.0), 'MIRRORED', (-0.5, k), (-0.5, -k)),
                ((0.0, -0.5), 'MIRRORED', (-k, -0.5), (k, -0.5))]
    vertices = preset_vertices(kind)
    if vertices is None:
        return None
    return [(tuple(v), 'SHARP', tuple(v), tuple(v)) for v in vertices]


def preset_vertices(kind):
    """Unit-box vertex positions for a preset kind, in counter-clockwise order."""
    if kind == 'RECTANGLE':
        return [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    if kind == 'TRIANGLE':
        return [(-0.5, -0.5), (0.5, -0.5), (0.0, 0.5)]
    if kind == 'DIAMOND':
        return [(0.0, -0.5), (0.5, 0.0), (0.0, 0.5), (-0.5, 0.0)]
    if kind == 'ELLIPSE':
        return [(0.5, 0.0), (0.0, 0.5), (-0.5, 0.0), (0.0, -0.5)]
    if kind == 'PENTAGON':
        return _regular(5)
    if kind == 'HEXAGON':
        return _regular(6, 0.0)
    if kind == 'STAR':
        return _star()
    return None


def rotate(point, degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    return point[0] * c - point[1] * s, point[0] * s + point[1] * c


def shape_extent(item):
    """Canvas size of the shape's box (before rotation)."""
    return (item.shape_width * item.scale_master,
            item.shape_height * item.scale_master)


def unit_to_canvas(item, unit):
    width, height = shape_extent(item)
    x, y = rotate((unit[0] * width, unit[1] * height), item.rotation)
    return item.location[0] + x, item.location[1] + y


def canvas_to_unit(item, point):
    width, height = shape_extent(item)
    x, y = rotate((point[0] - item.location[0], point[1] - item.location[1]),
                  -item.rotation)
    return x / max(width, 1e-6), y / max(height, 1e-6)


# --- Bezier curve -----------------------------------------------------------------------

def _lerp(a, b, t):
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def record_contour(record):
    return record[4] if len(record) > 4 else 0


def next_index(records, index):
    """The vertex after `index` in its own contour (the first one after the last)."""
    label = record_contour(records[index])
    if index + 1 < len(records) and record_contour(records[index + 1]) == label:
        return index + 1
    while index > 0 and record_contour(records[index - 1]) == label:
        index -= 1
    return index


def prev_index(records, index):
    """The vertex before `index` in its own contour (the last one before the first)."""
    label = record_contour(records[index])
    if index > 0 and record_contour(records[index - 1]) == label:
        return index - 1
    while index + 1 < len(records) and record_contour(records[index + 1]) == label:
        index += 1
    return index


def contour_ranges(records):
    """(start, stop) vertex index ranges, one per contour, in order."""
    if not records:
        return []
    ranges = []
    start = 0
    for index in range(1, len(records) + 1):
        if (index == len(records)
                or record_contour(records[index]) != record_contour(records[start])):
            ranges.append((start, index))
            start = index
    return ranges


def is_closed(item):
    """False for an open path: its contours do not join their last vertex to the first."""
    return getattr(item, 'shape_closed', True)


def min_vertices(item):
    """Fewest vertices a contour may have: three for a closed outline, two for a line."""
    return MIN_VERTICES if is_closed(item) else 2


def is_closing_edge(records, index):
    """True for the edge that joins the last vertex of a contour back to its first."""
    return next_index(records, index) <= index


def effective_handles(records, closed=True):
    """(left, right) unit handle positions per vertex record (co, type, left, right, ...).

    Sharp: both on the vertex. Auto: along the line between the two neighbours, a sixth
    of that distance each way (a Catmull-Rom curve); at the end of an open path the
    vertex itself stands in for the missing neighbour. Aligned, Mirrored and Free: as
    stored.
    """
    result = []
    for i, record in enumerate(records):
        co, kind = record[0], record[1]
        if kind == 'SHARP':
            result.append((tuple(co), tuple(co)))
        elif kind == 'AUTO':
            before, after = prev_index(records, i), next_index(records, i)
            if not closed:
                before = i if before > i else before
                after = i if after < i else after
            prev = records[before][0]
            nxt = records[after][0]
            dx, dy = (nxt[0] - prev[0]) / 6.0, (nxt[1] - prev[1]) / 6.0
            result.append(((co[0] - dx, co[1] - dy), (co[0] + dx, co[1] + dy)))
        else:
            result.append((tuple(record[2]), tuple(record[3])))
    return result


def item_records(item):
    return [(tuple(v.co), v.handle_type, tuple(v.handle_left), tuple(v.handle_right),
             v.contour) for v in item.shape_vertices]


def item_contour_ranges(item):
    labels = [v.contour for v in item.shape_vertices]
    return contour_ranges([((0.0, 0.0), '', None, None, label) for label in labels])


def segment_controls(records, handles, index):
    """The four unit control points of the edge from vertex `index` to the next one."""
    j = next_index(records, index)
    return (tuple(records[index][0]), handles[index][1], handles[j][0], tuple(records[j][0]))


def is_straight(controls, eps=1e-9):
    p0, p1, p2, p3 = controls
    return (abs(p1[0] - p0[0]) < eps and abs(p1[1] - p0[1]) < eps
            and abs(p2[0] - p3[0]) < eps and abs(p2[1] - p3[1]) < eps)


def cubic(controls, t):
    p0, p1, p2, p3 = controls
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def split_cubic(controls, t):
    """De Casteljau: (left half, right half) of an edge cut at t."""
    p0, p1, p2, p3 = controls
    a, b, c = _lerp(p0, p1, t), _lerp(p1, p2, t), _lerp(p2, p3, t)
    d, e = _lerp(a, b, t), _lerp(b, c, t)
    f = _lerp(d, e, t)
    return (p0, a, d, f), (f, e, c, p3)


def has_curves(item):
    return any(vertex.handle_type != 'SHARP' for vertex in item.shape_vertices)


def uses_curve_resolution(item):
    """True when the Curve Resolution changes how the shape looks: curved edges or
    rounded corners."""
    return has_curves(item) or getattr(item, 'shape_corner_radius', 0.0) > 0.0


_curve_cache = {}


def _plain_curve(item):
    """(units, spans) of the flattened outline before corners are rounded."""
    records = item_records(item)
    closed = is_closed(item)
    curved = any(record[1] != 'SHARP' for record in records)
    steps = max(2, int(getattr(item, 'shape_curve_resolution', CURVE_STEPS))) if curved else 0
    key = item.as_pointer()
    cached = _curve_cache.get(key)
    if cached is not None and cached[0] == (records, steps, closed):
        return cached[1]
    handles = effective_handles(records, closed) if curved else None
    units, spans = [], []
    for start, stop in contour_ranges(records):
        first = len(units)
        for i in range(start, stop):
            if not curved or (not closed and i == stop - 1):
                units.append((tuple(records[i][0]), i, 0.0))
                continue
            controls = segment_controls(records, handles, i)
            units.append((controls[0], i, 0.0))
            if is_straight(controls):
                continue
            for step in range(1, steps):
                t = step / steps
                units.append((cubic(controls, t), i, t))
        spans.append((first, len(units)))
    if len(_curve_cache) > 512:
        _curve_cache.clear()
    _curve_cache[key] = ((records, steps, closed), (units, spans))
    return units, spans


_round_cache = {}


def _curve(item):
    """(units, spans): the flattened outline and the (start, stop) of each contour in it,
    with corners rounded when the shape has a corner radius."""
    plain = _plain_curve(item)
    radius = getattr(item, 'shape_corner_radius', 0.0)
    if radius <= 0.0:
        return plain
    width, height = shape_extent(item)
    key = item.as_pointer()
    signature = (radius, width, height, getattr(item, 'shape_curve_resolution', CURVE_STEPS))
    cached = _round_cache.get(key)
    if cached is not None and cached[0] == signature and cached[2] is plain[0]:
        return cached[1]
    result = _round_corners(item, plain, radius, width, height)
    if len(_round_cache) > 512:
        _round_cache.clear()
    _round_cache[key] = (signature, result, plain[0])
    return result


def _fillet(previous, corner, following, radius, steps_per_quarter=16):
    """Points of the arc that rounds `corner`, from the edge towards `previous` to the
    edge towards `following`, or None when the corner is too flat or too short.

    The radius shrinks when the edges are too short for it: each corner may use at
    most half of each edge, so the arcs of neighbouring corners never overlap.
    """
    a = (previous[0] - corner[0], previous[1] - corner[1])
    b = (following[0] - corner[0], following[1] - corner[1])
    la, lb = math.hypot(*a), math.hypot(*b)
    if la < 1e-9 or lb < 1e-9:
        return None
    a, b = (a[0] / la, a[1] / la), (b[0] / lb, b[1] / lb)
    cosine = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
    angle = math.acos(cosine)                       # inner angle of the corner
    if angle < 1e-3 or angle > math.pi - 1e-3:
        return None
    reach = radius / math.tan(angle * 0.5)          # from the corner to each tangent point
    reach = min(reach, la * 0.5, lb * 0.5)
    radius = reach * math.tan(angle * 0.5)
    start = (corner[0] + a[0] * reach, corner[1] + a[1] * reach)
    end = (corner[0] + b[0] * reach, corner[1] + b[1] * reach)
    bisector = (a[0] + b[0], a[1] + b[1])
    length = math.hypot(*bisector)
    distance = radius / math.sin(angle * 0.5)
    center = (corner[0] + bisector[0] / length * distance,
              corner[1] + bisector[1] / length * distance)
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    turn = (a1 - a0 + math.pi) % math.tau - math.pi  # the short way round
    steps = max(2, int(math.ceil(abs(turn) / (math.pi / 2) * steps_per_quarter)))
    return [(center[0] + radius * math.cos(a0 + turn * k / steps),
             center[1] + radius * math.sin(a0 + turn * k / steps)) for k in range(steps + 1)]


def _round_corners(item, plain, radius, width, height):
    """Replace each Sharp corner between two straight edges by an arc of `radius`
    canvas units. Worked out at the shape's real size, so a stretched shape still gets
    round (not oval) corners; the ends of an open path stay as they are."""
    units, spans = plain
    records = item_records(item)
    closed = is_closed(item)
    sx, sy = max(width, 1e-9), max(height, 1e-9)
    rounded, new_spans = [], []
    for a, b in spans:
        first = len(rounded)
        count = b - a
        for k in range(count):
            unit, edge, t = units[a + k]
            corner = t == 0.0 and records[edge][1] == 'SHARP' and count >= 3
            if corner and not closed and k in (0, count - 1):
                corner = False
            if corner:
                before, after = units[a + (k - 1) % count], units[a + (k + 1) % count]
                corner = before[2] == 0.0 and after[2] == 0.0   # both edges straight
            arc = None
            if corner:
                arc = _fillet((before[0][0] * sx, before[0][1] * sy), (unit[0] * sx, unit[1] * sy),
                              (after[0][0] * sx, after[0][1] * sy), radius,
                              max(2, int(getattr(item, 'shape_curve_resolution', CURVE_STEPS))))
            if arc is None:
                rounded.append((unit, edge, t))
                continue
            rounded.extend(((x / sx, y / sy), edge, 0.0) for x, y in arc)
        new_spans.append((first, len(rounded)))
    return rounded, new_spans


def plain_curve_units(item):
    """`curve_units` without the rounded corners (the outline the vertices describe)."""
    return _plain_curve(item)[0]


def curve_units(item):
    """[(unit point, edge index, t)] along every contour, curves flattened.

    The contours follow each other in the list (`curve_spans` says where each one
    starts). Without curves these are exactly the vertices, with t = 0.
    """
    return _curve(item)[0]


def curve_spans(item):
    """(start, stop) of each contour in `curve_units(item)` and in `outline(item)`."""
    return _curve(item)[1]


def vertex_points(item):
    """Canvas positions of the shape's vertices, in order."""
    return [unit_to_canvas(item, vertex.co) for vertex in item.shape_vertices]


_outline_cache = {}


def outline(item):
    """Canvas points of the shape's outline: the vertices, with curved edges flattened.

    Every contour, one after the other (`curve_spans` says where each one starts); use
    `outlines` for the separate closed loops. Cached until the shape changes, since
    drawing, bounds and picking all ask for it. The list is shared: callers must not
    change it.
    """
    return _outline(item)[0]


def outlines(item):
    """One closed list of canvas points per contour (shared lists: do not change them)."""
    return _outline(item)[1]


def _outline(item):
    units, spans = _curve(item)
    width, height = shape_extent(item)
    key = (id(units), len(units), units[0][0] if units else None,
           tuple(item.location), item.rotation, width, height)
    cached = _outline_cache.get(item.as_pointer())
    if cached is not None and cached[0] == key and cached[2] is units:
        return cached[1]
    angle = math.radians(item.rotation)
    c, s = math.cos(angle), math.sin(angle)
    x0, y0 = item.location
    points = [(x0 + u[0] * width * c - u[1] * height * s,
               y0 + u[0] * width * s + u[1] * height * c) for u, _, _ in units]
    rings = [points[a:b] for a, b in spans] if len(spans) > 1 else [points]
    if len(_outline_cache) > 512:
        _outline_cache.clear()
    _outline_cache[item.as_pointer()] = (key, (points, rings), units)
    return points, rings


def item_handles(item):
    """`effective_handles` of a shape's vertices."""
    return effective_handles(item_records(item), is_closed(item))


def edge_indices(item):
    """Index of the first vertex of every edge (an open path has no closing edges)."""
    records = item_records(item)
    if is_closed(item):
        return list(range(len(records)))
    return [i for i in range(len(records)) if not is_closing_edge(records, i)]


def edge_midpoints(item):
    """Unit point halfway along each edge (on the curve when the edge is curved)."""
    records = item_records(item)
    handles = effective_handles(records, is_closed(item))
    return [cubic(segment_controls(records, handles, i), 0.5) for i in edge_indices(item)]


def handle_points(item, index):
    """(left, right) canvas positions of a vertex's handles."""
    left, right = item_handles(item)[index]
    return unit_to_canvas(item, left), unit_to_canvas(item, right)


def bounds(item):
    """Axis-aligned canvas bounds (left, bottom, right, top) of the rotated shape."""
    points = outline(item)
    if item.shape_kind == 'PENCIL':
        # A Pencil Drawing has no outline: its box is what it occupies.
        points = box_corners(item)
    if not points:
        x, y = item.location
        return x, y, x, y
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def box_corners(item):
    """Canvas corners of the shape's box: bottom-left, bottom-right, top-right, top-left."""
    return [unit_to_canvas(item, corner)
            for corner in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))]


def signed_area(points):
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1]
                     for a, b in zip(points, points[1:] + points[:1]))


def point_in_polygon(point, polygon):
    """Even-odd test."""
    x, y = point
    inside = False
    count = len(polygon)
    for i in range(count):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % count]
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
    return inside


def point_in_contours(point, rings):
    """Even-odd test over several closed contours: inside an odd number of them."""
    inside = False
    for ring in rings:
        if len(ring) >= MIN_VERTICES and point_in_polygon(point, ring):
            inside = not inside
    return inside


def contour_depths(rings):
    """How many other contours hold each contour; an odd depth makes it a hole."""
    depths = []
    for index, ring in enumerate(rings):
        if not ring:
            depths.append(0)
            continue
        probe = ring[0]
        depths.append(sum(1 for other, candidate in enumerate(rings)
                          if other != index and len(candidate) >= MIN_VERTICES
                          and point_in_polygon(probe, candidate)))
    return depths


def segment_distance(point, a, b):
    """(distance, parameter along a->b) from a point to a segment."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return math.dist(point, a), 0.0
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.dist(point, (a[0] + dx * t, a[1] + dy * t)), t


def nearest_edge(points, point, closed=True):
    """(edge index, distance, parameter) of the outline edge closest to a point.

    Without `closed`, the edge from the last point back to the first is left out.
    """
    best = (-1, float('inf'), 0.0)
    count = len(points)
    for i in range(count if closed else count - 1):
        distance, t = segment_distance(point, points[i], points[(i + 1) % count])
        if distance < best[1]:
            best = (i, distance, t)
    return best


def nearest_outline_edge(item, point):
    """(start, end, distance, t) of the outline segment closest to a canvas point.

    `start` and `end` index `outline(item)`; a segment never jumps between contours.
    None for a shape without an outline.
    """
    points = outline(item)
    closed = is_closed(item)
    best = None
    for a, b in curve_spans(item):
        if b - a < 2:
            continue
        index, distance, t = nearest_edge(points[a:b], point, closed)
        if best is None or distance < best[2]:
            start = a + index
            best = (start, start + 1 if start + 1 < b else a, distance, t)
    return best


def stroke_paths(item):
    """(points, edges) per contour along the middle of the line.

    That is the outline itself, or, for a line drawn inside or outside a closed outline,
    the outline moved by half the line width towards that side (holes included: the
    inside of a hole is outside the shape). `edges` gives the edge of each point.
    """
    from .stroke_geometry import offset_contour
    points = outline(item)
    units = curve_units(item)
    closed = is_closed(item)
    align = getattr(item, 'shape_line_align', 'CENTER') if closed else 'CENTER'
    spans = curve_spans(item)
    rings = [points[a:b] for a, b in spans]
    depths = contour_depths(rings) if align != 'CENTER' and len(rings) > 1 else [0] * len(rings)
    half = item.shape_line_width * 0.5
    result = []
    for (a, b), ring, depth in zip(spans, rings, depths):
        if b - a < 2:
            continue
        if align != 'CENTER' and b - a >= MIN_VERTICES:
            filled_on_left = (signed_area(ring) > 0) == (depth % 2 == 0)
            ring = offset_contour(ring, half if (align == 'INSIDE') == filled_on_left else -half)
        result.append((ring, [edge for _, edge, _ in units[a:b]]))
    return result


def hit_shape(item, point, tolerance):
    """True when a canvas point should pick the shape.

    A filled shape is picked anywhere inside it (not inside its holes). A shape without
    a fill is picked only on its outline, so it never blocks the image underneath it.
    """
    if item.shape_kind == 'PENCIL':
        # A Pencil Drawing is picked on its strokes, never on the empty part of its box,
        # so the image under it stays reachable.
        from . import pencil
        return pencil.pick_stroke(item, point, tolerance) is not None
    points = outline(item)
    if len(points) < min_vertices(item):
        return False
    if item.shape_show_fill and item.shape_fill_opacity > 0.0 \
            and point_in_contours(point, outlines(item)):
        return True
    reach = tolerance + (item.shape_line_width * 0.5 if item.shape_show_outline else 0.0)
    nearest = nearest_outline_edge(item, point)
    return nearest is not None and nearest[2] <= reach


def _is_ear(a, b, c, polygon):
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if cross <= 1e-12:
        return False
    for p in polygon:
        if p is a or p is b or p is c:
            continue
        d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
        d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
        d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
        if d1 >= -1e-12 and d2 >= -1e-12 and d3 >= -1e-12:
            return False
    return True


def _tessellate(rings):
    """Triangle index triples from Blender's own polygon filler, or None outside Blender.

    The indices run over the contours one after the other; nested contours are holes.
    """
    try:
        from mathutils import Vector
        from mathutils.geometry import tessellate_polygon
    except ImportError:
        return None
    try:
        return tessellate_polygon([[Vector((x, y, 0.0)) for x, y in ring] for ring in rings])
    except (ValueError, TypeError):
        return None


_triangle_cache = {}


def fill_triangles(item):
    """Index triples into `outline(item)` that fill the shape, cached with the curve.

    Triangulating in the unit box is enough: the box transform (scale, rotation and
    translation, never a mirror) keeps every triangle valid on the canvas.
    """
    units, spans = _curve(item)
    cached = _triangle_cache.get(item.as_pointer())
    if cached is not None and cached[0] is units:
        return cached[1]
    points = [unit for unit, _, _ in units]
    kept = [(a, b) for a, b in spans if b - a >= MIN_VERTICES]
    rings = [points[a:b] for a, b in kept]
    indices = _tessellate(rings) if rings else []
    triangles = []
    if indices:
        # The filler numbers the kept contours one after the other.
        flat = [i for a, b in kept for i in range(a, b)]
        triangles = [(flat[a], flat[b], flat[c]) for a, b, c in indices]
    elif rings:
        # Outside Blender: each filled contour on its own, holes left out.
        for ring, (a, _), depth in zip(rings, kept, contour_depths(rings)):
            if depth % 2:
                continue
            index = {}
            for i, point in enumerate(ring):
                index.setdefault(point, a + i)
            triangles.extend(tuple(index[p] for p in triangle) for triangle in _ear_clip(ring))
    if len(_triangle_cache) > 512:
        _triangle_cache.clear()
    _triangle_cache[item.as_pointer()] = (units, triangles)
    return triangles


def _delaunay_fill(rings):
    """Even-odd fill triangles (point triples) of rings that cross each other or
    themselves, or None outside Blender.

    Blender's polygon filler expects contours that do not cross, and fills crossing
    ones wrongly. Here a constrained Delaunay triangulation (which adds the crossing
    points) covers the whole area, and a flood from the outside flips between filled
    and empty every time it steps over an edge of the outline: exactly the even-odd
    rule, with overlapping edges cancelling out.
    """
    try:
        from mathutils import Vector
        from mathutils.geometry import delaunay_2d_cdt
    except ImportError:
        return None
    from collections import deque
    vertices = [p for ring in rings for p in ring]
    edges, offset = [], 0
    for ring in rings:
        edges.extend((offset + i, offset + (i + 1) % len(ring)) for i in range(len(ring)))
        offset += len(ring)
    try:
        out_vertices, out_edges, faces, _v, origins, _f = delaunay_2d_cdt(
            [Vector(v) for v in vertices], edges, [], 0, 1e-9)
    except (ValueError, TypeError, RuntimeError):
        return None
    crossings = {(min(a, b), max(a, b)): len(found) % 2
                 for (a, b), found in zip(out_edges, origins)}
    owners = {}
    for index, face in enumerate(faces):
        for k in range(len(face)):
            a, b = face[k], face[(k + 1) % len(face)]
            owners.setdefault((min(a, b), max(a, b)), []).append(index)
    parity = [None] * len(faces)
    queue = deque()
    for edge, faces_here in owners.items():
        if len(faces_here) == 1 and parity[faces_here[0]] is None:
            parity[faces_here[0]] = crossings.get(edge, 0)   # stepping in from outside
            queue.append(faces_here[0])
    while queue:
        index = queue.popleft()
        face = faces[index]
        for k in range(len(face)):
            a, b = face[k], face[(k + 1) % len(face)]
            edge = (min(a, b), max(a, b))
            for other in owners[edge]:
                if parity[other] is None:
                    parity[other] = parity[index] ^ crossings.get(edge, 0)
                    queue.append(other)
    triangles = []
    for face, filled in zip(faces, parity):
        if filled:
            points = [tuple(out_vertices[k]) for k in face]
            triangles.extend((points[0], points[k], points[k + 1])
                             for k in range(1, len(points) - 1))
    return triangles


_fill_unit_cache = {}


def fill_unit_triangles(item):
    """The fill as unit-box triangles (point triples), cached with the curve.

    The Shape Fill preference picks the method, the same for every shape so nothing
    changes behind the user's back: Exact (the default) always uses `_delaunay_fill`,
    right for any outline; Fast always uses Blender's polygon filler (`fill_triangles`),
    which fills crossing outlines wrongly. Outside Blender, the polygon filler or ear
    clipping is used.
    """
    units, spans = _curve(item)
    method = fill_method()
    cached = _fill_unit_cache.get(item.as_pointer())
    if cached is not None and cached[0] is units and cached[2] == method:
        return cached[1]
    points = [unit for unit, _, _ in units]
    rings = [points[a:b] for a, b in spans if b - a >= MIN_VERTICES]
    triangles = None
    if rings and method == 'DELAUNAY':
        triangles = _delaunay_fill(rings)
    if triangles is None:
        triangles = [tuple(points[i] for i in triangle) for triangle in fill_triangles(item)]
    if len(_fill_unit_cache) > 512:
        _fill_unit_cache.clear()
    _fill_unit_cache[item.as_pointer()] = (units, triangles, method)
    return triangles


def fill_method():
    """'DELAUNAY' or 'FAST', from the Shape Fill preference ('DELAUNAY' without it)."""
    try:
        from .gpu.gpu_common import get_prefs
        prefs = get_prefs()
    except ImportError:
        return 'DELAUNAY'
    return getattr(prefs, 'shape_fill', 'DELAUNAY') if prefs is not None else 'DELAUNAY'


def fill_canvas_triangles(item):
    """`fill_unit_triangles` placed on the canvas, as a flat list of vertices."""
    width, height = shape_extent(item)
    angle = math.radians(item.rotation)
    c, s = math.cos(angle), math.sin(angle)
    x0, y0 = item.location
    return [(x0 + u[0] * width * c - u[1] * height * s, y0 + u[0] * width * s + u[1] * height * c)
            for triangle in fill_unit_triangles(item) for u in triangle]


def triangulate(points):
    """Triangles (as point triples) covering a polygon.

    Uses Blender's polygon filler when available (fast, and it copes with outlines
    that cross themselves); otherwise ear clipping, falling back to a fan from the
    first vertex when the outline crosses itself, so a badly edited polygon still
    draws something.
    """
    if len(points) < 3:
        return []
    indices = _tessellate([points])
    if indices:
        return [(points[a], points[b], points[c]) for a, b, c in indices]
    return _ear_clip(points)


def _ear_clip(points):
    if len(points) < 3:
        return []
    remaining = list(points)
    if signed_area(remaining) < 0:
        remaining.reverse()
    triangles = []
    guard = len(remaining) * len(remaining)
    while len(remaining) > 3 and guard > 0:
        guard -= 1
        count = len(remaining)
        for i in range(count):
            a, b, c = remaining[i - 1], remaining[i], remaining[(i + 1) % count]
            if _is_ear(a, b, c, remaining):
                triangles.append((a, b, c))
                del remaining[i]
                break
        else:
            return [(points[0], points[i], points[i + 1])
                    for i in range(1, len(points) - 1)]
    if len(remaining) == 3:
        triangles.append(tuple(remaining))
    return triangles


def normalized(vertices, extent=None):
    """Rescale unit vertices so their bounding box is exactly the unit box.

    `extent` are the points that must fill the box (the flattened curve), when they
    differ from the vertices. Returns (vertices, center, span): the new vertices, the
    former box center and the former box size, all in unit coordinates, or None for a
    shape that is a single point. A flat shape (a straight line) keeps its box size
    across the line and is centered in it.
    """
    if not vertices:
        return None
    extent = extent or vertices
    xs = [v[0] for v in extent]
    ys = [v[1] for v in extent]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    if span_x < 1e-6 and span_y < 1e-6:
        return None
    span_x = span_x if span_x >= 1e-6 else 1.0
    span_y = span_y if span_y >= 1e-6 else 1.0
    cx, cy = (max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5
    return ([((x - cx) / span_x, (y - cy) / span_y) for x, y in vertices],
            (cx, cy), (span_x, span_y))


def box_from_drag(origin, current, *, square=False, from_center=False):
    """(center, width, height) of the box drawn by dragging from origin to current."""
    dx, dy = current[0] - origin[0], current[1] - origin[1]
    if square:
        size = max(abs(dx), abs(dy))
        dx = math.copysign(size, dx or 1.0)
        dy = math.copysign(size, dy or 1.0)
    if from_center:
        return origin, abs(dx) * 2.0, abs(dy) * 2.0
    return (origin[0] + dx * 0.5, origin[1] + dy * 0.5), abs(dx), abs(dy)


def gizmo_layout(item, size):
    """Corners, edge midpoints, rotation stem and rotation handle of the shape's box."""
    from .gizmo_geometry import handle_layout
    width, height = shape_extent(item)
    return handle_layout(item.location, width, height, (0.0, 0.0), item.rotation, size)


def hit_vertex(item, point, radius):
    """Index of the vertex within `radius` of a canvas point, or None."""
    best, best_distance = None, radius
    for index, canvas in enumerate(vertex_points(item)):
        distance = math.dist(canvas, point)
        if distance <= best_distance:
            best, best_distance = index, distance
    return best


def hit_edge(item, point, radius):
    """(edge index, curve parameter) of an outline edge within `radius`, or None."""
    units = curve_units(item)
    nearest = nearest_outline_edge(item, point)
    if nearest is None or nearest[2] > radius:
        return None
    index, following, distance, local = nearest
    _, edge, t0 = units[index]
    _, next_edge, t1 = units[following]
    if next_edge != edge:
        t1 = 1.0
    return edge, t0 + (t1 - t0) * local


def hit_handle(item, point, radius, indices):
    """(vertex index, 'left' or 'right') of a visible handle near a canvas point, or None.

    Only the vertices in `indices` (the selected ones) show handles; Sharp ones have none.
    """
    best, best_distance = None, radius
    for index in indices:
        if item.shape_vertices[index].handle_type == 'SHARP':
            continue
        for side, canvas in zip(('left', 'right'), handle_points(item, index)):
            distance = math.dist(canvas, point)
            if distance <= best_distance:
                best, best_distance = (index, side), distance
    return best


def bend_offsets(t, delta):
    """How far the two inner control points move so the curve point at t moves by delta.

    The weighting is the one Inkscape uses when a segment is dragged: near an end only
    that end's handle moves, in the middle both share the pull.
    """
    t = max(0.1, min(0.9, t))
    if t <= 1.0 / 6.0:
        weight = 0.0
    elif t <= 0.5:
        weight = ((6.0 * t - 1.0) / 2.0) ** 3 / 2.0
    elif t <= 5.0 / 6.0:
        weight = (1.0 - ((6.0 * (1.0 - t) - 1.0) / 2.0) ** 3) / 2.0 + 0.5
    else:
        weight = 1.0
    first = (1.0 - weight) / (3.0 * t * (1.0 - t) * (1.0 - t))
    second = weight / (3.0 * t * t * (1.0 - t))
    return ((delta[0] * first, delta[1] * first), (delta[0] * second, delta[1] * second))


# --- arrow anchors ---------------------------------------------------------------------
# An arrow end attached to a shape is stored as a position inside the shape's box, from
# (0, 0) to (1, 1), so it follows the shape when it moves, turns, scales or is resized.

def point_from_uv(item, uv):
    return unit_to_canvas(item, (uv[0] - 0.5, uv[1] - 0.5))


def uv_at(item, point):
    x, y = canvas_to_unit(item, point)
    return x + 0.5, y + 0.5


def anchor_points(item):
    """(uv, canvas point) snap targets: corners and the middle of each side.

    An ellipse has eight, one every 45 degrees: its four vertices and the middle of
    its four curved edges (an ellipse made with the former 48 vertices: every sixth).
    """
    vertices = [tuple(v.co) for v in item.shape_vertices]
    if len(vertices) < min_vertices(item):
        return []
    if item.shape_kind == 'ELLIPSE' and len(vertices) > 8:
        units = vertices[::max(1, len(vertices) // 8)]
    else:
        units = list(vertices) + edge_midpoints(item)
    return [((u[0] + 0.5, u[1] + 0.5), unit_to_canvas(item, u)) for u in units]


def outline_attach(item, point, radius):
    """(uv, canvas point) on the outline nearest to `point`, within `radius`, or None."""
    points = outline(item)
    nearest = nearest_outline_edge(item, point)
    if nearest is None or nearest[2] > radius:
        return None
    index, following, _, t = nearest
    a, b = points[index], points[following]
    onto = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return uv_at(item, onto), onto


def contains(item, point):
    """Inside the filled area (even-odd over every contour, so not inside a hole)."""
    return point_in_contours(point, outlines(item))

