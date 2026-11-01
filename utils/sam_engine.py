"""Optional Auto Select support (MobileSAM through ONNX Runtime).

Nothing in this module runs unless the user explicitly installs the engine,
downloads the model and presses Analyze Image. Heavy work happens in worker
threads that never touch `bpy` data; the UI polls `status` with a short-lived
timer, so no modal operator is ever left running (that would block auto save).
"""

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from collections import OrderedDict

import bpy
import numpy as np

MODEL_URL = 'https://huggingface.co/Heliosoph/sam-onnx/resolve/main/'
MODEL_FILES = {
    'mobile_sam_image_encoder.onnx': 20_000_000,   # minimum plausible size in bytes
    'sam_mask_decoder_single.onnx': 10_000_000,
}
ENGINE_PACKAGES = ('onnxruntime', 'packaging', 'protobuf')
MODEL_LICENSE = 'Apache-2.0 (MobileSAM encoder + Meta SAM decoder)'
INPUT_SIZE = 1024
MAX_CACHED_IMAGES = 8

_lock = threading.Lock()
status = {
    'engine': {'state': 'idle', 'message': ''},
    'model': {'state': 'idle', 'message': '', 'progress': 0.0},
    'analyze': {'state': 'idle', 'message': '', 'image': ''},
}
_embeddings = OrderedDict()      # image name -> Embedding
_decoder = {'session': None}


def _set(section, **values):
    with _lock:
        status[section].update(values)


def snapshot(section):
    with _lock:
        return dict(status[section])


def busy():
    with _lock:
        return any(entry['state'] == 'working' for entry in status.values())


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

def data_dir():
    # Kept short: ONNX Runtime ships deeply nested files and Windows limits paths.
    return bpy.utils.user_resource('DATAFILES', path='k_tools_kanvas/sam', create=True)


def libs_dir():
    return os.path.join(data_dir(), 'libs')


def models_dir():
    return os.path.join(data_dir(), 'models')


def _model_path(name):
    return os.path.join(models_dir(), name)


def ensure_libs_on_path():
    path = libs_dir()
    if os.path.isdir(path) and path not in sys.path:
        # Appended so Blender's own packages (numpy) always win.
        sys.path.append(path)
        importlib.invalidate_caches()


_ready_cache = {}


def _cached(name, compute, ttl=2.0):
    """Panels redraw constantly; do the filesystem checks at most every `ttl` s."""
    now = time.monotonic()
    entry = _ready_cache.get(name)
    if entry is None or now - entry[0] > ttl:
        entry = (now, compute())
        _ready_cache[name] = entry
    return entry[1]


def _invalidate_ready():
    _ready_cache.clear()


def engine_ready():
    def check():
        ensure_libs_on_path()
        return importlib.util.find_spec('onnxruntime') is not None
    return _cached('engine', check)


def models_ready():
    return _cached('models', lambda: all(
        os.path.isfile(_model_path(name)) and os.path.getsize(_model_path(name)) >= minimum
        for name, minimum in MODEL_FILES.items()))


def ready():
    return engine_ready() and models_ready()


_EXTENDED_PREFIX = '\\\\?\\'   # the four characters  \\?\


def _long_path(path):
    """Windows extended-length form, so very deep paths can still be read and deleted."""
    if os.name == 'nt':
        path = os.path.abspath(path)
        if not path.startswith(_EXTENDED_PREFIX):
            return _EXTENDED_PREFIX + path
    return path


def folder_size_mb():
    total = 0
    for root, _dirs, files in os.walk(_long_path(data_dir())):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total / (1024 * 1024)


# ---------------------------------------------------------------------------
# Install / download / remove (explicit user actions)
# ---------------------------------------------------------------------------

def online_blocked():
    """Message when Blender's Allow Online Access is off, otherwise an empty string."""
    if getattr(bpy.app, 'online_access', True):
        return ''
    return ("Blender's online access is off. Enable Preferences > System > "
            "Network > Allow Online Access to download the engine and model.")


def start_install_engine():
    if snapshot('engine')['state'] == 'working':
        return False
    blocked = online_blocked()
    if blocked:
        _set('engine', state='error', message=blocked)
        return False
    _set('engine', state='working', message='Installing ONNX Runtime...')
    threading.Thread(target=_install_engine, daemon=True).start()
    return True


def _install_engine():
    target = libs_dir()
    os.makedirs(target, exist_ok=True)
    command = [sys.executable, '-m', 'pip', 'install', '--no-deps', '--upgrade',
               '--disable-pip-version-check', '--no-warn-script-location',
               '--target', target, *ENGINE_PACKAGES]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as exc:
        _set('engine', state='error', message=f'Could not run pip: {exc}')
        return
    if result.returncode != 0:
        tail = ' '.join((result.stderr or result.stdout).strip().splitlines()[-3:])
        _set('engine', state='error', message=f'pip failed: {tail[:300]}')
        return
    importlib.invalidate_caches()
    _invalidate_ready()
    if engine_ready():
        _set('engine', state='done', message='ONNX Runtime installed.')
    else:
        _set('engine', state='error',
             message='pip finished but onnxruntime cannot be found for this Python.')


def start_download_models():
    if snapshot('model')['state'] == 'working':
        return False
    blocked = online_blocked()
    if blocked:
        _set('model', state='error', message=blocked, progress=0.0)
        return False
    _set('model', state='working', message='Starting download...', progress=0.0)
    threading.Thread(target=_download_models, daemon=True).start()
    return True


def _download_models():
    os.makedirs(models_dir(), exist_ok=True)
    names = list(MODEL_FILES)
    try:
        for index, name in enumerate(names):
            destination = _model_path(name)
            if os.path.isfile(destination) and os.path.getsize(destination) >= MODEL_FILES[name]:
                continue
            partial = destination + '.part'
            request = urllib.request.Request(MODEL_URL + name,
                                             headers={'User-Agent': 'k_tools_kanvas'})
            with urllib.request.urlopen(request, timeout=30) as response, \
                    open(partial, 'wb') as output:
                total = int(response.headers.get('Content-Length') or 0)
                received = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    received += len(chunk)
                    fraction = (received / total) if total else 0.0
                    _set('model', message=f'Downloading {name} ({index + 1}/{len(names)})',
                         progress=(index + fraction) / len(names))
            if os.path.getsize(partial) < MODEL_FILES[name]:
                os.remove(partial)
                raise RuntimeError(f'{name} downloaded incompletely')
            os.replace(partial, destination)
    except Exception as exc:   # network, disk and HTTP errors all end up here
        _set('model', state='error', message=f'Download failed: {exc}')
        return
    _invalidate_ready()
    _set('model', state='done', message='Model downloaded.', progress=1.0)


def remove_files():
    shutdown()
    shutil.rmtree(_long_path(data_dir()), ignore_errors=True)
    _invalidate_ready()
    for section, values in (('engine', {'state': 'idle', 'message': ''}),
                            ('model', {'state': 'idle', 'message': '', 'progress': 0.0}),
                            ('analyze', {'state': 'idle', 'message': '', 'image': ''})):
        _set(section, **values)
    # Modules already imported keep working until Blender restarts.
    sys.modules.pop('onnxruntime', None)
    if libs_dir() in sys.path:
        sys.path.remove(libs_dir())


# ---------------------------------------------------------------------------
# Image preparation (main thread, reads bpy data)
# ---------------------------------------------------------------------------

def image_key(image):
    return image.name


def _signature(image):
    """Identifies the pixels an analysis belongs to.

    The size alone is not enough: Replace Image or Reload can swap the content
    for another file of the same size.
    """
    packed = image.packed_file
    return (image.size[0], image.size[1], image.filepath,
            len(packed.data) if packed is not None else 0)


def _downscale(rgb, longest):
    """Area-average by an integer factor, then nearest to the exact size."""
    height, width = rgb.shape[:2]
    factor = max(1, max(height, width) // longest)
    if factor > 1:
        height, width = (height // factor) * factor, (width // factor) * factor
        rgb = rgb[:height, :width].reshape(
            height // factor, factor, width // factor, factor, 3).mean(axis=(1, 3))
        height, width = rgb.shape[:2]
    scale = longest / max(height, width)
    new_h, new_w = max(1, round(height * scale)), max(1, round(width * scale))
    ys = np.minimum((np.arange(new_h) / scale).astype(int), height - 1)
    xs = np.minimum((np.arange(new_w) / scale).astype(int), width - 1)
    return np.ascontiguousarray(rgb[ys][:, xs], dtype=np.float32)


def prepare_image(image):
    """Top-down RGB (0..255) at 1024 px on the long side, plus the source size."""
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError('Image has no pixels')
    source = image
    temporary = None
    if max(width, height) > 4096:
        # Avoid holding hundreds of MB of float pixels for huge images.
        temporary = image.copy()
        factor = 4096 / max(width, height)
        temporary.scale(max(1, round(width * factor)), max(1, round(height * factor)))
        source = temporary
    try:
        sw, sh = source.size
        pixels = np.empty(sw * sh * 4, dtype=np.float32)
        source.pixels.foreach_get(pixels)
        is_float = bool(source.is_float)
    finally:
        if temporary is not None:
            bpy.data.images.remove(temporary)
    rgb = pixels.reshape(sh, sw, 4)[::-1, :, :3].clip(0.0, 1.0)   # top row first
    if is_float:
        rgb = rgb ** (1.0 / 2.2)
    return _downscale(rgb * 255.0, INPUT_SIZE), (width, height)


# ---------------------------------------------------------------------------
# Analysis (worker thread) and decoding (main thread, milliseconds)
# ---------------------------------------------------------------------------

class Embedding:
    def __init__(self, data, size, signature):
        self.data = data
        self.width, self.height = size
        self.signature = signature
        self.scale = INPUT_SIZE / max(self.width, self.height)


def _thread_count():
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def _session(model_name):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = _thread_count()
    return ort.InferenceSession(_model_path(model_name), options,
                                providers=['CPUExecutionProvider'])


def start_analyze(image):
    """Prepare on the main thread, then encode in a worker thread."""
    if snapshot('analyze')['state'] == 'working':
        return False
    key, signature = image_key(image), _signature(image)
    try:
        array, size = prepare_image(image)
    except Exception as exc:
        _set('analyze', state='error', message=f'Could not read the image: {exc}', image=key)
        return False
    _set('analyze', state='working', message='Analyzing image...', image=key)
    threading.Thread(target=_analyze, args=(key, signature, array, size),
                     daemon=True).start()
    return True


def _analyze(key, signature, array, size):
    started = time.perf_counter()
    try:
        ensure_libs_on_path()
        session = _session('mobile_sam_image_encoder.onnx')
        data = session.run(None, {'input_image': array})[0]
        del session
    except Exception as exc:
        _set('analyze', state='error', message=f'Analysis failed: {exc}', image=key)
        return
    with _lock:
        _embeddings[key] = Embedding(data, size, signature)
        _embeddings.move_to_end(key)
        while len(_embeddings) > MAX_CACHED_IMAGES:
            _embeddings.popitem(last=False)
    _set('analyze', state='done', image=key,
         message=f'Analyzed in {time.perf_counter() - started:.1f} s')


def get_embedding(image):
    """Embedding for this image if it was analyzed and has not changed since."""
    if image is None:
        return None
    with _lock:
        entry = _embeddings.get(image_key(image))
    if entry is not None and entry.signature == _signature(image):
        return entry
    return None


def is_analyzed(image):
    return get_embedding(image) is not None


def decode(embedding, points):
    """Boolean mask (height, width), top row first, for [(x, y, label)] prompts.

    x/y are source-image pixels from the top-left; label 1 includes, 0 excludes.
    """
    if _decoder['session'] is None:
        ensure_libs_on_path()
        _decoder['session'] = _session('sam_mask_decoder_single.onnx')
    scale = embedding.scale
    coords = np.array([[(x * scale, y * scale) for x, y, _ in points] + [(0.0, 0.0)]],
                      dtype=np.float32)
    labels = np.array([[label for _, _, label in points] + [-1.0]], dtype=np.float32)
    masks = _decoder['session'].run(None, {
        'image_embeddings': embedding.data,
        'point_coords': coords,
        'point_labels': labels,
        'mask_input': np.zeros((1, 1, 256, 256), dtype=np.float32),
        'has_mask_input': np.zeros(1, dtype=np.float32),
        'orig_im_size': np.array([embedding.height, embedding.width], dtype=np.float32),
    })[0]
    return masks[0, 0] > 0


def release_decoder():
    _decoder['session'] = None


def shutdown():
    """Free sessions and cached embeddings (addon disable, files removed)."""
    release_decoder()
    with _lock:
        _embeddings.clear()
