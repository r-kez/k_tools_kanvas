"""Different source pixels must never reuse an older auto-copied WebP."""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_image import _find_or_save_webp, add_image_to_kanvas
from k_tools_kanvas.utils.gpu import gpu_common


addon.register()
try:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        root = Path(folder)
        assets = root / 'assets'
        first = root / 'first' / 'reference.png'
        second = root / 'second' / 'reference.png'
        third = root / 'third' / 'reference.png'
        first.parent.mkdir()
        second.parent.mkdir()
        third.parent.mkdir()

        def write_png(path, color):
            image = bpy.data.images.new('Source for WebP identity', 16, 16)
            image.pixels.foreach_set(list(color) * (16 * 16))
            image.filepath_raw = str(path)
            image.file_format = 'PNG'
            image.save()
            bpy.data.images.remove(image)

        def import_webp(path, size=(16, 16), convert_srgb=False):
            image = bpy.data.images.load(str(path), check_existing=False)
            try:
                return Path(_find_or_save_webp(image, str(path), str(assets),
                                               *size, convert_srgb=convert_srgb))
            finally:
                bpy.data.images.remove(image)

        write_png(first, (1.0, 0.0, 0.0, 1.0))
        write_png(second, (0.0, 0.0, 1.0, 1.0))
        third.write_bytes(first.read_bytes())
        legacy = assets / 'reference.webp'
        assets.mkdir()
        legacy.write_bytes(b'legacy file must remain untouched')

        red = import_webp(first)
        red_bytes = red.read_bytes()
        blue = import_webp(second)
        assert red != blue and red.exists() and blue.exists()
        same_pixels_other_origin = import_webp(third)
        assert same_pixels_other_origin != red
        assert red.read_bytes() == red_bytes
        assert legacy.read_bytes() == b'legacy file must remain untouched'
        assert import_webp(first) == red
        assert import_webp(first, size=(8, 8)) != red
        assert import_webp(first, convert_srgb=True) != red

        write_png(first, (0.0, 1.0, 0.0, 1.0))
        green = import_webp(first)
        assert green not in {red, blue}
        assert red.read_bytes() == red_bytes
        third.write_bytes(first.read_bytes())
        same_green_other_origin = import_webp(third)
        assert same_green_other_origin != green

        bpy.ops.wm.save_as_mainfile(filepath=str(root / 'identity.blend'))
        original_get_prefs = gpu_common.get_prefs
        try:
            gpu_common.get_prefs = lambda: SimpleNamespace(
                assets_folder=str(assets), auto_copy=True, use_optimization=True,
                max_image_resolution='0', force_8bit=False)
            area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
            area.type = 'NODE_EDITOR'
            area.ui_type = 'KanvasNodeTree'
            area.spaces.active.node_tree = bpy.data.node_groups.new(
                'WebP import identity', 'KanvasNodeTree')
            region = next(region for region in area.regions if region.type == 'WINDOW')
            with bpy.context.temp_override(area=area, region=region,
                                           space_data=area.spaces.active):
                item_green = add_image_to_kanvas(bpy.context, str(first), (0, 0))
                item_blue = add_image_to_kanvas(bpy.context, str(second), (100, 0))
                item_same_pixels = add_image_to_kanvas(bpy.context, str(third), (150, 0))
                assert item_green and item_blue and item_same_pixels
                assert Path(bpy.path.abspath(item_green.image_data.filepath)) == green
                assert Path(bpy.path.abspath(item_blue.image_data.filepath)) == blue
                assert item_green.image_data != item_same_pixels.image_data
                assert item_green.image_data['kanvas_source_path'] == str(first)
                assert item_same_pixels.image_data['kanvas_source_path'] == str(third)
                write_png(first, (1.0, 1.0, 0.0, 1.0))
                item_yellow = add_image_to_kanvas(bpy.context, str(first), (200, 0))
                assert item_yellow
                assert item_yellow.image_data != item_green.image_data
                assert Path(bpy.path.abspath(item_green.image_data.filepath)) == green
        finally:
            gpu_common.get_prefs = original_get_prefs
    print('WEBP_IDENTITY_OK')
finally:
    addon.unregister()
