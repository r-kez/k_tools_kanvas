"""The boolean engine on its own (pure Python, also runs outside Blender):
union, difference, intersection and exclusion of squares, circles, rings with holes,
shared edges, touching corners and nested shapes, checked by area and by points."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'utils'))
import shape_boolean as sb  # noqa: E402


def square(x, y, size, clockwise=False):
    ring = [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
    return list(reversed(ring)) if clockwise else ring


def circle(cx, cy, r, steps=64):
    return [(cx + r * math.cos(math.tau * i / steps), cy + r * math.sin(math.tau * i / steps))
            for i in range(steps)]


def near(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


a = [square(0, 0, 10)]
b = [square(5, 5, 10)]
assert near(sb.area(sb.boolean(a, b, 'UNION')), 175.0)
assert near(sb.area(sb.boolean(a, b, 'INTERSECT')), 25.0)
assert near(sb.area(sb.boolean(a, b, 'DIFFERENCE')), 75.0)
assert near(sb.area(sb.boolean(a, b, 'EXCLUDE')), 150.0)
union = sb.boolean(a, b, 'UNION')
assert len(union) == 1 and len(union[0]) == 8, union      # collinear points dropped
assert sb._inside((12, 12), union) and not sb._inside((12, 2), union)

# Clockwise input works the same (even-odd does not care about winding).
assert near(sb.area(sb.boolean([square(0, 0, 10, True)], b, 'UNION')), 175.0)

# A hole: the small square cut out of the big one, then filled back by a union.
hole = sb.boolean([square(0, 0, 10)], [square(3, 3, 4)], 'DIFFERENCE')
assert len(hole) == 2 and near(sb.area(hole), 84.0)
assert not sb._inside((5, 5), hole) and sb._inside((1, 1), hole)
assert near(sb.area(sb.boolean(hole, [square(2, 2, 6)], 'UNION')), 100.0)
# Operands that already have holes (even-odd rings).
frame = [square(0, 0, 10), square(3, 3, 4)]
assert near(sb.area(sb.boolean(frame, [square(4, 4, 2)], 'UNION')), 88.0)
assert near(sb.area(sb.boolean(frame, [square(-5, 4, 20)], 'INTERSECT')),
            sb.area(sb.boolean([square(0, 0, 10)], [square(-5, 4, 20)], 'INTERSECT')) - 3 * 4)

# Shared edge: two squares side by side merge into one rectangle.
merged = sb.boolean([square(0, 0, 10)], [square(10, 0, 10)], 'UNION')
assert len(merged) == 1 and len(merged[0]) == 4 and near(sb.area(merged), 200.0), merged
assert sb.boolean([square(0, 0, 10)], [square(10, 0, 10)], 'INTERSECT') == []
# Same square twice.
assert near(sb.area(sb.boolean(a, a, 'UNION')), 100.0)
assert sb.boolean(a, a, 'EXCLUDE') == [] and sb.boolean(a, a, 'DIFFERENCE') == []
# Touching only at a corner: two separate rings.
corner = sb.boolean([square(0, 0, 10)], [square(10, 10, 10)], 'UNION')
assert len(corner) == 2 and near(sb.area(corner), 200.0)
# Nested: the inner one disappears in a union, stays in an intersection.
assert near(sb.area(sb.boolean([square(0, 0, 10)], [square(2, 2, 3)], 'UNION')), 100.0)
assert near(sb.area(sb.boolean([square(0, 0, 10)], [square(2, 2, 3)], 'INTERSECT')), 9.0)
# Disjoint.
assert len(sb.boolean([square(0, 0, 1)], [square(5, 5, 1)], 'UNION')) == 2
assert sb.boolean([square(0, 0, 1)], [square(5, 5, 1)], 'INTERSECT') == []
# Circles: the lens of two overlapping discs, close to the exact value.
lens = sb.boolean([circle(0, 0, 10, 256)], [circle(10, 0, 10, 256)], 'INTERSECT')
exact = 2 * 10 ** 2 * math.acos(0.5) - 5 * math.sqrt(4 * 10 ** 2 - 10 ** 2)
assert len(lens) == 1 and abs(sb.area(lens) - exact) < 0.01 * exact, (sb.area(lens), exact)
# A ring of two circles minus a bar across it: two pieces, each with no hole.
ring = [circle(0, 0, 10), circle(0, 0, 5)]
cut = sb.boolean(ring, [[(-20, -1), (20, -1), (20, 1), (-20, 1)]], 'DIFFERENCE')
assert len(cut) == 2 and all(sb.area([r]) > 0 for r in cut), [sb.area([r]) for r in cut]
# Several operands.
three = sb.combine([[square(0, 0, 10)], [square(5, 0, 10)], [square(10, 0, 10)]], 'UNION')
assert len(three) == 1 and near(sb.area(three), 200.0)
minus = sb.combine([[square(0, 0, 30)], [square(5, 5, 5)], [square(20, 20, 5)]], 'DIFFERENCE')
assert len(minus) == 3 and near(sb.area(minus), 900.0 - 50.0)
# Output orientation: filled areas counter-clockwise, holes clockwise.
for r in hole:
    contained = sum(1 for other in hole if other is not r and sb._inside(r[0], [other]))
    assert (sb.area([r]) > 0) == (contained % 2 == 0)
# A star crossing itself fills by even-odd: its middle is a hole.
star = [(math.cos(math.radians(90 + 144 * i)) * 10, math.sin(math.radians(90 + 144 * i)) * 10)
        for i in range(5)]
pieces = sb.boolean([star], [square(-20, -20, 1)], 'UNION')
assert not sb._inside((0, 0), pieces)
assert sb.area(pieces) > 0

# Crossing detection (decides which fill is used).
assert not sb.rings_cross([square(0, 0, 10)])
assert not sb.rings_cross([square(0, 0, 10), square(3, 3, 4)]), 'a hole inside'
assert not sb.rings_cross([circle(0, 0, 10, 1920)])
assert sb.rings_cross([star])
assert sb.rings_cross([[(0, 0), (10, 10), (10, 0), (0, 10)]]), 'figure eight'
assert sb.rings_cross([square(0, 0, 10), square(5, 5, 10)]), 'overlapping contours'
assert sb.rings_cross([square(0, 0, 10), square(10, 0, 10)]), 'a shared edge'
assert sb.rings_cross([square(0, 0, 10), square(10, 10, 10)]), 'touching at a corner'
assert sb.rings_cross([[(0, 0), (10, 0), (5, 0), (5, 5)]]), 'folding back'

print('SHAPE BOOLEAN CORE PASS')
