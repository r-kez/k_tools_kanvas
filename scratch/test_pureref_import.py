"""Run with Blender --background --python this_file -- scene.pur."""

from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_image import image_origin
from k_tools_kanvas.utils.pureref import read_pureref


source = Path(sys.argv[sys.argv.index('--') + 1])
scene = read_pureref(source)
addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('PureRef Import Test', 'KanvasNodeTree')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.import_pureref(filepath=str(source)) == {'FINISHED'}
        settings = area.spaces.active.edit_tree.kanvas_settings
        assert len(settings.images) == len(scene.images)
        assert len({item.image_data.as_pointer() for item in settings.images}) == len(
            {record.image_id for record in scene.images})
        for item, record in zip(settings.images, scene.images):
            assert item.image_data.packed_file
            assert image_origin(item.image_data) == ('PUR', str(source.resolve()))
            assert not item.image_data.filepath
            assert abs(item.location[0] - record.center[0]) < 0.02
            assert abs(item.location[1] - record.center[1]) < 0.02
            assert abs(item.rotation - record.rotation) < 0.02
            assert abs(item.scale_xy[0] * item.image_data.size[0]
                       - record.scale[0] * record.source_size[0]) < 0.1
        assert not bpy.ops.kanvas.open_image_source.poll()
    print(f'PUREREF IMPORT PASS: {len(scene.images)} items')
finally:
    addon.unregister()
