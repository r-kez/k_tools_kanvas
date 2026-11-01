"""Check the screen-sized soft edge built around arrow silhouettes."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from k_tools_kanvas.utils.gpu.gpu_arrow import (
    _antialias_fringe, _label_center_y, _label_width_limit,
)


outline = [(0, 1), (8, 1), (8, 3), (12, 0),
           (8, -3), (8, -1), (0, -1)]
vertices, colors = _antialias_fringe(outline, 1.0, (1.0, 0.7, 0.2, 0.8))
assert len(vertices) == len(colors) == 6 * len(outline) + 3 * 5
assert vertices[:6] == [(0, 1), (8, 1), (8, 2),
                        (0, 1), (8, 2), (0, 2)]
assert [color[3] for color in colors[:6]] == [0.8, 0.8, 0.0, 0.8, 0.0, 0.0]
assert all(math.isfinite(value) for point in vertices for value in point)
assert _label_center_y(100, 14, 5, False, 200) == 100
assert _label_center_y(100, 14, 5, True, 200) == 128
assert _label_center_y(180, 14, 5, True, 200) == 152
assert _label_width_limit((0, 0), (100, 0), 1000) == 66
assert _label_width_limit((0, 0), (500, 0), 1000) == 240
assert _label_width_limit((0, 0), (10, 0), 1000) < 0

print('PASS arrow antialias fringe')
