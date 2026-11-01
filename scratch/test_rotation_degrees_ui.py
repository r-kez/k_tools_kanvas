"""Keep stored Kanvas rotations in degrees while the UI uses Blender angles."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.utils.gpu.gpu_common import rotate_point


addon.register()
try:
    item = get_settings(bpy.context).images.add()
    item.rotation = 90.0
    assert math.isclose(item.rotation_ui, -math.pi / 2, abs_tol=1e-5)
    item.rotation_ui = math.pi
    assert math.isclose(item.rotation, -180.0, abs_tol=1e-5)
    item.rotation_ui = math.pi / 2
    x, y = rotate_point((1.0, 0.0), (0.0, 0.0), item.rotation)
    assert math.isclose(x, 0.0, abs_tol=1e-5)
    assert math.isclose(y, -1.0, abs_tol=1e-5)
    print('ROTATION DEGREES UI PASS')
finally:
    addon.unregister()
