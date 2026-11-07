"""Geometry of Kanvas shapes: presets, transforms, hit testing and triangulation.

A shape stores its vertices in a unit box (-0.5..0.5 on both axes). The canvas
position of a vertex is its unit position times the shape size, then the shape's
rotation, then its location. Every preset, and every hand-edited polygon, uses the
same representation, so the kind of a shape can change at any time.

Vertices can carry Bezier handles (see `handle_type`). The outline used to draw,
pick, triangulate, attach arrows and fit the box is the curve flattened into short
segments; a shape whose vertices are all Sharp has exactly its vertices as outline.
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
ELLIPSE_SEGMENTS = 48
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


def preset_vertices(kind):
    """Unit-box vertices for a preset kind, in counter-clockwise order."""
    if kind == 'RECTANGLE':
        return [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    if kind == 'TRIANGLE':
        return [(-0.5, -0.5), (0.5, -0.5), (0.0, 0.5)]
    if kind == 'DIAMOND':
        return [(0.0, -0.5), (0.5, 0.0), (0.0, 0.5), (-0.5, 0.0)]
    if kind == 'ELLIPSE':
        return [(0.5 * math.cos(math.tau * i / ELLIPSE_SEGMENTS),
                 0.5 * math.sin(math.tau * i / ELLIPSE_SEGMENTS))
                for i in range(ELLIPSE_SEGMENTS)]
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


def effective_handles(records):
    """(left, right) unit handle positions per vertex record (co, type, left, right).

    Sharp: both on the vertex. Auto: along the line between the two neighbours, a sixth
    of that distance each way (a Catmull-Rom curve). Aligned, Mirrored and Free: as stored.
    """
    count = len(records)
    result = []
    for i, (co, kind, left, right) in enumerate(records):
        if kind == 'SHARP':
            result.append((tuple(co), tuple(co)))
        elif kind == 'AUTO':
            prev, nxt = records[i - 1][0], records[(i + 1) % count][0]
            dx, dy = (nxt[0] - prev[0]) / 6.0, (nxt[1] - prev[1]) / 6.0
            result.append(((co[0] - dx, co[1] - dy), (co[0] + dx, co[1] + dy)))
        else:
            result.append((tuple(left), tuple(right)))
    return result


def item_records(item):
    return [(tuple(v.co), v.handle_type, tuple(v.handle_left), tuple(v.handle_right))
            for v in item.shape_vertices]


def segment_controls(records, handles, index):
    """The four unit control points of the edge from vertex `index` to the next one."""
    j = (index + 1) % len(records)
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


_curve_cache = {}


def curve_units(item):
    """[(unit point, edge index, t)] along the closed outline, curves flattened.

    Without curves these are exactly the vertices, with t = 0.
    """
    records = item_records(item)
    curved = any(record[1] != 'SHARP' for record in records)
    steps = max(2, int(getattr(item, 'shape_curve_resolution', CURVE_STEPS))) if curved else 0
    key = item.as_pointer()
    cached = _curve_cache.get(key)
    if cached is not None and cached[0] == (records, steps):
        return cached[1]
    if not curved:
        units = [(tuple(record[0]), i, 0.0) for i, record in enumerate(records)]
        if len(_curve_cache) > 512:
            _curve_cache.clear()
        _curve_cache[key] = ((records, steps), units)
        return units
    handles = effective_handles(records)
    units = []
    for i in range(len(records)):
        controls = segment_controls(records, handles, i)
        units.append((controls[0], i, 0.0))
        if is_straight(controls):
            continue
        for step in range(1, steps):
            t = step / steps
            units.append((cubic(controls, t), i, t))
    if len(_curve_cache) > 512:
        _curve_cache.clear()
    _curve_cache[key] = ((records, steps), units)
    return units


def vertex_points(item):
    """Canvas positions of the shape's vertices, in order."""
    return [unit_to_canvas(item, vertex.co) for vertex in item.shape_vertices]


_outline_cache = {}


def outline(item):
    """Canvas points of the shape's outline: the vertices, with curved edges flattened.

    Cached until the shape changes, since drawing, bounds and picking all ask for it.
    The list is shared: callers must not change it.
    """
    units = curve_units(item)
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
    if len(_outline_cache) > 512:
        _outline_cache.clear()
    _outline_cache[item.as_pointer()] = (key, points, units)
    return points


def edge_midpoints(item):
    """Unit point halfway along each edge (on the curve when the edge is curved)."""
    records = item_records(item)
    handles = effective_handles(records)
    return [cubic(segment_controls(records, handles, i), 0.5) for i in range(len(records))]


def handle_points(item, index):
    """(left, right) canvas positions of a vertex's handles."""
    left, right = effective_handles(item_records(item))[index]
    return unit_to_canvas(item, left), unit_to_canvas(item, right)


def bounds(item):
    """Axis-aligned canvas bounds (left, bottom, right, top) of the rotated shape."""
    points = outline(item)
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


def segment_distance(point, a, b):
    """(distance, parameter along a->b) from a point to a segment."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return math.dist(point, a), 0.0
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.dist(point, (a[0] + dx * t, a[1] + dy * t)), t


def nearest_edge(points, point):
    """(edge index, distance, parameter) of the closed outline edge closest to a point."""
    best = (-1, float('inf'), 0.0)
    count = len(points)
    for i in range(count):
        distance, t = segment_distance(point, points[i], points[(i + 1) % count])
        if distance < best[1]:
            best = (i, distance, t)
    return best


def hit_shape(item, point, tolerance):
    """True when a canvas point should pick the shape.

    A filled shape is picked anywhere inside it. A shape without a fill is picked
    only on its outline, so it never blocks the image underneath it.
    """
    points = outline(item)
    if len(points) < MIN_VERTICES:
        return False
    if item.shape_show_fill and item.shape_fill_opacity > 0.0 \
            and point_in_polygon(point, points):
        return True
    reach = tolerance + (item.shape_line_width * 0.5 if item.shape_show_outline else 0.0)
    _, distance, _ = nearest_edge(points, point)
    return distance <= reach


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


def _tessellate(points):
    """Triangle index triples from Blender's own polygon filler, or None outside Blender."""
    try:
        from mathutils import Vector
        from mathutils.geometry import tessellate_polygon
    except ImportError:
        return None
    try:
        return tessellate_polygon([[Vector((x, y, 0.0)) for x, y in points]])
    except (ValueError, TypeError):
        return None


_triangle_cache = {}


def fill_triangles(item):
    """Index triples into `outline(item)` that fill the shape, cached with the curve.

    Triangulating in the unit box is enough: the box transform (scale, rotation and
    translation, never a mirror) keeps every triangle valid on the canvas.
    """
    units = curve_units(item)
    cached = _triangle_cache.get(item.as_pointer())
    if cached is not None and cached[0] is units:
        return cached[1]
    points = [unit for unit, _, _ in units]
    index = {}
    for i, point in enumerate(points):
        index.setdefault(point, i)
    triangles = [tuple(index[p] for p in triangle) for triangle in triangulate(points)]
    if len(_triangle_cache) > 512:
        _triangle_cache.clear()
    _triangle_cache[item.as_pointer()] = (units, triangles)
    return triangles


def triangulate(points):
    """Triangles (as point triples) covering a polygon.

    Uses Blender's polygon filler when available (fast, and it copes with outlines
    that cross themselves); otherwise ear clipping, falling back to a fan from the
    first vertex when the outline crosses itself, so a badly edited polygon still
    draws something.
    """
    if len(points) < 3:
        return []
    indices = _tessellate(points)
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
    degenerate shape.
    """
    if not vertices:
        return None
    extent = extent or vertices
    xs = [v[0] for v in extent]
    ys = [v[1] for v in extent]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    if span_x < 1e-6 or span_y < 1e-6:
        return None
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
    points = [unit_to_canvas(item, unit) for unit, _, _ in units]
    index, distance, local = nearest_edge(points, point)
    if index < 0 or distance > radius:
        return None
    _, edge, t0 = units[index]
    _, next_edge, t1 = units[(index + 1) % len(units)]
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

    An ellipse has eight, one every 45 degrees, instead of one per vertex.
    """
    vertices = [tuple(v.co) for v in item.shape_vertices]
    if len(vertices) < MIN_VERTICES:
        return []
    if item.shape_kind == 'ELLIPSE':
        units = vertices[::max(1, len(vertices) // 8)]
    else:
        units = list(vertices) + edge_midpoints(item)
    return [((u[0] + 0.5, u[1] + 0.5), unit_to_canvas(item, u)) for u in units]


def outline_attach(item, point, radius):
    """(uv, canvas point) on the outline nearest to `point`, within `radius`, or None."""
    points = outline(item)
    index, distance, t = nearest_edge(points, point)
    if index < 0 or distance > radius:
        return None
    a, b = points[index], points[(index + 1) % len(points)]
    onto = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return uv_at(item, onto), onto


def contains(item, point):
    return point_in_polygon(point, outline(item))

