"""Read and write Kanvas shapes as SVG.

Reading turns every element of an SVG file (paths, rectangles, circles, ellipses,
polygons and polylines, inside groups and transforms) into contours of cubic segments
with its fill and stroke. Each element becomes one shape, and the subpaths of a path
become the contours of that shape, so holes stay holes (see `contour_groups` for the
`nonzero` fill rule).

Writing gives one <path> per shape, with the curve exactly as stored (Bezier handles
become cubic segments, rotation and scale are baked into the coordinates); a shape
with several contours writes one subpath per contour and `fill-rule="evenodd"`.

Points here are canvas points (y up). SVG uses y down, so y is flipped on the way in
and out. Nothing here needs bpy except `export_svg`, which reads shape items.
"""

import math
import re
import xml.etree.ElementTree as ET

# --- colors ----------------------------------------------------------------------------

_NAMED = {
    'black': (0, 0, 0), 'white': (255, 255, 255), 'red': (255, 0, 0), 'lime': (0, 255, 0),
    'green': (0, 128, 0), 'blue': (0, 0, 255), 'yellow': (255, 255, 0),
    'cyan': (0, 255, 255), 'aqua': (0, 255, 255), 'magenta': (255, 0, 255),
    'fuchsia': (255, 0, 255), 'gray': (128, 128, 128), 'grey': (128, 128, 128),
    'silver': (192, 192, 192), 'maroon': (128, 0, 0), 'olive': (128, 128, 0),
    'purple': (128, 0, 128), 'teal': (0, 128, 128), 'navy': (0, 0, 128),
    'orange': (255, 165, 0), 'pink': (255, 192, 203), 'brown': (165, 42, 42),
    'gold': (255, 215, 0), 'darkgray': (169, 169, 169), 'darkgrey': (169, 169, 169),
    'lightgray': (211, 211, 211), 'lightgrey': (211, 211, 211),
}
GRADIENT_FALLBACK = (0.5, 0.5, 0.5)


def parse_color(value):
    """(r, g, b) in 0..1, or None for 'none'/'transparent'. Unknown values give None."""
    if value is None:
        return None
    value = value.strip().lower()
    if value in {'', 'none', 'transparent'}:
        return None
    if value == 'currentcolor':
        return (0.0, 0.0, 0.0)
    if value.startswith('url('):
        return GRADIENT_FALLBACK   # gradients and patterns: a neutral flat color
    if value.startswith('#'):
        digits = value[1:]
        if len(digits) in (3, 4):
            digits = ''.join(c * 2 for c in digits[:3])
        if len(digits) in (6, 8):
            try:
                return tuple(int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            except ValueError:
                return None
        return None
    match = re.match(r'rgba?\(([^)]*)\)', value)
    if match:
        parts = [p.strip() for p in re.split(r'[,\s/]+', match.group(1)) if p.strip()]
        channels = []
        for part in parts[:3]:
            try:
                channels.append(float(part[:-1]) / 100.0 if part.endswith('%')
                                else float(part) / 255.0)
            except ValueError:
                return None
        if len(channels) == 3:
            return tuple(max(0.0, min(1.0, c)) for c in channels)
        return None
    if value in _NAMED:
        return tuple(c / 255.0 for c in _NAMED[value])
    return None


def hex_color(color):
    return '#{:02x}{:02x}{:02x}'.format(*(round(max(0.0, min(1.0, v)) * 255) for v in color))


# --- transforms ------------------------------------------------------------------------
# An affine transform is (a, b, c, d, e, f): x' = a x + c y + e, y' = b x + d y + f.

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def multiply(m, n):
    """m applied after n."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def apply(m, point):
    a, b, c, d, e, f = m
    return a * point[0] + c * point[1] + e, b * point[0] + d * point[1] + f


_NUMBER = r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?'


def parse_transform(text):
    matrix = IDENTITY
    for name, args in re.findall(r'(\w+)\s*\(([^)]*)\)', text or ''):
        values = [float(v) for v in re.findall(_NUMBER, args)]
        step = None
        if name == 'matrix' and len(values) == 6:
            step = tuple(values)
        elif name == 'translate' and values:
            step = (1.0, 0.0, 0.0, 1.0, values[0], values[1] if len(values) > 1 else 0.0)
        elif name == 'scale' and values:
            sy = values[1] if len(values) > 1 else values[0]
            step = (values[0], 0.0, 0.0, sy, 0.0, 0.0)
        elif name == 'rotate' and values:
            angle = math.radians(values[0])
            cos, sin = math.cos(angle), math.sin(angle)
            step = (cos, sin, -sin, cos, 0.0, 0.0)
            if len(values) == 3:
                cx, cy = values[1], values[2]
                step = multiply((1.0, 0.0, 0.0, 1.0, cx, cy),
                                multiply(step, (1.0, 0.0, 0.0, 1.0, -cx, -cy)))
        elif name == 'skewX' and values:
            step = (1.0, 0.0, math.tan(math.radians(values[0])), 1.0, 0.0, 0.0)
        elif name == 'skewY' and values:
            step = (1.0, math.tan(math.radians(values[0])), 0.0, 1.0, 0.0, 0.0)
        if step is not None:
            matrix = multiply(matrix, step)
    return matrix


# --- path data -------------------------------------------------------------------------

class _Scanner:
    """Reads numbers and arc flags from path data (flags may be written without spaces)."""

    _number = re.compile(r'[\s,]*(' + _NUMBER + ')')
    _flag = re.compile(r'[\s,]*([01])')
    _command = re.compile(r'[\s,]*([MmZzLlHhVvCcSsQqTtAa])')

    def __init__(self, text):
        self.text = text
        self.pos = 0

    def command(self):
        match = self._command.match(self.text, self.pos)
        if not match:
            return None
        self.pos = match.end()
        return match.group(1)

    def has_number(self):
        return self._number.match(self.text, self.pos) is not None

    def number(self):
        match = self._number.match(self.text, self.pos)
        if not match:
            raise ValueError('number expected')
        self.pos = match.end()
        return float(match.group(1))

    def flag(self):
        match = self._flag.match(self.text, self.pos)
        if not match:
            raise ValueError('arc flag expected')
        self.pos = match.end()
        return match.group(1) == '1'


def _line(p0, p3):
    return (p0, p0, p3, p3)


def _quad(p0, q, p3):
    return (p0, (p0[0] + 2.0 / 3.0 * (q[0] - p0[0]), p0[1] + 2.0 / 3.0 * (q[1] - p0[1])),
            (p3[0] + 2.0 / 3.0 * (q[0] - p3[0]), p3[1] + 2.0 / 3.0 * (q[1] - p3[1])), p3)


def _arc(p0, rx, ry, rotation, large, sweep, p3):
    """Cubic segments of an SVG elliptical arc (endpoint parametrization)."""
    if p0 == p3:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-12 or ry < 1e-12:
        return [_line(p0, p3)]
    phi = math.radians(rotation)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p3[0]) / 2.0, (p0[1] - p3[1]) / 2.0
    x1, y1 = cos * dx + sin * dy, -sin * dx + cos * dy
    scale = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if scale > 1.0:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    numerator = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    denominator = rx * rx * y1 * y1 + ry * ry * x1 * x1
    factor = math.sqrt(max(0.0, numerator / denominator)) if denominator else 0.0
    if large == sweep:
        factor = -factor
    cx1, cy1 = factor * rx * y1 / ry, -factor * ry * x1 / rx
    cx = cos * cx1 - sin * cy1 + (p0[0] + p3[0]) / 2.0
    cy = sin * cx1 + cos * cy1 + (p0[1] + p3[1]) / 2.0

    def angle(ux, uy, vx, vy):
        value = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return value

    start = angle(1.0, 0.0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    delta = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and delta > 0:
        delta -= math.tau
    elif sweep and delta < 0:
        delta += math.tau
    count = max(1, math.ceil(abs(delta) / (math.pi / 2.0) - 1e-9))
    step = delta / count
    k = 4.0 / 3.0 * math.tan(step / 4.0)

    def point(theta):
        x, y = rx * math.cos(theta), ry * math.sin(theta)
        return cx + cos * x - sin * y, cy + sin * x + cos * y

    def tangent(theta):
        x, y = -rx * math.sin(theta), ry * math.cos(theta)
        return cos * x - sin * y, sin * x + cos * y

    segments = []
    previous = p0
    for i in range(count):
        a, b = start + step * i, start + step * (i + 1)
        end = p3 if i == count - 1 else point(b)
        ta, tb = tangent(a), tangent(b)
        segments.append((previous, (previous[0] + k * ta[0], previous[1] + k * ta[1]),
                         (end[0] - k * tb[0], end[1] - k * tb[1]), end))
        previous = end
    return segments


def parse_path(data):
    """[(segments, closed)] for each subpath; segments are cubic (p0, p1, p2, p3)."""
    scanner = _Scanner(data or '')
    subpaths = []
    segments = []
    current = start = (0.0, 0.0)
    last_cubic = last_quad = None
    command = None

    def finish(closed):
        nonlocal segments
        if segments:
            subpaths.append((segments, closed))
        segments = []

    while True:
        found = scanner.command()
        if found is None:
            if command is None or not scanner.has_number() or command in 'Zz':
                break
            found = command
            if found in 'Mm':
                found = 'l' if found == 'm' else 'L'   # extra pairs after M are lines
        command = found
        relative = command.islower()
        upper = command.upper()
        ox, oy = current if relative else (0.0, 0.0)
        try:
            if upper == 'Z':
                if current != start:
                    segments.append(_line(current, start))
                current = start
                finish(True)
                last_cubic = last_quad = None
                continue
            if upper == 'M':
                finish(False)
                current = start = (ox + scanner.number(), oy + scanner.number())
                last_cubic = last_quad = None
                continue
            if upper == 'L':
                end = (ox + scanner.number(), oy + scanner.number())
                segments.append(_line(current, end))
                current, last_cubic, last_quad = end, None, None
            elif upper == 'H':
                end = ((ox if relative else 0.0) + scanner.number(), current[1])
                segments.append(_line(current, end))
                current, last_cubic, last_quad = end, None, None
            elif upper == 'V':
                end = (current[0], (oy if relative else 0.0) + scanner.number())
                segments.append(_line(current, end))
                current, last_cubic, last_quad = end, None, None
            elif upper == 'C':
                c1 = (ox + scanner.number(), oy + scanner.number())
                c2 = (ox + scanner.number(), oy + scanner.number())
                end = (ox + scanner.number(), oy + scanner.number())
                segments.append((current, c1, c2, end))
                current, last_cubic, last_quad = end, c2, None
            elif upper == 'S':
                c1 = ((2 * current[0] - last_cubic[0], 2 * current[1] - last_cubic[1])
                      if last_cubic else current)
                c2 = (ox + scanner.number(), oy + scanner.number())
                end = (ox + scanner.number(), oy + scanner.number())
                segments.append((current, c1, c2, end))
                current, last_cubic, last_quad = end, c2, None
            elif upper == 'Q':
                q = (ox + scanner.number(), oy + scanner.number())
                end = (ox + scanner.number(), oy + scanner.number())
                segments.append(_quad(current, q, end))
                current, last_cubic, last_quad = end, None, q
            elif upper == 'T':
                q = ((2 * current[0] - last_quad[0], 2 * current[1] - last_quad[1])
                     if last_quad else current)
                end = (ox + scanner.number(), oy + scanner.number())
                segments.append(_quad(current, q, end))
                current, last_cubic, last_quad = end, None, q
            elif upper == 'A':
                rx, ry, rotation = scanner.number(), scanner.number(), scanner.number()
                large, sweep = scanner.flag(), scanner.flag()
                end = (ox + scanner.number(), oy + scanner.number())
                segments.extend(_arc(current, rx, ry, rotation, large, sweep, end))
                current, last_cubic, last_quad = end, None, None
        except ValueError:
            break   # malformed data: keep what was read so far
    finish(False)
    return subpaths


def _ellipse_segments(cx, cy, rx, ry):
    k = 0.5522847498
    right, top, left, bottom = (cx + rx, cy), (cx, cy + ry), (cx - rx, cy), (cx, cy - ry)
    return [(right, (cx + rx, cy + k * ry), (cx + k * rx, cy + ry), top),
            (top, (cx - k * rx, cy + ry), (cx - rx, cy + k * ry), left),
            (left, (cx - rx, cy - k * ry), (cx - k * rx, cy - ry), bottom),
            (bottom, (cx + k * rx, cy - ry), (cx + rx, cy - k * ry), right)]


def _rect_segments(x, y, w, h, rx, ry):
    if rx <= 0 and ry <= 0:
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return [_line(a, b) for a, b in zip(corners, corners[1:] + corners[:1])]
    rx = min(rx if rx > 0 else ry, w / 2.0)
    ry = min(ry if ry > 0 else rx, h / 2.0)
    d = (f'M{x + rx},{y} H{x + w - rx} A{rx},{ry} 0 0 1 {x + w},{y + ry} V{y + h - ry} '
         f'A{rx},{ry} 0 0 1 {x + w - rx},{y + h} H{x + rx} A{rx},{ry} 0 0 1 {x},{y + h - ry} '
         f'V{y + ry} A{rx},{ry} 0 0 1 {x + rx},{y} Z')
    return parse_path(d)[0][0]


# --- styles ----------------------------------------------------------------------------

_INHERITED = ('fill', 'stroke', 'stroke-width', 'fill-opacity', 'stroke-opacity',
              'stroke-dasharray', 'display', 'visibility', 'fill-rule', 'stroke-linejoin',
              'stroke-linecap')


def _style_of(element, classes):
    style = {}
    for name in element.get('class', '').split():
        style.update(classes.get(name, {}))
    for key in _INHERITED + ('opacity',):
        if element.get(key) is not None:
            style[key] = element.get(key)
    for part in (element.get('style') or '').split(';'):
        if ':' in part:
            key, value = part.split(':', 1)
            style[key.strip()] = value.strip()
    return style


def _css_classes(root):
    classes = {}
    for element in root.iter():
        if _tag(element) != 'style' or not element.text:
            continue
        for selectors, body in re.findall(r'([^{}]+)\{([^}]*)\}', element.text):
            declarations = {}
            for part in body.split(';'):
                if ':' in part:
                    key, value = part.split(':', 1)
                    declarations[key.strip()] = value.strip()
            for selector in selectors.split(','):
                selector = selector.strip()
                if re.fullmatch(r'\.[\w-]+', selector):
                    classes.setdefault(selector[1:], {}).update(declarations)
    return classes


def _tag(element):
    return element.tag.rsplit('}', 1)[-1] if isinstance(element.tag, str) else ''


def _float(value, default=0.0):
    if value is None:
        return default
    match = re.match(_NUMBER, value.strip())
    return float(match.group(0)) if match else default


# --- reading ---------------------------------------------------------------------------

def parse_svg(text):
    """Every outline of an SVG document.

    Returns one entry per drawn element: [{'contours': [segments, ...], 'name': str,
    'fill': color or None, 'fill_opacity': float, 'fill_rule': 'nonzero' or 'evenodd',
    'stroke': color or None, 'stroke_width': float, 'stroke_opacity': float,
    'dashed': bool}], with points in canvas space (y up) and every transform already
    applied. Each contour is a list of cubic segments; 'closed' says, per contour,
    whether the subpath ended with Z (rectangles, circles and polygons always do).
    """
    root = ET.fromstring(text)
    classes = _css_classes(root)
    outlines = []

    def visit(element, matrix, inherited, opacity):
        tag = _tag(element)
        if tag in {'defs', 'clipPath', 'mask', 'symbol', 'style', 'title', 'desc',
                   'metadata', 'linearGradient', 'radialGradient', 'pattern', 'marker'}:
            return
        style = dict(inherited)
        own = _style_of(element, classes)
        style.update({k: v for k, v in own.items() if k != 'opacity'})
        opacity *= _float(own.get('opacity'), 1.0)
        if style.get('display') == 'none' or style.get('visibility') == 'hidden':
            return
        matrix = multiply(matrix, parse_transform(element.get('transform')))
        found = []
        if tag == 'path':
            found = parse_path(element.get('d'))
        elif tag == 'rect':
            w, h = _float(element.get('width')), _float(element.get('height'))
            if w > 0 and h > 0:
                found = [(_rect_segments(_float(element.get('x')), _float(element.get('y')), w, h,
                                         _float(element.get('rx')), _float(element.get('ry'))),
                          True)]
        elif tag in {'circle', 'ellipse'}:
            if tag == 'circle':
                rx = ry = _float(element.get('r'))
            else:
                rx, ry = _float(element.get('rx')), _float(element.get('ry'))
            if rx > 0 and ry > 0:
                found = [(_ellipse_segments(_float(element.get('cx')), _float(element.get('cy')),
                                            rx, ry), True)]
        elif tag == 'line':
            start = (_float(element.get('x1')), _float(element.get('y1')))
            end = (_float(element.get('x2')), _float(element.get('y2')))
            if start != end:
                found = [([_line(start, end)], False)]
        elif tag in {'polygon', 'polyline'}:
            values = [float(v) for v in re.findall(_NUMBER, element.get('points') or '')]
            points = list(zip(values[0::2], values[1::2]))
            if len(points) >= 2:
                ends = points[1:] + points[:1] if tag == 'polygon' else points[1:]
                found = [([_line(a, b) for a, b in zip(points, ends)], tag == 'polygon')]
        for child in element:
            visit(child, matrix, style, opacity)
        if not found:
            return
        scale = math.sqrt(abs(matrix[0] * matrix[3] - matrix[1] * matrix[2])) or 1.0
        # A <line> is never filled, whatever its fill says.
        fill = None if tag == 'line' else parse_color(style.get('fill', 'black'))
        stroke = parse_color(style.get('stroke', 'none'))
        dash = style.get('stroke-dasharray', 'none').strip().lower()
        contours = [[tuple((x, -y) for x, y in (apply(matrix, p) for p in segment))
                     for segment in segments] for segments, _closed in found]
        closed = [flag for _segments, flag in found]
        rule = style.get('fill-rule', 'nonzero').strip().lower()
        outlines.append({
            'contours': contours, 'closed': closed, 'name': element.get('id') or '',
            'fill': fill, 'fill_opacity': _float(style.get('fill-opacity'), 1.0) * opacity,
            'fill_rule': 'evenodd' if rule == 'evenodd' else 'nonzero',
            'stroke': stroke, 'stroke_width': _float(style.get('stroke-width'), 1.0) * scale,
            'stroke_opacity': _float(style.get('stroke-opacity'), 1.0) * opacity,
            'dashed': dash not in {'', 'none', '0'},
            'join': {'miter': 'MITER', 'miter-clip': 'MITER', 'arcs': 'MITER', 'bevel': 'BEVEL',
                     'round': 'ROUND'}.get(style.get('stroke-linejoin', 'miter').strip().lower(),
                                           'MITER'),
            'cap': {'butt': 'FLAT', 'square': 'SQUARE', 'round': 'ROUND'}.get(
                style.get('stroke-linecap', 'butt').strip().lower(), 'FLAT'),
        })

    visit(root, IDENTITY, {}, 1.0)
    return outlines


def _close(a, b, eps):
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def outline_records(segments, eps=1e-6, closed=True):
    """Vertex records (co, type, left, right) of an outline, in canvas space.

    Zero-length segments are dropped. Closed (the default), an open outline is closed
    with a straight edge and fewer than three vertices give []. With `closed` off, the
    path keeps its two ends: one vertex per segment start plus the last end, and fewer
    than two give []. A vertex whose handles both sit on it is Sharp; handles in line
    are Aligned, or Mirrored when they also have the same length; anything else is Free.
    """
    from .shape_geometry import split_cubic
    cleaned = [s for s in segments if not (_close(s[0], s[3], eps) and _close(s[1], s[0], eps)
                                           and _close(s[2], s[3], eps))]
    if not cleaned:
        return []
    if not closed:
        if _close(cleaned[-1][3], cleaned[0][0], eps):
            closed = True   # it comes back to its start: an outline after all
        else:
            ends = [segment[0] for segment in cleaned] + [cleaned[-1][3]]
            lefts = [ends[0]] + [segment[2] for segment in cleaned]
            rights = [segment[1] for segment in cleaned] + [ends[-1]]
            return [(co, _vertex_kind(co, left, right, eps), left, right)
                    for co, left, right in zip(ends, lefts, rights)]
    if not _close(cleaned[-1][3], cleaned[0][0], eps):
        cleaned.append(_line(cleaned[-1][3], cleaned[0][0]))
    # A closed outline needs three vertices: split curved segments until it has them.
    while len(cleaned) < 3:
        curved = [i for i, s in enumerate(cleaned)
                  if not (_close(s[1], s[0], eps) and _close(s[2], s[3], eps))]
        if not curved:
            return []
        i = curved[0]
        first, second = split_cubic(cleaned[i], 0.5)
        cleaned[i:i + 1] = [first, second]
    records = []
    for i, segment in enumerate(cleaned):
        co = segment[0]
        left = cleaned[i - 1][2]
        right = segment[1]
        records.append((co, _vertex_kind(co, left, right, eps), left, right))
    return records


def _vertex_kind(co, left, right, eps):
    at_left, at_right = _close(left, co, eps), _close(right, co, eps)
    if at_left and at_right:
        return 'SHARP'
    if at_left or at_right:
        return 'FREE'
    ax, ay = co[0] - left[0], co[1] - left[1]
    bx, by = right[0] - co[0], right[1] - co[1]
    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
    cross = (ax * by - ay * bx) / (la * lb)
    if abs(cross) < 1e-4 and ax * bx + ay * by > 0:
        return 'MIRRORED' if abs(la - lb) <= max(eps, 1e-4 * max(la, lb)) else 'ALIGNED'
    return 'FREE'


def _sampled(records):
    """A few points along each edge of a closed record outline, for nesting tests."""
    from .shape_geometry import cubic
    points = []
    for i, (co, _, _, right) in enumerate(records):
        following = records[(i + 1) % len(records)]
        controls = (co, right, following[2], following[0])
        points.extend(cubic(controls, t) for t in (0.0, 0.25, 0.5, 0.75))
    return points


def contour_groups(contours, fill_rule='evenodd'):
    """Split an element's contours (vertex record lists) into the shapes they make.

    Kanvas fills with the even-odd rule. With `evenodd`, every contour goes into one
    shape. With `nonzero`, a contour wound the other way round from the contour around
    it is a hole, as in even-odd; one wound the same way would be filled twice over
    (no hole), so it starts a shape of its own, drawn on top. Returns lists of indices,
    outer shapes first.
    """
    from .shape_geometry import point_in_polygon, signed_area
    if fill_rule == 'evenodd' or len(contours) < 2:
        return [list(range(len(contours)))] if contours else []
    rings = [_sampled(records) for records in contours]
    areas = [signed_area(ring) for ring in rings]
    parents = []
    for i, ring in enumerate(rings):
        holders = [j for j, other in enumerate(rings)
                   if j != i and abs(areas[j]) > abs(areas[i])
                   and point_in_polygon(ring[0], other)]
        parents.append(min(holders, key=lambda j: abs(areas[j])) if holders else None)
    roots = {}

    def root(i):
        if i not in roots:
            parent = parents[i]
            if parent is None or (areas[i] > 0) == (areas[parent] > 0):
                roots[i] = i
            else:
                roots[i] = root(parent)
        return roots[i]

    depth = {}

    def level(i):
        if i not in depth:
            depth[i] = 0 if parents[i] is None else level(parents[i]) + 1
        return depth[i]

    groups = {}
    for i in range(len(contours)):
        groups.setdefault(root(i), []).append(i)
    return [groups[key] for key in sorted(groups, key=lambda key: (level(key), key))]


# --- writing ---------------------------------------------------------------------------

def _num(value):
    text = f'{value:.4f}'.rstrip('0').rstrip('.')
    return '0' if text in {'-0', ''} else text


def _escape(text):
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def shape_path_data(item):
    """SVG path data of a shape's outline, rotation and scale included."""
    from . import shape_geometry as sg
    records = sg.item_records(item)
    closed = sg.is_closed(item)
    least = sg.min_vertices(item)
    if len(records) < least:
        return ''
    handles = sg.effective_handles(records, closed)

    def point(unit):
        x, y = sg.unit_to_canvas(item, unit)
        return f'{_num(x)} {_num(-y)}'

    if getattr(item, 'shape_corner_radius', 0.0) > 0.0:
        # Rounded corners exist only in the drawn outline: write that outline.
        return ' '.join('M ' + ' L '.join(f'{_num(x)} {_num(-y)}' for x, y in ring)
                        + (' Z' if closed else '')
                        for ring in sg.outlines(item) if len(ring) >= least)
    parts = []
    for start, stop in sg.contour_ranges(records):
        if stop - start < least:
            continue
        parts.append(f'M {point(records[start][0])}')
        for i in range(start, stop if closed else stop - 1):
            controls = sg.segment_controls(records, handles, i)
            if sg.is_straight(controls):
                if i < stop - 1:
                    parts.append(f'L {point(controls[3])}')
            else:
                parts.append(f'C {point(controls[1])} {point(controls[2])} {point(controls[3])}')
        if closed:
            parts.append('Z')
    return ' '.join(parts)


def _stroke_attributes(item, dash_pattern):
    width = item.shape_line_width
    join = {'ROUND': 'round', 'MITER': 'miter', 'BEVEL': 'bevel'}[item.shape_line_join]
    cap = ('round' if item.shape_line_style == 'DOTTED'
           else {'ROUND': 'round', 'FLAT': 'butt', 'SQUARE': 'square'}[item.shape_line_cap])
    attributes = [f'stroke="{hex_color(item.shape_line_color)}"',
                  f'stroke-width="{_num(width)}"',
                  f'stroke-opacity="{_num(item.opacity)}"',
                  f'stroke-linejoin="{join}"', f'stroke-linecap="{cap}"']
    if join == 'miter':
        attributes.append('stroke-miterlimit="4"')
    if item.shape_line_style != 'SOLID':
        dash, gap = dash_pattern(item.shape_line_style, width)
        attributes.append(f'stroke-dasharray="{_num(dash)} {_num(gap)}"')
    return attributes


def export_svg(items):
    """An SVG document with one <path> (and its text) per shape item."""
    from . import shape_geometry as sg
    from .arrow_geometry import dash_pattern
    bodies = []
    left = bottom = math.inf
    right = top = -math.inf
    for item in items:
        data = shape_path_data(item)
        if not data:
            continue
        margin = item.shape_line_width if item.shape_show_outline else 0.0
        for x, y in sg.outline(item):
            left, right = min(left, x - margin), max(right, x + margin)
            bottom, top = min(bottom, y - margin), max(top, y + margin)
        attributes = [f'id="{_escape(item.name)}"', f'd="{data}"']
        if data.count('M ') > 1:
            attributes.append('fill-rule="evenodd"')
        if item.shape_show_fill:
            attributes.append(f'fill="{hex_color(item.shape_fill_color)}"')
            attributes.append(f'fill-opacity="{_num(item.shape_fill_opacity * item.opacity)}"')
        else:
            attributes.append('fill="none"')
        stroke = _stroke_attributes(item, dash_pattern) if item.shape_show_outline else []
        aligned = stroke and sg.is_closed(item) and item.shape_line_align != 'CENTER'
        if aligned:
            # SVG has no inside or outside line: the line goes on a second path, along
            # the outline moved by half the line width.
            bodies.append(f'  <path {" ".join(attributes)} stroke="none"/>')
            line = ' '.join('M ' + ' L '.join(f'{_num(x)} {_num(-y)}' for x, y in points) + ' Z'
                            for points, _edges in sg.stroke_paths(item) if len(points) >= 2)
            bodies.append(f'  <path id="{_escape(item.name)} line" d="{line}" fill="none" '
                          f'{" ".join(stroke)}/>')
        else:
            bodies.append(f'  <path {" ".join(attributes + stroke)}/>')
        text = ' '.join(line.value for line in item.text_lines if line.value).strip()
        if item.shape_show_text and text:
            cx, cy = item.location[0], -item.location[1]
            size = item.text_font_size * item.scale_master
            bodies.append(
                f'  <text x="{_num(cx)}" y="{_num(cy)}" font-size="{_num(size)}" '
                f'font-family="sans-serif" text-anchor="middle" dominant-baseline="central" '
                f'fill="{hex_color(item.text_color)}" fill-opacity="{_num(item.opacity)}" '
                f'transform="rotate({_num(-item.rotation)} {_num(cx)} {_num(cy)})">'
                f'{_escape(text)}</text>')
    if not bodies:
        return ''
    width, height = right - left, top - bottom
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(width)}" '
            f'height="{_num(height)}" viewBox="{_num(left)} {_num(-top)} {_num(width)} '
            f'{_num(height)}">\n' + '\n'.join(bodies) + '\n</svg>\n')
