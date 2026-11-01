"""Auto Select inside the Mask/Color painters: click -> outline -> commit -> undo/redo.

Needs SAM_LIBS and SAM_MODELS (folders with onnxruntime and the ONNX models).
"""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy
import numpy as np

libs, models = os.environ.get('SAM_LIBS'), os.environ.get('SAM_MODELS')
if not (libs and models):
    print('AUTO SELECT PAINTER TEST SKIPPED (set SAM_LIBS and SAM_MODELS)')
    raise SystemExit(0)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_mask import MaskPainterMixin
from k_tools_kanvas.operators.ops_markup import _MarkupEditProxy, _add_region
from k_tools_kanvas.utils import sam_engine
from k_tools_kanvas.utils.gpu.gpu_mask import mask_dimensions, rasterize_mask

addon.register()
try:
    sam_engine.libs_dir = lambda: libs
    sam_engine.models_dir = lambda: models

    width, height = 640, 480
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:height, 0:width]
    rgb = np.clip(rng.normal(0.43, 0.1, (height, width, 3)), 0, 1)
    rgb[:, :, 2] += np.linspace(0, 0.23, width)[None, :]
    disk = (xx - 400) ** 2 + (yy - 200) ** 2 <= 80 ** 2        # top-down
    rgb[disk] = (0.86, 0.16, 0.16)
    image = bpy.data.images.new('painter-test', width, height, alpha=True)
    rgba = np.ones((height, width, 4), np.float32)
    rgba[:, :, :3] = rgb[::-1].clip(0, 1)
    image.pixels.foreach_set(rgba.ravel())
    image.update()

    tree = bpy.data.node_groups.new('Painter', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_type = 'IMAGE'
    item.item_id = 'img'
    item.image_data = image

    assert sam_engine.start_analyze(image)
    started = time.perf_counter()
    while sam_engine.snapshot('analyze')['state'] == 'working':
        time.sleep(0.05)
        assert time.perf_counter() - started < 60
    assert sam_engine.is_analyzed(image)

    class Painter(MaskPainterMixin):
        def __init__(self):
            self._area = SimpleNamespace(tag_redraw=lambda: None)
            self._history, self._history_index = [], 0
            self._sam_points, self._sam_loops = [], []
            self._alt_held = False
            self._stroke_start_count = None
            self._painting = False
            self._last_uv = None
            self._stroke_anchor_uv = None
            self.reports = []

        def report(self, kinds, message):
            self.reports.append(message)

    def disk_iou(polygons, tool_item):
        mw, mh = mask_dimensions(image)
        raster = rasterize_mask(tool_item.mask_dabs, mw, mh, polygons=polygons)
        truth = np.zeros((mh, mw), bool)
        sy, sx = np.mgrid[0:mh, 0:mw]
        px, py = (sx + 0.5) * width / mw, (sy + 0.5) * height / mh
        truth = (px - 400) ** 2 + (height - py - 200) ** 2 <= 80 ** 2   # bottom-up rows
        got = raster > 0.5
        return (got & truth).sum() / max(1, (got | truth).sum())

    # ---- Mask mode ------------------------------------------------------
    painter = Painter()
    assert painter._sam_ready(item)
    painter._sam_points.append(((400 / width, 1 - 200 / height), 1))
    painter._sam_update(item)
    assert painter._sam_loops, 'the click must produce an outline'
    assert painter._sam_commit(item)
    assert not painter._sam_points and not painter._sam_loops
    assert len(item.mask_polygons) >= 1 and item.mask_revision >= 1
    iou = disk_iou(item.mask_polygons, item)
    print(f'mask mode: {len(item.mask_polygons)} polygon(s), IoU {iou:.3f}')
    assert iou > 0.95

    painter._history_step(item, False)
    assert len(item.mask_polygons) == 0, 'undo must remove the whole selection'
    painter._history_step(item, True)
    assert len(item.mask_polygons) >= 1 and disk_iou(item.mask_polygons, item) > 0.95

    # ---- Erase mode ignores holes ---------------------------------------
    erase_painter = Painter()
    item.mask_erase = True
    donut = [
        {'uv': [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)], 'hole': False, 'area': 1},
        {'uv': [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)], 'hole': True, 'area': 1}]
    erase_painter._sam_loops = list(donut)
    before = len(item.mask_polygons)
    assert erase_painter._sam_commit(item)
    assert len(item.mask_polygons) == before + 1 and item.mask_polygons[before].erase
    assert any('Holes' in text for text in erase_painter.reports)
    item.mask_erase = False

    # ---- Paint mode applies holes as erase polygons ---------------------
    hole_painter = Painter()
    hole_painter._sam_loops = list(donut)
    start = len(item.mask_polygons)
    assert hole_painter._sam_commit(item)
    outer, hole = item.mask_polygons[start], item.mask_polygons[start + 1]
    assert not outer.erase and hole.erase and hole.sequence > outer.sequence

    # ---- Color mode (proxy over the active region) ----------------------
    region = _add_region(item)
    proxy = _MarkupEditProxy(item)
    color_painter = Painter()
    color_painter._sam_points.append(((400 / width, 1 - 200 / height), 1))
    color_painter._sam_update(proxy)
    assert color_painter._sam_commit(proxy)
    assert len(region.polygons) >= 1 and item.markup_revision >= 1
    print(f'color mode: {len(region.polygons)} polygon(s) in region {region.name!r}')
    color_painter._history_step(proxy, False)
    assert len(region.polygons) == 0

    # ---- Excluding point shrinks the preview ----------------------------
    refine = Painter()
    refine._sam_points.append(((400 / width, 1 - 200 / height), 1))
    refine._sam_update(item)
    full = sum(entry['area'] for entry in refine._sam_loops if not entry['hole'])
    refine._sam_points.append(((400 / width, 1 - 130 / height), 0))
    refine._sam_update(item)
    smaller = sum(entry['area'] for entry in refine._sam_loops if not entry['hole'])
    assert smaller < full
    refine._sam_points.pop()
    refine._sam_update(item)
    assert abs(sum(e['area'] for e in refine._sam_loops if not e['hole']) - full) < 1

    sam_engine.release_decoder()
    print('AUTO SELECT PAINTER OK')
finally:
    addon.unregister()
