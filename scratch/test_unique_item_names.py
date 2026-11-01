"""Check predictable names from Kanvas creation operators."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_image import add_image_to_kanvas
from k_tools_kanvas.utils.kanvas_data import unique_item_name
from k_tools_kanvas.utils.gpu import gpu_common


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Unique names', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        for _ in range(3):
            assert bpy.ops.kanvas.create_text(location=(0, 0)) == {'FINISHED'}
        assert [item.name for item in settings.images] == [
            'Text Note', 'Text Note.001', 'Text Note.002']
        settings.images[0].name = 'Custom card'
        assert bpy.ops.kanvas.create_text(location=(0, 0)) == {'FINISHED'}
        assert settings.images[-1].name == 'Text Note'

        for _ in range(2):
            assert bpy.ops.kanvas.create_text(location=(0, 0), checklist=True) == {'FINISHED'}
        assert [item.name for item in settings.images[-2:]] == ['Checklist', 'Checklist.001']

        for item in settings.images:
            item.is_selected = False
        for _ in range(2):
            assert bpy.ops.kanvas.create_frame(cursor=(0, 0)) == {'FINISHED'}
        assert sorted(item.name for item in settings.images if item.item_type == 'FRAME') == [
            'Kanvas Frame', 'Kanvas Frame.001']

        for _ in range(2):
            assert bpy.ops.kanvas.create_arrow() == {'FINISHED'}
        assert [arrow.name for arrow in settings.arrows] == ['Arrow', 'Arrow.001']
        assert unique_item_name(settings, 'Text Note.001') == 'Text Note.003'

        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            path = str(Path(temp_dir) / 'reference.png')
            source = bpy.data.images.new('Source for names', 8, 8)
            source.filepath_raw = path
            source.file_format = 'PNG'
            source.save()
            bpy.data.images.remove(source)
            old_prefs = gpu_common.get_prefs
            gpu_common.get_prefs = lambda: SimpleNamespace(
                auto_copy=False, use_optimization=False, force_8bit=False,
                max_image_resolution='0')
            try:
                assert add_image_to_kanvas(bpy.context, path, location=(0, 0))
                assert add_image_to_kanvas(bpy.context, path, location=(0, 0))
            finally:
                gpu_common.get_prefs = old_prefs
            image_names = sorted(item.name for item in settings.images
                                 if item.item_type == 'IMAGE' and item.image_data)
            assert image_names == ['Kanvas_reference.png', 'Kanvas_reference.png.001'], image_names
            original_index = next(i for i, item in enumerate(settings.images)
                                  if item.name == 'Kanvas_reference.png')
            settings.active_image_index = original_index
            assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
            settings.active_image_index = original_index
            assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
            copy_names = sorted(item.name for item in settings.images if '_copy' in item.name)
            assert copy_names == [
                'Kanvas_reference.png_copy', 'Kanvas_reference.png_copy.001'], copy_names

    print('UNIQUE ITEM NAMES PASS')
finally:
    addon.unregister()
