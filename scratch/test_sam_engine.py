"""End-to-end Auto Select engine check (skipped unless a model folder is provided).

Set SAM_LIBS and SAM_MODELS to folders holding onnxruntime and the two ONNX files.
"""

import os
import sys
import time
from pathlib import Path

import bpy
import numpy as np

libs, models = os.environ.get('SAM_LIBS'), os.environ.get('SAM_MODELS')
if not (libs and models):
    print('SAM ENGINE TEST SKIPPED (set SAM_LIBS and SAM_MODELS)')
    raise SystemExit(0)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import sam_engine
from k_tools_kanvas.utils.mask_vectorize import mask_to_polygons, resize_mask

addon.register()
try:
    sam_engine.libs_dir = lambda: libs
    sam_engine.models_dir = lambda: models
    assert sam_engine.engine_ready() and sam_engine.models_ready()

    # A synthetic image: red disk on a noisy gradient, drawn bottom-up like Blender.
    width, height = 640, 480
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:height, 0:width]
    rgb = np.clip(rng.normal(0.43, 0.1, (height, width, 3)), 0, 1)
    rgb[:, :, 2] += np.linspace(0, 0.23, width)[None, :]
    disk_top_down = (xx - 400) ** 2 + (yy - 200) ** 2 <= 80 ** 2
    rgb[disk_top_down] = (0.86, 0.16, 0.16)
    image = bpy.data.images.new('sam-test', width, height, alpha=True)
    rgba = np.ones((height, width, 4), np.float32)
    rgba[:, :, :3] = rgb[::-1].clip(0, 1)          # bottom row first
    image.pixels.foreach_set(rgba.ravel())
    image.update()

    assert not sam_engine.is_analyzed(image)
    assert sam_engine.start_analyze(image)
    started = time.perf_counter()
    while sam_engine.snapshot('analyze')['state'] == 'working':
        time.sleep(0.05)
        assert time.perf_counter() - started < 60, 'analysis timed out'
    state = sam_engine.snapshot('analyze')
    assert state['state'] == 'done', state
    print('analyze:', state['message'])
    embedding = sam_engine.get_embedding(image)
    assert embedding is not None and sam_engine.is_analyzed(image)

    started = time.perf_counter()
    mask = sam_engine.decode(embedding, [(400, 200, 1)])
    print(f'decode (incl. session load): {(time.perf_counter() - started) * 1000:.0f} ms')
    started = time.perf_counter()
    mask = sam_engine.decode(embedding, [(400, 200, 1)])
    print(f'decode: {(time.perf_counter() - started) * 1000:.0f} ms')
    assert mask.shape == (height, width)
    iou = (mask & disk_top_down).sum() / (mask | disk_top_down).sum()
    print(f'IoU vs disk: {iou:.3f}')
    assert iou > 0.95

    # Vectorize like the painter does: flip to bottom-up, then to mask resolution.
    from k_tools_kanvas.utils.gpu.gpu_mask import mask_dimensions
    mw, mh = mask_dimensions(image)
    polygons = mask_to_polygons(resize_mask(mask[::-1], mh, mw))
    assert len(polygons) == 1 and not polygons[0]['hole']
    print(f'{len(polygons[0]["points"])} polygon vertices at {mw}x{mh}')

    # An excluding point on the disk shrinks the result.
    smaller = sam_engine.decode(embedding, [(400, 200, 1), (400, 130, 0)])
    assert smaller.sum() < mask.sum()

    # Changing the image invalidates the cached analysis.
    image.scale(320, 240)
    assert not sam_engine.is_analyzed(image)

    # Swapping the content for another file of the same size also invalidates it.
    image2 = bpy.data.images.new('sam-test-2', width, height)
    assert sam_engine.start_analyze(image2)
    while sam_engine.snapshot('analyze')['state'] == 'working':
        time.sleep(0.05)
    assert sam_engine.is_analyzed(image2)
    image2.filepath = r'C:/somewhere/else.png'
    assert not sam_engine.is_analyzed(image2), 'a different source must drop the analysis'

    # Online access switched off blocks the downloads with a clear message.
    previous = getattr(bpy.app, 'online_access', True)
    sam_engine.online_blocked = lambda: 'Blender online access is off'
    assert not sam_engine.start_install_engine() and not sam_engine.start_download_models()
    assert 'online access' in sam_engine.snapshot('engine')['message']
    assert sam_engine.snapshot('model')['state'] == 'error'

    sam_engine.shutdown()
    print('SAM ENGINE OK')
finally:
    addon.unregister()
