"""Real install + download into an empty folder (network; set SAM_NETWORK_DIR to run)."""

import os
import sys
import time
from pathlib import Path

import bpy

target = os.environ.get('SAM_NETWORK_DIR')
if not target:
    print('SAM INSTALL TEST SKIPPED (set SAM_NETWORK_DIR to an empty folder)')
    raise SystemExit(0)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import sam_engine

addon.register()
try:
    libs, models = os.path.join(target, 'libs'), os.path.join(target, 'models')
    sam_engine.libs_dir = lambda: libs
    sam_engine.models_dir = lambda: models
    sam_engine.data_dir = lambda: target
    assert not sam_engine.engine_ready() and not sam_engine.models_ready()

    def wait(section, limit):
        started = time.perf_counter()
        while sam_engine.snapshot(section)['state'] == 'working':
            time.sleep(0.2)
            assert time.perf_counter() - started < limit, f'{section} timed out'
        return sam_engine.snapshot(section)

    assert sam_engine.start_install_engine()
    assert not sam_engine.start_install_engine(), 'a second install must be refused while running'
    state = wait('engine', 600)
    print('engine:', state)
    assert state['state'] == 'done' and sam_engine.engine_ready()
    assert not os.path.isdir(os.path.join(libs, 'numpy')), 'numpy must come from Blender'

    assert sam_engine.start_download_models()
    seen = []
    started = time.perf_counter()
    while sam_engine.snapshot('model')['state'] == 'working':
        seen.append(sam_engine.snapshot('model')['progress'])
        time.sleep(0.2)
        assert time.perf_counter() - started < 600
    state = sam_engine.snapshot('model')
    print('model:', state, f'progress samples {len(seen)}, max {max(seen or [0]):.2f}')
    assert state['state'] == 'done' and sam_engine.models_ready()
    assert not [n for n in os.listdir(models) if n.endswith('.part')]
    assert sam_engine.ready()
    print(f'installed size: {sam_engine.folder_size_mb():.0f} MB')

    sam_engine.remove_files()
    assert not sam_engine.engine_ready() and not sam_engine.models_ready()
    assert not os.path.exists(target) or not os.listdir(target)
    print('SAM INSTALL FLOW OK')
finally:
    addon.unregister()
