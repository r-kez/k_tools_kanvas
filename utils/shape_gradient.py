"""Gradient fills for shapes: the color ramp, the samples the shader reads, copying.

A gradient lives on the shape: a fill type (Solid, Linear or Radial), a spread (what
lies past the ends), two points in the shape's unit box (the same coordinates as the
vertices, so the gradient moves, turns and scales with the shape) and a color ramp.
Linear runs from the start point to the end point; Radial is a circle centred on the
start point whose edge passes through the end point. Distances are measured on the
canvas, so a radial gradient stays round on a stretched shape.

The colors are a Blender ColorRamp, so the panel shows Blender's own color ramp widget
(stops, opacity, interpolation, color mode, flip). A ColorRamp can only live inside a
datablock, so every shape with a gradient owns a hidden texture (`RAMP_NAME`, the dot
keeps it out of Blender's lists) used only for its ramp; it is saved because the shape
points to it, and dropped by Blender once no shape does. Shapes saved before the ramp
kept their stops in `shape_gradient_stops`; those are read until a ramp is made.

The ramp is sampled with `ColorRamp.evaluate` into RAMP_SIZE colors, which become a
small texture; the fragment shader turns each pixel's position into a place on it
(`gradient_t`, mirrored in GLSL). The maths below is plain Python, testable outside
Blender.
"""

import math

RAMP_SIZE = 256
RAMP_NAME = '.Kanvas Gradient'
FILL_TYPES = ('SOLID', 'LINEAR', 'RADIAL')
SPREADS = ('PAD', 'REFLECT', 'REPEAT')
DEFAULT_POINTS = {'LINEAR': ((-0.5, 0.0), (0.5, 0.0)),
                  'RADIAL': ((0.0, 0.0), (0.5, 0.0))}
# Stops written to SVG for a ramp that is not plain linear RGB (Ease, B-Spline, HSV...).
EXPORT_SAMPLES = 33


def is_gradient(item):
    return getattr(item, 'shape_fill_type', 'SOLID') in {'LINEAR', 'RADIAL'}


# --- Pure maths ------------------------------------------------------------------------

def spread_t(t, spread):
    """Place on the ramp (0 to 1) for any t, by the spread rule."""
    if spread == 'REPEAT':
        return t - math.floor(t)
    if spread == 'REFLECT':
        t = abs(t) % 2.0
        return 2.0 - t if t > 1.0 else t
    return min(1.0, max(0.0, t))


def gradient_t(kind, start, end, point):
    """Raw gradient parameter at a canvas point (0 at the start, 1 at the end)."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    px, py = point[0] - start[0], point[1] - start[1]
    if kind == 'RADIAL':
        return math.hypot(px, py) / max(math.hypot(dx, dy), 1e-9)
    return (px * dx + py * dy) / max(dx * dx + dy * dy, 1e-12)


def sample(stops, t):
    """Color (r, g, b, a) of sorted (r, g, b, a, position) stops at t, linearly."""
    if not stops:
        return (1.0, 1.0, 1.0, 1.0)
    if t <= stops[0][4]:
        return tuple(stops[0][:4])
    for a, b in zip(stops, stops[1:]):
        if t <= b[4]:
            span = b[4] - a[4]
            f = 0.0 if span <= 1e-9 else (t - a[4]) / span
            return tuple(a[i] + (b[i] - a[i]) * f for i in range(4))
    return tuple(stops[-1][:4])


def ramp(stops, size=RAMP_SIZE):
    """Flat RGBA list of `size` colors along linear stops."""
    values = []
    for i in range(size):
        values.extend(sample(stops, i / (size - 1)))
    return values


def average_color(values):
    """One color standing in for a flat RGBA sample list where it cannot be drawn."""
    count = max(1, len(values) // 4)
    return tuple(sum(values[i::4]) / count for i in range(4))


# --- The ramp of a shape ---------------------------------------------------------------

def color_ramp(item):
    """The shape's ColorRamp, or None before it has one."""
    texture = getattr(item, 'shape_gradient_texture', None)
    return texture.color_ramp if texture is not None and texture.color_ramp else None


def _legacy_stops(item):
    return sorted(((*stop.color, stop.alpha, stop.position)
                   for stop in getattr(item, 'shape_gradient_stops', ())),
                  key=lambda stop: stop[4])


def _write_stops(ramp, stops):
    """Make the ramp's elements these (r, g, b, a, position) stops (at least one)."""
    stops = sorted(stops, key=lambda stop: stop[4]) or [(1.0, 1.0, 1.0, 1.0, 0.0)]
    elements = ramp.elements
    while len(elements) > len(stops):
        elements.remove(elements[-1])
    while len(elements) < len(stops):
        elements.new(1.0)
    # Elements keep themselves sorted by position: set positions first, then colors.
    for element, stop in zip(list(elements), stops):
        element.position = stop[4]
    for element, stop in zip(sorted(elements, key=lambda e: e.position), stops):
        element.color = stop[:4]


def ensure_ramp(item):
    """The shape's own ColorRamp, made when missing (from stops saved by an older
    version, or the fill color fading to clear). A ramp shared with another shape
    (a copy made outside Kanvas) is copied first, so editing one never edits both."""
    import bpy
    texture = item.shape_gradient_texture
    if texture is not None and texture.users > 1:
        texture = texture.copy()
        item.shape_gradient_texture = texture
    if texture is None:
        texture = bpy.data.textures.new(RAMP_NAME, 'BLEND')
        texture.use_color_ramp = True
        color = tuple(item.shape_fill_color)
        stops = _legacy_stops(item) or [(*color, 1.0, 0.0), (*color, 0.0, 1.0)]
        _write_stops(texture.color_ramp, stops)
        item.shape_gradient_texture = texture
    elif not texture.use_color_ramp:
        texture.use_color_ramp = True
    return texture.color_ramp


def stop_records(item):
    """(r, g, b, a, position) of every stop, sorted by position."""
    ramp = color_ramp(item)
    if ramp is None:
        return _legacy_stops(item)
    return sorted(((*element.color, element.position) for element in ramp.elements),
                  key=lambda stop: stop[4])


def ramp_key(item):
    """Everything about the colors that changes the drawing."""
    ramp = color_ramp(item)
    if ramp is None:
        return ('stops', tuple(_legacy_stops(item)))
    return (ramp.interpolation, ramp.color_mode, ramp.hue_interpolation,
            tuple(stop_records(item)))


def ramp_values(item, size=RAMP_SIZE):
    """Flat RGBA list of `size` colors along the gradient, as the ramp widget shows."""
    colors = color_ramp(item)
    if colors is None:
        return ramp(_legacy_stops(item), size)
    values = []
    for i in range(size):
        values.extend(colors.evaluate(i / (size - 1)))
    return values


def export_stops(item):
    """Stops for SVG, which only knows linear RGB: other ramps are sampled."""
    ramp = color_ramp(item)
    if ramp is None or (ramp.interpolation == 'LINEAR' and ramp.color_mode == 'RGB'):
        return stop_records(item)
    values = ramp_values(item, EXPORT_SAMPLES)
    return [(*values[i * 4:i * 4 + 4], i / (EXPORT_SAMPLES - 1)) for i in range(EXPORT_SAMPLES)]


def canvas_points(item):
    """Start and end point of the gradient on the canvas."""
    from .shape_geometry import unit_to_canvas
    return (unit_to_canvas(item, item.shape_gradient_start),
            unit_to_canvas(item, item.shape_gradient_end))


def signature(item):
    """Everything about the gradient that changes the drawing."""
    if not is_gradient(item):
        return ('SOLID',)
    return (item.shape_fill_type, item.shape_gradient_spread,
            tuple(item.shape_gradient_start), tuple(item.shape_gradient_end), ramp_key(item))


# --- Reading, writing and seeding ------------------------------------------------------

def gradient_record(item):
    """Plain copy of the gradient, for duplicates, Copy Style and SVG."""
    ramp = color_ramp(item)
    return {'type': item.shape_fill_type, 'spread': item.shape_gradient_spread,
            'start': tuple(item.shape_gradient_start), 'end': tuple(item.shape_gradient_end),
            'stops': stop_records(item),
            'ramp': ((ramp.interpolation, ramp.color_mode, ramp.hue_interpolation)
                     if ramp is not None else None)}


def set_gradient_record(item, record):
    # The type first: its update seeds defaults, which the record then overwrites.
    item.shape_fill_type = record['type']
    if record['stops'] or record.get('ramp'):
        ramp = ensure_ramp(item)
        _write_stops(ramp, record['stops'])
        if record.get('ramp'):
            ramp.interpolation, ramp.color_mode, ramp.hue_interpolation = record['ramp']
    item.shape_gradient_start = record['start']
    item.shape_gradient_end = record['end']
    item.shape_gradient_spread = record['spread']


def seed_gradient(item):
    """First time a shape gets a gradient: its own ramp (the fill color fading to
    clear) and points that fit the type."""
    ensure_ramp(item)
    if item.shape_fill_type in DEFAULT_POINTS:
        start, end = DEFAULT_POINTS[item.shape_fill_type]
        other = DEFAULT_POINTS['RADIAL' if item.shape_fill_type == 'LINEAR' else 'LINEAR']
        current = (tuple(item.shape_gradient_start), tuple(item.shape_gradient_end))
        # Untouched points (or the other type's defaults) take this type's defaults.
        if _close(current, other) or _close(current, ((0.0, 0.0), (0.0, 0.0))):
            item.shape_gradient_start, item.shape_gradient_end = start, end


def _close(a, b):
    return all(math.dist(p, q) < 1e-6 for p, q in zip(a, b))


# --- Keeping ramps apart ---------------------------------------------------------------

def unshare_ramps():
    """Give a shape its own ramp where two shapes point to one (Blender's own copy of a
    Kanvas tree keeps the pointer). The first owner keeps it. Returns how many changed."""
    import bpy
    owners, changed = set(), 0
    for tree in bpy.data.node_groups:
        if tree.bl_idname != 'KanvasNodeTree':
            continue
        for item in tree.kanvas_settings.images:
            texture = item.shape_gradient_texture if item.item_type == 'SHAPE' else None
            if texture is None:
                continue
            if texture.name_full in owners:
                item.shape_gradient_texture = texture.copy()
                changed += 1
            owners.add(item.shape_gradient_texture.name_full)
    return changed


def is_ramp_texture(id_data):
    import bpy
    return isinstance(id_data, bpy.types.Texture) and id_data.name.startswith(RAMP_NAME)
