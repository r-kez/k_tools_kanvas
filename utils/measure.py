"""Measuring on images: marks drawn on an image, and a scale that turns pixels into real
sizes.

A mark is a line (two points) or a rectangle (two opposite corners), stored in the
image's own coordinates (UV, as masks store them) so it follows the image when it is
moved, turned, scaled, flipped or cropped. One mark of an image can be its **scale**:
the user says how long it really is (the wheel and tire are 66 cm high), and every
other mark of that image, and the size of the image in the 3D View, follows from it.
Without a scale, marks read in pixels.

Everything here is plain Python over the item's properties, so it works the same in the
canvas drawing, the panel, the 3D View code and the tests.
"""

import math
import uuid

# meters per unit
UNITS = {'MM': 0.001, 'CM': 0.01, 'M': 1.0, 'IN': 0.0254, 'FT': 0.3048}
UNIT_ITEMS = (
    ('MM', 'mm', 'Millimeters'),
    ('CM', 'cm', 'Centimeters'),
    ('M', 'm', 'Meters'),
    ('IN', 'in', 'Inches'),
    ('FT', 'ft', 'Feet'),
)
UNIT_SYMBOLS = {'MM': 'mm', 'CM': 'cm', 'M': 'm', 'IN': 'in', 'FT': 'ft'}
# Which size of a rectangle the scale is given for.
SIDE_ITEMS = (
    ('LENGTH', 'Length', 'The length of the line'),
    ('HEIGHT', 'Height', 'The height of the rectangle'),
    ('WIDTH', 'Width', 'The width of the rectangle'),
)
KINDS = ('LINE', 'RECT')


# --- Marks ---------------------------------------------------------------------------------

def pixel_size(item):
    """(width, height) of the image in pixels."""
    return item.image_data.size[0], item.image_data.size[1]


def mark_pixels(item, measure):
    """The size of a mark in image pixels: the length for a line, (width, height) for a
    rectangle. On an image with its perspective corrected the pixels are those of the
    straightened picture, so a mark on the rectangle reads true sizes: a line is as long
    as it is there, a rectangle as wide and high as its corners come out."""
    from .item_crop import corrected
    rectangle = corrected(item)
    if rectangle is not None:
        from . import perspective
        points = [perspective.uv_to_rect(rectangle, uv) for uv in mark_corners(measure)]
        if any(point is None for point in points):
            return (0.0, 0.0) if measure.kind == 'RECT' else 0.0
        points = [(x * rectangle.width, y * rectangle.height) for x, y in points]
        if measure.kind == 'RECT':
            return ((math.dist(points[0], points[1]) + math.dist(points[3], points[2])) * 0.5,
                    (math.dist(points[0], points[3]) + math.dist(points[1], points[2])) * 0.5)
        return math.dist(points[0], points[1])
    width, height = pixel_size(item)
    dx = abs(measure.p1[0] - measure.p0[0]) * width
    dy = abs(measure.p1[1] - measure.p0[1]) * height
    if measure.kind == 'RECT':
        return dx, dy
    return math.hypot(dx, dy)


def default_side(kind):
    return 'LENGTH' if kind == 'LINE' else 'HEIGHT'


def valid_side(kind, side):
    """A line has only a length; a rectangle a height or a width (height if asked for a
    length)."""
    if kind == 'LINE':
        return 'LENGTH'
    return side if side in {'HEIGHT', 'WIDTH'} else 'HEIGHT'


def side_pixels(item, measure, side):
    """Pixels of the side a scale is given for."""
    size = mark_pixels(item, measure)
    if measure.kind == 'LINE':
        return size
    return size[0] if side == 'WIDTH' else size[1]


def add_mark(item, kind, p0, p1, name=''):
    """Add a mark (UV points) to an image, make it active, and return it. The
    reference stays valid only until the collection changes again."""
    mark_id = uuid.uuid4().hex
    mark = item.measures.add()
    mark.measure_id = mark_id
    mark.kind = kind
    mark.p0, mark.p1 = tuple(p0), tuple(p1)
    mark.name = name or _next_name(item, kind)
    item.measure_active_index = len(item.measures) - 1
    return item.measures[item.measure_active_index]


def _next_name(item, kind):
    base = 'Line' if kind == 'LINE' else 'Rectangle'
    taken = {mark.name for mark in item.measures}
    number = 1
    while f'{base} {number}' in taken:
        number += 1
    return f'{base} {number}'


def find_mark(item, measure_id):
    return next((mark for mark in item.measures if mark.measure_id == measure_id), None)


def scale_mark(item):
    """The mark that is this image's scale, or None."""
    return find_mark(item, item.measure_scale_id) if item.measure_scale_id else None


def set_scale(item, measure_id, value, unit, side=None):
    """Make a mark the scale of its image: it is `value` `unit` long (or high, or wide).
    Returns False for a mark that is gone, a zero size or a non-positive value."""
    mark = find_mark(item, measure_id)
    if mark is None or value <= 0.0:
        return False
    side = valid_side(mark.kind, side or default_side(mark.kind))
    if side_pixels(item, mark, side) < 1e-6:
        return False
    # The unit first: choosing a unit converts the value the mark already has, and the
    # value that follows is the one meant.
    mark.known_unit = unit
    mark.known_value = value
    mark.known_side = side
    item.measure_scale_id = measure_id
    return True


def clear_scale(item):
    item.measure_scale_id = ''


def meters_per_pixel(item):
    """Real meters in one pixel of the image, None without a usable scale."""
    mark = scale_mark(item)
    if mark is None or mark.known_value <= 0.0:
        return None
    pixels = side_pixels(item, mark, mark.known_side)
    if pixels < 1e-6:
        return None
    return mark.known_value * UNITS[mark.known_unit] / pixels


def is_calibrated(item):
    return meters_per_pixel(item) is not None


# --- Reading marks as text -----------------------------------------------------------------

def _number(value, places=2):
    if value != 0.0 and abs(value) < 10.0 ** -places:
        text = f'{value:.3g}'          # a very small size keeps its significant digits
        return text
    text = f'{value:.{places}f}'
    if '.' in text:
        text = text.rstrip('0').rstrip('.')   # only the zeros after the point
    return text or '0'


def format_length(meters, unit):
    """A length in the unit, such as '66 cm'. More decimals for large units."""
    value = meters / UNITS[unit]
    places = 2 if unit in {'CM', 'M', 'IN', 'FT'} else 1
    if abs(value) >= 1000.0:
        places = 0
    return f'{_number(value, places)} {UNIT_SYMBOLS[unit]}'


def format_pixels(pixels):
    return f'{_number(pixels, 0 if pixels >= 10.0 else 1)} px'


def mark_text(item, measure, unit):
    """What a mark reads: its size in the unit when the image has a scale, in pixels
    when it does not. A rectangle reads 'width × height'."""
    size = mark_pixels(item, measure)
    per_pixel = meters_per_pixel(item)
    if per_pixel is None:
        if measure.kind == 'RECT':
            return f'{_number(size[0], 0)} × {_number(size[1], 0)} px'
        return format_pixels(size)
    symbol = UNIT_SYMBOLS[unit]
    if measure.kind == 'RECT':
        w, h = (side * per_pixel / UNITS[unit] for side in size)
        places = 2 if unit in {'CM', 'M', 'IN', 'FT'} else 1
        return f'{_number(w, places)} × {_number(h, places)} {symbol}'
    return format_length(size * per_pixel, unit)


def scale_text(item):
    """'1 px = 0.42 cm' for the panel, or None without a scale."""
    mark = scale_mark(item)
    per_pixel = meters_per_pixel(item)
    if mark is None or per_pixel is None:
        return None
    unit = mark.known_unit
    value = per_pixel / UNITS[unit]
    return f'1 px = {_number(value, 4)} {UNIT_SYMBOLS[unit]}'


# --- Where a mark is on the board ----------------------------------------------------------

def canvas_to_uv(item, point):
    """The image coordinates (UV, not clamped) under a point of the canvas. The
    opposite of `arrow_geometry.image_point_from_uv`."""
    from .item_crop import stored_crop
    from .item_picture import _apply, _inverse, _mirrored, image_to_canvas
    inverse = _inverse(image_to_canvas(item))
    if inverse is None:
        return None
    x, y = _apply(inverse, (point[0] - item.location[0], point[1] - item.location[1]))
    mirror_x, mirror_y = _mirrored(item)
    from .item_crop import corrected
    rectangle = corrected(item)
    if rectangle is not None:
        from . import perspective
        r_u, r_v = x / rectangle.width + 0.5, y / rectangle.height + 0.5
        return perspective.rect_to_uv(rectangle, (1.0 - r_u if mirror_x else r_u,
                                                  1.0 - r_v if mirror_y else r_v))
    width, height = pixel_size(item)
    u0, v0, u1, v1 = stored_crop(item)
    u, v = x / width + (u0 + u1) * 0.5, y / height + (v0 + v1) * 0.5
    return (u0 + u1 - u if mirror_x else u), (v0 + v1 - v if mirror_y else v)


def mark_corners(measure):
    """UV points of a mark's outline: the two ends of a line, the four corners of a
    rectangle."""
    (u0, v0), (u1, v1) = measure.p0, measure.p1
    if measure.kind == 'RECT':
        return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    return [(u0, v0), (u1, v1)]


def mark_canvas_points(item, measure):
    """The outline of a mark on the canvas (None if the image has no size)."""
    from .arrow_geometry import image_point_from_uv
    points = [image_point_from_uv(item, uv) for uv in mark_corners(measure)]
    return None if any(point is None for point in points) else points


def mark_label_point(item, measure):
    """Canvas point where a mark's text sits: the middle of a line, the center of a
    rectangle."""
    from .arrow_geometry import image_point_from_uv
    (u0, v0), (u1, v1) = measure.p0, measure.p1
    return image_point_from_uv(item, ((u0 + u1) * 0.5, (v0 + v1) * 0.5))


# --- Editing marks on the canvas ------------------------------------------------------------
#
# A line has handles at its two ends (P0, P1); a rectangle at its four corners
# (CORNER_ab: `a` says whether the corner's U comes from p0 or p1, `b` the same for V)
# and along its four edges (EDGE_X0 and EDGE_X1 hold a U, EDGE_Y0 and EDGE_Y1 a V). Both
# have a CENTER handle that moves the whole mark; the body of a line does the same.

HANDLE_PIXELS = 9.0         # how close a click must be to a handle, in screen pixels
EDGE_PIXELS = 6.0           # and to the line or an edge


def mark_handles(item, mark):
    """(part, canvas point) of each handle of a mark."""
    points = mark_canvas_points(item, mark)
    center = mark_label_point(item, mark)
    if points is None or center is None:
        return []
    if mark.kind == 'LINE':
        return [('P0', points[0]), ('P1', points[1]), ('CENTER', center)]
    return [('CORNER_00', points[0]), ('CORNER_10', points[1]), ('CORNER_11', points[2]),
            ('CORNER_01', points[3]), ('CENTER', center)]


def mark_edges(item, mark):
    """(part, start, end) of what can be grabbed along a mark: the line itself (it moves
    the mark), or one edge of a rectangle (it moves that side)."""
    points = mark_canvas_points(item, mark)
    if points is None:
        return []
    if mark.kind == 'LINE':
        return [('CENTER', points[0], points[1])]
    return [('EDGE_Y0', points[0], points[1]), ('EDGE_X1', points[1], points[2]),
            ('EDGE_Y1', points[2], points[3]), ('EDGE_X0', points[3], points[0])]


def _segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared < 1e-18:
        return math.dist(point, start)
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
                     / length_squared))
    return math.dist(point, (start[0] + t * dx, start[1] + t * dy))


def hit_mark(item, point, pixel_size):
    """(mark, part) of the handle or edge under a canvas point, handles first, the active
    mark and the last drawn before the others. None when nothing is there."""
    marks = [mark for mark in item.measures if mark.visible]
    active = item.measure_active_index
    marks.sort(key=lambda mark: 0 if (0 <= active < len(item.measures)
                                      and item.measures[active].measure_id == mark.measure_id)
               else 1)
    for mark in marks:
        for part, handle in mark_handles(item, mark):
            if math.dist(point, handle) <= HANDLE_PIXELS * pixel_size:
                return mark, part
    for mark in marks:
        for part, start, end in mark_edges(item, mark):
            if _segment_distance(point, start, end) <= EDGE_PIXELS * pixel_size:
                return mark, part
    return None


def editing_item(settings, window_manager):
    """The image whose marks can be edited on the canvas: the selected active image while
    the Measure tab is open, when it shows its marks. None otherwise."""
    tabs = getattr(window_manager, 'kanvas_tabs', None)
    if tabs is None or tabs.image != 'MEASURE':
        return None
    index = settings.active_image_index
    if not 0 <= index < len(settings.images):
        return None
    item = settings.images[index]
    if (item.item_type != 'IMAGE' or not item.is_selected or not item.image_data
            or not item.measure_visible or not item.measures or not item.show_in_editor):
        return None
    return item


def hit_editable(settings, window_manager, point, pixel_size):
    """(item_id, measure_id, part) of the handle of an editable mark under a point."""
    item = editing_item(settings, window_manager)
    if item is None:
        return None
    hit = hit_mark(item, point, pixel_size)
    return None if hit is None else (item.item_id, hit[0].measure_id, hit[1])


def apply_part(mark, part, start_p0, start_p1, start_uv, uv):
    """Move one part of a mark to `uv`, from how the mark was when the drag began:
    CENTER shifts the whole mark by the drag (kept inside the image), the others move
    their point, corner or side."""
    p0, p1 = list(start_p0), list(start_p1)
    if part == 'CENTER':
        dx, dy = uv[0] - start_uv[0], uv[1] - start_uv[1]
        dx = max(-min(p0[0], p1[0]), min(1.0 - max(p0[0], p1[0]), dx))
        dy = max(-min(p0[1], p1[1]), min(1.0 - max(p0[1], p1[1]), dy))
        p0, p1 = [p0[0] + dx, p0[1] + dy], [p1[0] + dx, p1[1] + dy]
    elif part == 'P0':
        p0 = list(uv)
    elif part == 'P1':
        p1 = list(uv)
    elif part.startswith('CORNER_'):
        points = (p0, p1)
        points[int(part[7])][0] = uv[0]
        points[int(part[8])][1] = uv[1]
    elif part.startswith('EDGE_'):
        axis = 0 if part[5] == 'X' else 1
        (p0, p1)[int(part[6])][axis] = uv[axis]
    mark.p0, mark.p1 = tuple(p0), tuple(p1)


def opposite_point(part, p0, p1):
    """The point a corner or an end is held against while it is dragged with Shift."""
    if part == 'P0':
        return tuple(p1)
    if part == 'P1':
        return tuple(p0)
    if part.startswith('CORNER_'):
        a, b = int(part[7]), int(part[8])
        return ((p0, p1)[1 - a][0], (p0, p1)[1 - b][1])
    return None


# --- Real size in the 3D View --------------------------------------------------------------

def real_size_meters(item, picture_pixels):
    """Real longer side, in meters, of a picture whose longer side is
    `picture_pixels` image pixels, None without a scale."""
    per_pixel = meters_per_pixel(item)
    return None if per_pixel is None else picture_pixels * per_pixel


def scene_units(meters, scene):
    """Meters as Blender units of a scene (its Unit Scale says how many meters a unit
    is)."""
    scale = scene.unit_settings.scale_length or 1.0
    return meters / scale


def signature(item):
    """What the scale of an image depends on, to notice a change cheaply."""
    mark = scale_mark(item)
    if mark is None:
        return None
    return (mark.measure_id, tuple(mark.p0), tuple(mark.p1), mark.known_value,
            mark.known_unit, mark.known_side, tuple(item.image_data.size))
