"""Synthetic 1.10 note record based on the documented legacy layout."""

from pathlib import Path
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.pureref import read_pureref


def pack(fmt, *values):
    return struct.pack(fmt, *values)


def qt_string(value):
    encoded = value.encode('utf-16-be')
    return pack('>I', len(encoded)) + encoded


raw = bytearray(224)
raw[:12] = qt_string('1.10')
raw[12:16] = pack('>HH', 1, 0)
start = len(raw)
raw.extend(pack('>Q', 0))
raw.extend(pack('>I', 32))
raw.extend('GraphicsTextItem'.encode('utf-16-be'))
raw.extend(qt_string('<p>Hello</p><p>World</p>'))
raw.extend(pack('>6d', 1, 0, 0, 0, 1, 0))
raw.extend(pack('>3d', 120, -35, 1))
raw.extend(pack('>Id', 7, 2.0))
raw.extend(pack('>BH3H', 1, 65535, 65535, 32768, 0))
raw.extend(pack('>H', 0))
raw.extend(pack('>BH3H', 1, 32768, 0, 0, 0))
raw.extend(pack('>HI', 0, 0))
raw[start:start + 8] = pack('>Q', len(raw))
raw.extend(qt_string(''))

with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
    path = Path(folder) / 'note.pur'
    path.write_bytes(raw)
    scene = read_pureref(path)
    assert scene.version == '1.10'
    assert not scene.images and len(scene.texts) == 1
    assert scene.texts[0].center == (120, 35)
    assert scene.texts[0].content == '<p>Hello</p><p>World</p>'
    try:
        import bpy
    except ImportError:
        pass
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import k_tools_kanvas as addon
        addon.register()
        try:
            area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
            area.type = 'NODE_EDITOR'
            area.ui_type = 'KanvasNodeTree'
            area.spaces.active.node_tree = bpy.data.node_groups.new('Legacy Note Test', 'KanvasNodeTree')
            region = next(region for region in area.regions if region.type == 'WINDOW')
            with bpy.context.temp_override(area=area, region=region,
                                           space_data=area.spaces.active):
                assert bpy.ops.kanvas.import_pureref(filepath=str(path)) == {'FINISHED'}
            item = area.spaces.active.edit_tree.kanvas_settings.images[0]
            assert item.item_type == 'TEXT' and item.text_body == 'Hello\nWorld'
            assert tuple(item.location) == (120, 35)
        finally:
            addon.unregister()
print('LEGACY TEXT PASS')
