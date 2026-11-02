"""Geometry of Kanvas shapes: presets, transforms, hit testing and triangulation.

A shape stores its vertices in a unit box (-0.5..0.5 on both axes). The canvas
position of a vertex is its unit position times the shape size, then the shape's
rotation, then its location. Every preset, and every hand-edited polygon, uses the
same representation, so the kind of a shape can change at any time.
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


def outline(item):
    """Canvas positions of the shape's vertices, in order."""
    return [unit_to_canvas(item, vertex.co) for vertex in item.shape_vertices]


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


def triangulate(points):
    """Triangles (as point triples) covering a simple polygon, by ear clipping.

    Falls back to a fan from the first vertex when the outline crosses itself, so a
    badly edited polygon still draws something.
    """
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


def normalized(vertices):
    """Rescale unit vertices so their bounding box is exactly the unit box.

    Returns (vertices, center, span): the new vertices, the former box center and
    the former box size, all in unit coordinates, or None for a degenerate shape.
    """
    if not vertices:
        return None
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
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
    for index, canvas in enumerate(outline(item)):
        distance = math.dist(canvas, point)
        if distance <= best_distance:
            best, best_distance = index, distance
    return best


def hit_edge(item, point, radius):
    """(edge index, parameter) of an outline edge within `radius`, or None."""
    index, distance, t = nearest_edge(outline(item), point)
    return (index, t) if index >= 0 and distance <= radius else None


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
        units = list(vertices)
        units += [((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
                  for a, b in zip(vertices, vertices[1:] + vertices[:1])]
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

