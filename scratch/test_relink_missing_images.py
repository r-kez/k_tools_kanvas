"""Relink multiple missing external references from one replacement folder."""
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_image import missing_external_items


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Relink test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        original = Path(temp_dir) / 'original'
        replacement = Path(temp_dir) / 'replacement'
        original.mkdir()
        replacement.mkdir()
        for number in (1, 2):
            path = original / f'image{number}.png'
            source = bpy.data.images.new(f'Relink source {number}', 8 * number, 8)
            source.filepath_raw = str(path)
            source.file_format = 'PNG'
            source.save()
            bpy.data.images.remove(source)
            loaded = bpy.data.images.load(str(path), check_existing=False)
            item = settings.images.add()
            item.item_type = 'IMAGE'
            item.image_data = loaded
            item.name = f'Reference {number}'
            item.location = (number * 100, -50)
            path.rename(replacement / path.name)

        packed = settings.images.add()
        packed.item_type = 'IMAGE'
        packed_path = original / 'packed.png'
        packed_source = bpy.data.images.new('Packed source', 4, 4)
        packed_source.filepath_raw = str(packed_path)
        packed_source.file_format = 'PNG'
        packed_source.save()
        bpy.data.images.remove(packed_source)
        packed.image_data = bpy.data.images.load(str(packed_path), check_existing=False)
        packed.image_data.pack()
        packed.item_id = 'packed-test-item'
        packed_image = packed.image_data
        assert packed_image.packed_file is not None
        assert len(missing_external_items(settings)) == 2

        with bpy.context.temp_override(area=area, region=region,
                                       space_data=area.spaces.active):
            assert bpy.ops.kanvas.relink_missing_images(directory=str(replacement)) == {'FINISHED'}
            assert not missing_external_items(settings)
            assert sorted(item.name for item in settings.images if item.name.startswith('Reference')) == [
                'Reference 1', 'Reference 2']
            for item in settings.images:
                if item.name.startswith('Reference'):
                    assert tuple(item.location) in {(100, -50), (200, -50)}
                    assert Path(item.image_data['kanvas_source_path']).parent == replacement
            packed = next(item for item in settings.images if item.item_id == 'packed-test-item')
            assert packed.image_data == packed_image
            assert packed.image_data.packed_file is not None
    print('RELINK MISSING IMAGES PASS')
finally:
    addon.unregister()
