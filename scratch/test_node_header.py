"""The Kanvas header replaces Blender's draw function and puts it back."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.ui import node_header

original = bpy.types.NODE_HT_header._dyn_ui_initialize()[0]
addon.register()
try:
    funcs = bpy.types.NODE_HT_header._dyn_ui_initialize()
    assert getattr(funcs[0], node_header._MARK) is original
    assert len(funcs) >= 3          # Blender's header plus what Kanvas appends

    node_header.install()           # a second install must not wrap twice
    assert getattr(bpy.types.NODE_HT_header._dyn_ui_initialize()[0],
                   node_header._MARK) is original

    tree = SimpleNamespace(bl_idname='KanvasNodeTree')
    other = SimpleNamespace(bl_idname='GeometryNodeTree')
    assert node_header.is_kanvas_header(SimpleNamespace(space_data=SimpleNamespace(edit_tree=tree)))
    assert not node_header.is_kanvas_header(SimpleNamespace(space_data=SimpleNamespace(edit_tree=other)))
    assert not node_header.is_kanvas_header(SimpleNamespace(space_data=None))
finally:
    addon.unregister()

assert bpy.types.NODE_HT_header._dyn_ui_initialize()[0] is original
print('test_node_header: OK')
