"""Colors for markup regions and checklist tasks.

The first colors follow a curated sequence; after that, colors are random but
chosen to stay far from the ones already in use, so many regions remain easy to
tell apart.
"""

import colorsys
import math
import random

SEQUENCE = (
    (0.95, 0.34, 0.18),
    (0.20, 0.67, 1.0),
    (0.36, 0.85, 0.45),
    (1.0, 0.76, 0.22),
    (0.72, 0.45, 1.0),
    (1.0, 0.44, 0.72),
)

_CANDIDATES = 48


def _random_color(rng):
    return colorsys.hsv_to_rgb(rng.random(), rng.uniform(0.55, 0.95),
                               rng.uniform(0.85, 1.0))


def distinct_color(existing, rng=random):
    """Random color that maximizes its distance to every color in `existing`."""
    existing = [tuple(color[:3]) for color in existing]
    if not existing:
        return _random_color(rng)
    best, best_distance = None, -1.0
    for _ in range(_CANDIDATES):
        candidate = _random_color(rng)
        distance = min(math.dist(candidate, color) for color in existing)
        if distance > best_distance:
            best, best_distance = candidate, distance
    return best


def color_for_index(index, existing=(), rng=random):
    """Curated color for the first slots, then a distinct random one."""
    if index < len(SEQUENCE):
        return SEQUENCE[index]
    return distinct_color(existing, rng)


def spread_colors(count, rng=random):
    """`count` random colors evenly spread around the hue wheel, shuffled."""
    if count <= 0:
        return []
    offset = rng.random()
    colors = []
    for index in range(count):
        hue = (offset + index / count + rng.uniform(-0.15, 0.15) / count) % 1.0
        colors.append(colorsys.hsv_to_rgb(hue, rng.uniform(0.6, 0.95),
                                          rng.uniform(0.85, 1.0)))
    rng.shuffle(colors)
    return colors
