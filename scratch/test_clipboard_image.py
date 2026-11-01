"""Clipboard path, bitmap, and Kanvas paste integration checks."""

import struct
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators import ops_image
from k_tools_kanvas.utils.clipboard_image import (
    ClipboardImage, dib_to_bmp, local_image_paths,
)
from k_tools_kanvas.utils.gpu import gpu_common


addon.register()
original_reader = ops_image.read_image_clipboard
original_prefs = gpu_common.get_prefs
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Clipboard paste test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = tree.kanvas_settings
    keymap = bpy.context.window_manager.keyconfigs.addon.keymaps['Node Editor']
    bindings = [item for item in keymap.keymap_items
                if item.idname == 'kanvas.paste_image']
    assert len(bindings) == 1 and bindings[0].type == 'V' and bindings[0].ctrl
    area.ui_type = 'GeometryNodeTree'
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert not bpy.ops.kanvas.paste_image.poll()
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = tree

    dib = struct.pack('<IiiHHIIiiII', 40, 2, 1, 1, 24, 0, 8, 0, 0, 0, 0)
    dib += bytes((0, 0, 255, 0, 255, 0, 0, 0))
    bmp = dib_to_bmp(dib)
    assert bmp[:2] == b'BM'
    assert struct.unpack_from('<I', bmp, 10)[0] == 54
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        source_path = Path(folder) / 'source.png'
        source = bpy.data.images.new('Clipboard test pixels', 16, 8)
        source.pixels.foreach_set([1.0, 0.0, 0.0, 1.0] * (16 * 8))
        source.update()
        source.filepath_raw = str(source_path)
        source.file_format = 'PNG'
        source.save()
        bpy.data.images.remove(source)
        assert local_image_paths(f'"{source_path}"') == (str(source_path),)
        assert not local_image_paths('https://example.com/source.png')
        assert not local_image_paths(str(source_path) + '.missing')
        assert local_image_paths(f'"{source_path}"\n"{source_path}"') == (str(source_path),)

        prefs = SimpleNamespace(auto_copy=True, use_optimization=True,
                                max_image_resolution='8', force_8bit=True)
        gpu_common.get_prefs = lambda: prefs
        ops_image.read_image_clipboard = lambda _text: ClipboardImage(
            pixels=source_path.read_bytes(), extension='.png')
        with bpy.context.temp_override(area=area, region=region,
                                       space_data=area.spaces.active):
            assert bpy.ops.kanvas.paste_image.poll()
            assert bpy.ops.kanvas.paste_image() == {'FINISHED'}
        pasted = settings.images[-1]
        assert pasted.image_data.packed_file is not None
        assert pasted.image_data.filepath == ''
        assert pasted.image_data.pixels[0] > 0.9
        assert pasted.image_data.get('kanvas_clipboard') is True
        assert tuple(pasted.image_data.size) == (8, 4)
        assert pasted.image_data.get('kanvas_source_path') is None
        assert settings.active_image_index == len(settings.images) - 1

        prefs.auto_copy = False
        ops_image.read_image_clipboard = lambda _text: ClipboardImage(
            paths=(str(source_path),))
        with bpy.context.temp_override(area=area, region=region,
                                       space_data=area.spaces.active):
            assert bpy.ops.kanvas.paste_image() == {'FINISHED'}
        imported = settings.images[-1]
        assert imported.image_data.packed_file is not None
        assert imported.image_data.get('kanvas_source_path') == str(source_path)

        ops_image.read_image_clipboard = lambda _text: ClipboardImage(
            pixels=bmp, extension='.bmp')
        with bpy.context.temp_override(area=area, region=region,
                                       space_data=area.spaces.active):
            assert bpy.ops.kanvas.paste_image() == {'FINISHED'}
        dib_item = settings.images[-1]
        assert dib_item.image_data.packed_file is not None
        assert tuple(dib_item.image_data.size) == (2, 1)

        dib_item.mask_editing = True
        with bpy.context.temp_override(area=area, region=region,
                                       space_data=area.spaces.active):
            assert not bpy.ops.kanvas.paste_image.poll()
        dib_item.mask_editing = False

        blend_path = Path(folder) / 'clipboard.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        loaded = bpy.data.node_groups['Clipboard paste test'].kanvas_settings.images[0]
        assert loaded.image_data.packed_file is not None
        assert tuple(loaded.image_data.size) == (8, 4)
        assert loaded.image_data.filepath == ''
        assert loaded.image_data.pixels[0] > 0.9

    print('CLIPBOARD IMAGE PASS')
finally:
    ops_image.read_image_clipboard = original_reader
    gpu_common.get_prefs = original_prefs
    addon.unregister()
