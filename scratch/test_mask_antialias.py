"""Check fractional edge coverage and reveal/erase ordering for image masks."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from k_tools_kanvas.utils.gpu.gpu_mask import rasterize_mask


def polygon(points, *, erase=False, sequence=1):
    return SimpleNamespace(
        vertices=[SimpleNamespace(uv=(x / 64, y / 64)) for x, y in points],
        erase=erase, sequence=sequence,
    )


circle = SimpleNamespace(
    uv=(32.25 / 64, 32.25 / 64),
    uv_axis_x=(10 / 64, 0), uv_axis_y=(0, 10 / 64),
    radius_uv=(10 / 64, 10 / 64), erase=False, sequence=1,
)
circle_pixels = rasterize_mask([circle], 64, 64)
assert circle_pixels[32, 32] == 1.0
assert 0.0 < circle_pixels[32, 42] < 1.0
assert circle_pixels[32, 45] == 0.0

reveal = polygon(((10, 10), (54, 10), (54, 54), (10, 54)))
erase = polygon(((20.5, 20), (40, 20), (40, 40), (20.5, 40)),
                erase=True, sequence=2)
pixels = rasterize_mask([], 64, 64, polygons=[reveal, erase])
assert pixels[30, 15] == 1.0
assert pixels[30, 30] == 0.0
assert 0.0 < pixels[30, 20] < 1.0

second_circle = SimpleNamespace(**{**vars(circle), 'uv': (36.25 / 64, 32.25 / 64),
                                   'sequence': 2})
full = rasterize_mask([circle, second_circle], 64, 64)
first = rasterize_mask([circle], 64, 64)
incremental = rasterize_mask([circle, second_circle], 64, 64, first, start=1)
assert np.array_equal(full, incremental)

print('MASK ANTIALIAS PASS')
