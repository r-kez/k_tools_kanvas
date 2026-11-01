"""Force 8-bit must change the imported pixel storage, not just its color label."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_image import add_image_to_kanvas
from k_tools_kanvas.utils.gpu import gpu_common


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('8-bit import', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    old_prefs = gpu_common.get_prefs
    options = SimpleNamespace(auto_copy=False, use_optimization=True,
                              force_8bit=True, max_image_resolution='0')
    gpu_common.get_prefs = lambda: options
    try:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            path = str(Path(temp_dir) / 'float.exr')
            source = bpy.data.images.new('Float source', 2, 2, float_buffer=True)
            source.pixels[:] = [0.2, 0.4, 0.6, 1.0] * 4
            source.filepath_raw = path
            source.file_format = 'OPEN_EXR'
            source.save()
            bpy.data.images.remove(source)
            with bpy.context.temp_override(area=area, region=region,
                                           space_data=area.spaces.active):
                item = add_image_to_kanvas(bpy.context, path, location=(0, 0))
                assert item and not item.image_data.is_float
                assert item.image_data.packed_file is not None
                assert item.image_data['kanvas_source_path'] == path
                options.force_8bit = False
                other = add_image_to_kanvas(bpy.context, path, location=(200, 0))
                assert other and other.image_data.is_float
                bpy.ops.wm.save_as_mainfile(filepath=str(Path(temp_dir) / 'depth-test.blend'))
                options.auto_copy = True
                options.force_8bit = True
                options.assets_folder = '//assets/kanvas'
                webp = add_image_to_kanvas(bpy.context, path, location=(400, 0))
                assert webp and not webp.image_data.is_float
                assert webp.image_data.filepath.lower().endswith('.webp')
    finally:
        gpu_common.get_prefs = old_prefs
    print('FORCE 8-BIT PASS')
finally:
    addon.unregister()
