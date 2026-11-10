"""Mask Resolution: the texture size follows the preference ('IMAGE' is the image up to
4096), painting shows a lighter preview, the CPU analysis stays at 512, and adding
dabs over polygons gives the same pixels as rasterizing everything again."""
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    from k_tools_kanvas.utils.gpu import gpu_mask
    from types import SimpleNamespace
    from k_tools_kanvas.utils.gpu import gpu_common
    from k_tools_kanvas.preferences import KanvasPreferences
    default = KanvasPreferences.bl_rna.properties['mask_resolution'].default
    assert default == 'IMAGE', 'the faithful size by default'
    # Run from a folder, the add-on has no preferences: stand in for them.
    prefs = SimpleNamespace(mask_resolution='IMAGE')
    gpu_common.get_prefs = lambda: prefs
    tree = bpy.data.node_groups.new('Mask resolution', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_type, item.item_id = 'IMAGE', 'photo'
    item.image_data = bpy.data.images.new('photo', 3000, 2000)

    assert gpu_mask.display_dimensions(item) == (3000, 2000)
    prefs.mask_resolution = '1024'
    assert gpu_mask.display_dimensions(item) == (1024, 683)
    prefs.mask_resolution = 'IMAGE'
    big = bpy.data.images.new('big', 8000, 4000)
    item.image_data = big
    assert gpu_mask.display_dimensions(item) == (4096, 2048), 'capped at 4096'
    item.mask_editing = True
    assert gpu_mask.display_dimensions(item) == (1024, 512), 'a lighter preview while painting'
    item.mask_editing = False
    small = bpy.data.images.new('small', 300, 200)
    item.image_data = small
    assert gpu_mask.display_dimensions(item) == (300, 200), 'never larger than the image'
    item.image_data = big
    assert gpu_mask.mask_dimensions(big) == (512, 256), 'analysis stays at 512'

    # --- New dabs over polygons: same pixels as a full rebuild ------------------------
    polygon = item.mask_polygons.add()
    for uv in ((0.1, 0.1), (0.6, 0.1), (0.6, 0.6), (0.1, 0.6)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    for n in range(5):
        dab = item.mask_dabs.add()
        dab.uv, dab.radius_uv = (0.3 + 0.08 * n, 0.5), (0.05, 0.1)
        dab.uv_axis_x, dab.uv_axis_y = (0.05, 0.0), (0.0, 0.1)
        dab.erase = n == 2
        dab.sequence = 2 + n
    w, h = 400, 200
    first = gpu_mask.rasterize_mask(list(item.mask_dabs)[:3], w, h, polygons=item.mask_polygons)
    grown = gpu_mask.rasterize_mask(item.mask_dabs, w, h, first.copy(), start=3)
    full = gpu_mask.rasterize_mask(item.mask_dabs, w, h, polygons=item.mask_polygons)
    assert np.allclose(grown, full), 'appending dabs over polygons matches a rebuild'
    print('test_mask_resolution: OK')
finally:
    addon.unregister()
