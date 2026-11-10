"""Editing focus: while an image's Mask or Color, or a shape's vertices, are being
edited, the rest of the canvas is dimmed so the edited item stands out.

Drawn at the end of the canvas text pass (POST_PIXEL), so cards, labels and arrows are
dimmed too; the mode's own badge, shortcut panel and brush are drawn after it and stay
bright. The edited item is left out through a hole in the dimming.
"""

import math

import gpu
from gpu_extras.batch import batch_for_shader

from .gpu_common import get_prefs

HOLE_MARGIN = 6.0          # pixels around an edited image
SHAPE_MARGIN = 14.0        # pixels around an edited shape (its vertex handles)


def focus_item(settings):
    """(kind, item) being edited with the focus on it, or None."""
    for item in settings.images:
        if item.item_type == 'IMAGE' and (item.mask_editing or item.markup_editing):
            return 'IMAGE', item
    from .gpu_shape import vertex_edit_shape
    shape = vertex_edit_shape(settings)
    if shape is not None:
        return 'SHAPE', shape
    return None


def saturation_scale(settings):
    """(edited item id, factor) to multiply the saturation of every other image by
    while editing, or None.

    Only the drawing changes: the images keep their own Saturation, so nothing has
    to be stored or put back, and an auto save or an undo during the edit never
    catches them grey.
    """
    prefs = get_prefs()
    if prefs is None or not getattr(prefs, 'focus_desaturate', False):
        return None
    found = focus_item(settings)
    if found is None:
        return None
    amount = max(0.0, min(1.0, getattr(prefs, 'focus_desaturate_amount', 1.0)))
    return found[1].item_id, 1.0 - amount


def _image_corners(item):
    from ..arrow_geometry import image_point_from_uv
    from ..item_crop import corners_uv, stored_crop
    corners = [image_point_from_uv(item, uv) for uv in corners_uv(stored_crop(item))]
    return None if any(corner is None for corner in corners) else corners


def _shape_corners(item):
    from .. import shape_geometry as geometry
    points = list(geometry.outline(item))
    for index, vertex in enumerate(item.shape_vertices):
        if vertex.select and vertex.handle_type != 'SHARP':
            points.extend(geometry.handle_points(item, index))
    if not points:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]


def _grow(points, margin):
    """A convex outline pushed outwards by `margin` pixels from its middle."""
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    grown = []
    for x, y in points:
        dx, dy = x - cx, y - cy
        length = math.hypot(dx, dy) or 1.0
        grown.append((x + dx / length * margin * math.sqrt(2.0),
                      y + dy / length * margin * math.sqrt(2.0)))
    return grown


def focus_hole(settings, region):
    """Region-pixel outline left undimmed around the edited item, or None."""
    found = focus_item(settings)
    if found is None:
        return None
    kind, item = found
    corners = _image_corners(item) if kind == 'IMAGE' else _shape_corners(item)
    if not corners:
        return None
    view = region.view2d
    pixels = [tuple(view.view_to_region(x, y, clip=False)) for x, y in corners]
    return _grow(pixels, HOLE_MARGIN if kind == 'IMAGE' else SHAPE_MARGIN)


CLIP_MARGIN = 16.0   # pixels past the region edge where the hole is cut off


def clip_convex(polygon, left, bottom, right, top):
    """A convex polygon cut to a rectangle (Sutherland-Hodgman). [] when outside."""
    def cut(points, inside, cross):
        result = []
        for index, current in enumerate(points):
            previous = points[index - 1]
            if inside(current):
                if not inside(previous):
                    result.append(cross(previous, current))
                result.append(current)
            elif inside(previous):
                result.append(cross(previous, current))
        return result

    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    points = list(polygon)
    for inside, cross in ((lambda p: p[0] >= left, at_x(left)),
                          (lambda p: p[0] <= right, at_x(right)),
                          (lambda p: p[1] >= bottom, at_y(bottom)),
                          (lambda p: p[1] <= top, at_y(top))):
        if not points:
            break
        points = cut(points, inside, cross)
    return points


def dim_triangles(width, height, hole):
    """Triangles covering the region rectangle except the hole.

    Zoomed in on the edited item, its corners are far outside the region: the hole is
    first cut to the region (a little beyond its edges, so the two outlines never
    share an edge), then the even-odd Delaunay fill covers "inside the region but not
    inside the hole", which stays right however the two outlines meet.
    """
    width, height = float(width), float(height)
    outer = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    hole = clip_convex(hole, -CLIP_MARGIN, -CLIP_MARGIN, width + CLIP_MARGIN,
                       height + CLIP_MARGIN)
    if len(hole) < 3 or abs(sum(a[0] * b[1] - b[0] * a[1]
                                for a, b in zip(hole, hole[1:] + hole[:1]))) < 1.0:
        return [outer[0], outer[1], outer[2], outer[0], outer[2], outer[3]]   # all dimmed
    from ..shape_geometry import _delaunay_fill
    triangles = _delaunay_fill([outer, hole])
    if triangles is None:
        return []
    return [point for triangle in triangles for point in triangle]


def draw_focus_dim(settings, region):
    prefs = get_prefs()
    if prefs is None or not getattr(prefs, 'focus_dim_enabled', True):
        return
    amount = getattr(prefs, 'focus_dim_amount', 0.55)
    if amount <= 0.0:
        return
    hole = focus_hole(settings, region)
    if hole is None:
        return
    triangles = dim_triangles(region.width, region.height, hole)
    if not triangles:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        shader.uniform_float('color', (0.0, 0.0, 0.0, amount))
        batch_for_shader(shader, 'TRIS', {'pos': triangles}).draw(shader)
    finally:
        gpu.state.blend_set(old_blend)
