"""A big image comes onto the board smaller (only the scale), and Reset Scale goes back to
that scale, or to 100% when the preference is off."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators import ops_modal
from k_tools_kanvas.operators.ops_image import add_image_to_kanvas
from k_tools_kanvas.utils.gpu import gpu_common


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Import size', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    options = SimpleNamespace(auto_copy=False, use_optimization=True, force_8bit=True,
                              max_image_resolution='0', import_size='500',
                              reset_to_import_scale=True)
    old = gpu_common.get_prefs, ops_modal.get_prefs
    gpu_common.get_prefs = ops_modal.get_prefs = lambda: options
    try:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            paths = {}
            for name, size in (('big', (2000, 1000)), ('small', (200, 100))):
                image = bpy.data.images.new(name, *size)
                paths[name] = str(Path(temp_dir) / f'{name}.png')
                image.filepath_raw = paths[name]
                image.file_format = 'PNG'
                image.save()
                bpy.data.images.remove(image)
            with bpy.context.temp_override(area=area, region=region,
                                           space_data=area.spaces.active):
                settings = tree.kanvas_settings
                big = add_image_to_kanvas(bpy.context, paths['big'], location=(0, 0))
                assert abs(big.scale_master - 0.25) < 1e-6, big.scale_master    # 2000 -> 500
                assert big.image_data.size[0] == 2000                           # pixels kept
                assert abs(big.import_scale - 0.25) < 1e-6
                small = add_image_to_kanvas(bpy.context, paths['small'], location=(300, 0))
                assert small.scale_master == 1.0 and small.import_scale == 1.0   # never enlarged
                options.import_size = '0'
                full = add_image_to_kanvas(bpy.context, paths['big'], location=(600, 0))
                assert full.scale_master == 1.0
                options.import_size = '500'
                big = next(i for i in settings.images if i.item_id == big.item_id)
                big.scale_master = 2.0
                big.is_selected = True
                assert ops_modal.reset_item_transforms(bpy.context, settings, big, 'RESET_SCALE')
                assert abs(big.scale_master - 0.25) < 1e-6                       # import scale
                big.scale_master = 2.0
                options.reset_to_import_scale = False
                assert ops_modal.reset_item_transforms(bpy.context, settings, big, 'RESET_SCALE')
                assert big.scale_master == 1.0                                   # 100%
    finally:
        gpu_common.get_prefs, ops_modal.get_prefs = old
    print('IMPORT SIZE PASS')
finally:
    addon.unregister()
