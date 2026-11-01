"""Reload changed source pixels without moving or restyling the reference."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_image import add_image_to_kanvas, image_origin
from k_tools_kanvas.utils.gpu import gpu_common


addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Reload source', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    old_prefs = gpu_common.get_prefs
    import_prefs = SimpleNamespace(
        auto_copy=False, use_optimization=False, force_8bit=False,
        max_image_resolution='0', assets_folder='//assets/kanvas')
    gpu_common.get_prefs = lambda: import_prefs
    try:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            path = str(Path(temp_dir) / 'changing.png')

            def write_source(name, width, height):
                image = bpy.data.images.new(name, width, height)
                image.filepath_raw = path
                image.file_format = 'PNG'
                image.save()
                bpy.data.images.remove(image)

            write_source('First pixels', 8, 8)
            with bpy.context.temp_override(area=area, region=region,
                                           space_data=area.spaces.active):
                item = add_image_to_kanvas(bpy.context, path, location=(100, -80))
                item_id = item.item_id
                item.name = 'Custom reference'
                item.scale_xy = (2.0, 0.5)
                item.rotation = 25
                item.opacity = 0.4
                assert bpy.ops.kanvas.clear_image_gpu_cache() == {'FINISHED'}

                write_source('Changed pixels', 16, 4)
                assert bpy.ops.kanvas.refresh_image() == {'FINISHED'}
                item = next(entry for entry in settings.images if entry.item_id == item_id)
                assert item.name == 'Custom reference'
                assert tuple(item.location) == (100, -80)
                assert tuple(item.image_data.size) == (16, 4)
                assert tuple(item.scale_xy) == (1.0, 1.0)
                assert item.rotation == 25 and abs(item.opacity - 0.4) < 0.001
                assert len(settings.images) == 1
                assert bpy.ops.kanvas.clear_image_gpu_cache() == {'FINISHED'}

                bpy.ops.wm.save_as_mainfile(filepath=str(Path(temp_dir) / 'source-test.blend'))
                import_prefs.auto_copy = True
                copy_item = add_image_to_kanvas(bpy.context, path, location=(250, -160))
                copy_id = copy_item.item_id
                assert copy_item.image_data.filepath.lower().endswith('.webp')
                write_source('Changed again', 12, 6)
                assert bpy.ops.kanvas.refresh_image() == {'FINISHED'}
                copy_item = next(entry for entry in settings.images if entry.item_id == copy_id)
                assert tuple(copy_item.image_data.size) == (12, 6)
                assert copy_item.image_data.filepath.lower().endswith('.webp')
                assert tuple(copy_item.location) == (250, -160)

                replacement_path = str(Path(temp_dir) / 'replacement.png')
                replacement = bpy.data.images.new('Replacement pixels', 22, 11)
                replacement.filepath_raw = replacement_path
                replacement.file_format = 'PNG'
                replacement.save()
                bpy.data.images.remove(replacement)
                old_display = (copy_item.image_data.size[0] * copy_item.scale_xy[0],
                               copy_item.image_data.size[1] * copy_item.scale_xy[1])
                assert bpy.ops.kanvas.replace_image(filepath=replacement_path) == {'FINISHED'}
                copy_item = next(entry for entry in settings.images if entry.item_id == copy_id)
                assert image_origin(copy_item.image_data) == ('FILE', replacement_path)
                assert tuple(copy_item.image_data.size) == (22, 11)
                assert tuple(copy_item.location) == (250, -160)
                new_display = (copy_item.image_data.size[0] * copy_item.scale_xy[0],
                               copy_item.image_data.size[1] * copy_item.scale_xy[1])
                assert all(abs(a - b) < 0.001 for a, b in zip(old_display, new_display))
    finally:
        gpu_common.get_prefs = old_prefs
    print('RELOAD IMAGE SOURCE PASS')
finally:
    addon.unregister()
