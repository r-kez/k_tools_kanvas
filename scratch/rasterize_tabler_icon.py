"""Rasterize a Tabler outline SVG (stroke-only paths) into a white PNG icon.

Usage: python rasterize_tabler_icon.py <icon.svg> <out.png> [size]

Supports the path commands Tabler outline icons use (M m L l H h V v A a C c Z z).
The result is a white stroke on transparent, like the other icons in assets/icons.
"""

import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SUPERSAMPLE = 16


def tokens(data):
    for match in re.finditer(r'([MmLlHhVvAaCcZz])|(-?\d*\.?\d+(?:e-?\d+)?)', data):
        yield match.group(1) or float(match.group(2))


def arc_points(start, rx, ry, rotation, large, sweep, end, steps=24):
    """SVG endpoint arc -> polyline (W3C implementation notes, F.6.5)."""
    (x1, y1), (x2, y2) = start, end
    if rx == 0 or ry == 0 or start == end:
        return [end]
    phi = math.radians(rotation)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cos_p * dx + sin_p * dy, -sin_p * dx + cos_p * dy
    rx, ry = abs(rx), abs(ry)
    scale = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    numerator = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    denominator = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    factor = math.sqrt(max(0.0, numerator / denominator)) * (-1 if large == sweep else 1)
    cxp, cyp = factor * rx * y1p / ry, -factor * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        value = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return value

    theta = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                  (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    points = []
    for index in range(1, steps + 1):
        t = theta + delta * index / steps
        x = cx + rx * math.cos(t) * cos_p - ry * math.sin(t) * sin_p
        y = cy + rx * math.cos(t) * sin_p + ry * math.sin(t) * cos_p
        points.append((x, y))
    points[-1] = end
    return points


def cubic_points(p0, p1, p2, p3, steps=20):
    return [((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0],
             (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1])
            for t in (i / steps for i in range(1, steps + 1))]


def parse_path(data):
    """Return a list of polylines."""
    stream = list(tokens(data))
    polylines, current, position, start, command = [], [], (0.0, 0.0), (0.0, 0.0), None
    index = 0

    def number():
        nonlocal index
        value = stream[index]
        index += 1
        return value

    while index < len(stream):
        if isinstance(stream[index], str):
            command = stream[index]
            index += 1
            if command in 'Zz':
                if current:
                    current.append(start)
                    position = start
                continue
        relative = command.islower()
        kind = command.upper()
        ox, oy = position if relative else (0.0, 0.0)
        if kind == 'M':
            if current:
                polylines.append(current)
            position = (ox + number(), oy + number())
            start, current = position, [position]
            command = 'l' if relative else 'L'
        elif kind == 'L':
            position = (ox + number(), oy + number())
            current.append(position)
        elif kind == 'H':
            position = (ox + number() if relative else number(), position[1])
            current.append(position)
        elif kind == 'V':
            position = (position[0], oy + number() if relative else number())
            current.append(position)
        elif kind == 'A':
            rx, ry, rotation = number(), number(), number()
            large, sweep = int(number()), int(number())
            end = (ox + number(), oy + number())
            current.extend(arc_points(position, rx, ry, rotation, large, sweep, end))
            position = end
        elif kind == 'C':
            p1 = (ox + number(), oy + number())
            p2 = (ox + number(), oy + number())
            end = (ox + number(), oy + number())
            current.extend(cubic_points(position, p1, p2, end))
            position = end
        else:
            raise ValueError(f'Unsupported path command {command!r}')
    if current:
        polylines.append(current)
    return polylines


def rasterize(svg_path, out_path, size=64):
    text = Path(svg_path).read_text(encoding='utf-8')
    view = [float(v) for v in re.search(r'viewBox="([^"]+)"', text).group(1).split()]
    stroke = float(re.search(r'stroke-width="([\d.]+)"', text).group(1))
    big = size * SUPERSAMPLE
    scale = big / view[2]
    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = stroke * scale / 2
    for data in re.findall(r'<path[^>]*\sd="([^"]+)"', text):
        for line in parse_path(data):
            points = [((x - view[0]) * scale, (y - view[1]) * scale) for x, y in line]
            if len(points) > 1:
                draw.line(points, fill=(255, 255, 255, 255), width=round(radius * 2), joint='curve')
            for x, y in points:   # round caps and joins
                draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                             fill=(255, 255, 255, 255))
    image.resize((size, size), Image.LANCZOS).save(out_path)


if __name__ == '__main__':
    rasterize(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 64)
    print('wrote', sys.argv[2])
