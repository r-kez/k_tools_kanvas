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
    rectangle."""
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
    mark.known_value, mark.known_unit, mark.known_side = value, unit, side
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
    from .item_picture import _apply, _inverse, _mirrored, image_to_canvas
    inverse = _inverse(image_to_canvas(item))
    if inverse is None:
        return None
    x, y = _apply(inverse, (point[0] - item.location[0], point[1] - item.location[1]))
    width, height = pixel_size(item)
    u, v = x / width + 0.5, y / height + 0.5
    mirror_x, mirror_y = _mirrored(item)
    return (1.0 - u if mirror_x else u), (1.0 - v if mirror_y else v)


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
