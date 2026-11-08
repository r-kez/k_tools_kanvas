"""A PureRef scene comes in as one group named after the file (Group on by default),
so it moves as one wherever it lands; Group off leaves the items loose."""

from pathlib import Path
import struct
import sys
import tempfile

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon


def pack(fmt, *values):
    return struct.pack(fmt, *values)


def qt_string(value):
    encoded = value.encode('utf-16-be')
    return pack('>I', len(encoded)) + encoded


def note(text, x, y):
    """One legacy 1.10 text record (same layout as test_pureref_legacy_text)."""
    record = bytearray(pack('>Q', 0))
    record.extend(pack('>I', 32))
    record.extend('GraphicsTextItem'.encode('utf-16-be'))
    record.extend(qt_string(text))
    record.extend(pack('>6d', 1, 0, 0, 0, 1, 0))
    record.extend(pack('>3d', x, y, 1))
    record.extend(pack('>Id', 7, 2.0))
    record.extend(pack('>BH3H', 1, 65535, 65535, 32768, 0))
    record.extend(pack('>H', 0))
    record.extend(pack('>BH3H', 1, 32768, 0, 0, 0))
    record.extend(pack('>HI', 0, 0))
    return record


def scene_bytes():
    raw = bytearray(224)
    raw[:12] = qt_string('1.10')
    raw[12:16] = pack('>HH', 2, 0)
    for text, x, y in (('<p>First</p>', 0, 0), ('<p>Second</p>', 400, -100)):
        start = len(raw)
        raw.extend(note(text, x, y))
        raw[start:start + 8] = pack('>Q', len(raw))
    raw.extend(qt_string(''))
    return bytes(raw)


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    region = next(region for region in area.regions if region.type == 'WINDOW')
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        path = Path(folder) / 'Mood board.pur'
        path.write_bytes(scene_bytes())
        for grouped in (True, False):
            tree = bpy.data.node_groups.new(f'PureRef group {grouped}', 'KanvasNodeTree')
            area.spaces.active.node_tree = tree
            with bpy.context.temp_override(area=area, region=region,
                                           space_data=area.spaces.active):
                assert bpy.ops.kanvas.import_pureref(filepath=str(path),
                                                     group=grouped) == {'FINISHED'}
            settings = tree.kanvas_settings
            notes = [item for item in settings.images if item.item_type == 'TEXT']
            groups = [item for item in settings.images
                      if item.item_type == 'FRAME' and item.frame_is_group]
            assert len(notes) == 2, [item.name for item in settings.images]
            if grouped:
                assert len(groups) == 1 and groups[0].name == 'Mood board', \
                    [item.name for item in groups]
                assert all(item.parent_frame == groups[0].frame_node_name for item in notes)
                assert groups[0].is_selected, 'the new group is selected'
            else:
                assert not groups and all(not item.parent_frame for item in notes)
    print('test_pureref_group: OK')
finally:
    addon.unregister()
