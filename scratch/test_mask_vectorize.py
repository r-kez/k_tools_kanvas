"""Mask -> polygon conversion keeps shape, holes and separate islands."""

import sys
import time
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_mask import _rasterize_polygon
from k_tools_kanvas.utils.mask_vectorize import (
    mask_to_polygons, polygons_to_uv, resize_mask)

addon.register()
try:
    H, W = 256, 384
    yy, xx = np.mgrid[0:H, 0:W]
    mask = np.zeros((H, W), bool)
    mask[20:120, 20:150] = True                                  # rectangle with a hole
    mask[50:90, 60:110] = False
    mask |= (xx - 280) ** 2 + (yy - 80) ** 2 <= 45 ** 2          # disk
    mask[170:230, 30:360] = True                                 # long bar ...
    mask[185:200, 100:130] = False                               # ... with a notch
    mask[3, 3] = True                                            # speck

    started = time.perf_counter()
    polygons = mask_to_polygons(mask)
    elapsed = (time.perf_counter() - started) * 1000
    outers = [p for p in polygons if not p['hole']]
    holes = [p for p in polygons if p['hole']]
    assert len(outers) == 3 and len(holes) == 2, (len(outers), len(holes))
    assert not any(p['area'] < 12 for p in polygons), 'speck must be dropped'
    print(f'{len(polygons)} loops ({len(outers)} outer, {len(holes)} holes) in {elapsed:.1f} ms')

    # Rebuild through the addon's own polygon rasterizer and compare.
    tree = bpy.data.node_groups.new('Vec', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    rebuilt = np.zeros((H, W), np.float32)
    for sequence, entry in enumerate(
            sorted(polygons_to_uv(polygons, W, H), key=lambda e: e['hole']), start=1):
        polygon = item.mask_polygons.add()
        polygon.sequence = sequence
        polygon.erase = entry['hole']
        for uv in entry['uv']:
            polygon.vertices.add().uv = uv
        _rasterize_polygon(polygon, rebuilt, W, H)
    truth = mask.copy()
    truth[3, 3] = False
    got = rebuilt > 0.5
    iou = (got & truth).sum() / (got | truth).sum()
    print(f'IoU after polygon round trip: {iou:.4f}')
    assert iou > 0.985, iou

    # Simplification really shrinks the data.
    raw_points = sum(len(l) for l in __import__(
        'k_tools_kanvas.utils.mask_vectorize', fromlist=['x'])._boundary_loops(mask))
    kept = sum(len(p['points']) for p in polygons)
    assert kept < raw_points / 5, (kept, raw_points)
    print(f'vertices: {raw_points} raw -> {kept} simplified')

    # Realistic size: a blobby 512x512 mask.
    big = np.zeros((512, 512), bool)
    rng = np.random.default_rng(2)
    for _ in range(25):
        cx, cy, r = rng.integers(60, 450, 2).tolist() + [int(rng.integers(15, 70))]
        yy2, xx2 = np.mgrid[0:512, 0:512]
        big |= (xx2 - cx) ** 2 + (yy2 - cy) ** 2 <= r * r
    started = time.perf_counter()
    blob = mask_to_polygons(big)
    print(f'512x512 blobs: {len(blob)} loops, {sum(len(p["points"]) for p in blob)} vertices, '
          f'{(time.perf_counter() - started) * 1000:.0f} ms')

    small = resize_mask(mask, 128, 192)
    assert small.shape == (128, 192) and small.any()
    print('MASK VECTORIZE OK')
finally:
    addon.unregister()
