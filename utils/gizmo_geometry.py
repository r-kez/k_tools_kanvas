"""Screen-sized transform handle positions in Kanvas view coordinates."""

import math


def _rotate(point, origin, degrees):
    angle = math.radians(degrees)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    return (origin[0] + dx * cos_a - dy * sin_a,
            origin[1] + dx * sin_a + dy * cos_a)


def handle_layout(location, width, height, shear, rotation, size):
    """Return corners, edge midpoints, rotation stem and handle.

    ``size`` is the configured gizmo size converted from screen pixels to view
    units. The top-edge normal keeps the rotation handle outside a sheared or
    rotated image, and the caller uses these same positions for drawing/hits.
    """
    half_w, half_h = width * 0.5, height * 0.5
    raw_corners = [(-half_w, -half_h), (half_w, -half_h),
                   (half_w, half_h), (-half_w, half_h)]
    raw_edges = [(0, -half_h), (half_w, 0),
                 (0, half_h), (-half_w, 0)]

    def transform(point):
        x, y = point
        x, y = x + y * shear[0], y + x * shear[1]
        return _rotate((location[0] + x, location[1] + y), location, rotation)

    corners = [transform(point) for point in raw_corners]
    edges = [transform(point) for point in raw_edges]
    top_left, top_right = corners[3], corners[2]
    dx, dy = top_right[0] - top_left[0], top_right[1] - top_left[1]
    length = math.hypot(dx, dy)
    normal = (-dy / length, dx / length) if length else (0.0, 1.0)
    stem = edges[2]
    rotate = (stem[0] + normal[0] * size * 1.3,
              stem[1] + normal[1] * size * 1.3)
    return corners, edges, stem, rotate


def collective_handle_layout(bounds, size):
    left, bottom, right, top = bounds
    corners = [(left, bottom), (right, bottom),
               (right, top), (left, top)]
    stem = ((left + right) * 0.5, top)
    rotate = (stem[0], stem[1] + size * 1.3)
    return corners, stem, rotate
