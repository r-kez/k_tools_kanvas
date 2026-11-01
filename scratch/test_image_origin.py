"""Check that imported, packed and duplicated images keep their source path."""

import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_image import add_image_to_kanvas, image_origin
from k_tools_kanvas.utils.markdown import safe_link

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Origins', 'KanvasNodeTree')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        source = Path(folder) / 'reference.png'
        original = bpy.data.images.new('Source', 32, 24)
        original.filepath_raw = str(source)
        original.file_format = 'PNG'
        original.save()
        with bpy.context.temp_override(area=area, region=region,
                                       space_data=area.spaces.active):
            item = add_image_to_kanvas(bpy.context, str(source), (0, 0))
            assert item and item.image_data.packed_file
            assert image_origin(item.image_data) == ('FILE', str(source))
            assert bpy.ops.kanvas.open_image_source.poll()
            assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
            settings = area.spaces.active.edit_tree.kanvas_settings
            duplicate = settings.images[settings.active_image_index]
            assert image_origin(duplicate.image_data) == ('FILE', str(source))
            duplicate.image_data['kanvas_source_url'] = 'https://example.org/image.png'
            assert image_origin(duplicate.image_data) == (
                'URL', 'https://example.org/image.png')
            assert safe_link('https://example.org/image.png')
            assert safe_link('https://') is None
            assert safe_link('file:///unexpected.exe') is None
            duplicate.image_data['kanvas_source_url'] = ''
            unsafe_source = Path(folder) / 'unexpected.exe'
            unsafe_source.write_bytes(b'not an image')
            duplicate.image_data['kanvas_source_path'] = str(unsafe_source)
            assert bpy.ops.kanvas.open_image_source() == {'CANCELLED'}
    print('IMAGE ORIGIN PASS')
finally:
    addon.unregister()
