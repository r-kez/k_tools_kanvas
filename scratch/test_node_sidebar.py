"""Only K-Tools panels poll true on a Kanvas board; every poll comes back on unregister."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.ui import node_sidebar

generic = bpy.types.NODE_PT_active_node_generic
tool = bpy.types.NODE_PT_active_tool
before = generic.__dict__['poll']
assert 'poll' not in tool.__dict__

kanvas = SimpleNamespace(space_data=SimpleNamespace(edit_tree=SimpleNamespace(bl_idname='KanvasNodeTree')))
other = SimpleNamespace(space_data=SimpleNamespace(edit_tree=SimpleNamespace(bl_idname='GeometryNodeTree')))

addon.register()
try:
    assert generic.poll(kanvas) is False
    assert tool.poll(kanvas) is False and tool.poll(other) is True
    assert generic.poll.__func__ is not before.__func__
    mine = [c for c in node_sidebar._sidebar_panels()]
    assert all(not c.__module__.startswith('k_tools_kanvas') for c in mine)
    assert all(c in node_sidebar._patched for c in mine)
    assert not any(c.__name__.startswith('KANVAS') for c in node_sidebar._patched)
    node_sidebar.patch_panels()       # again: nothing is wrapped twice
finally:
    addon.unregister()

assert generic.__dict__['poll'] is before
assert 'poll' not in tool.__dict__ and tool.is_registered
assert not node_sidebar._patched
print('test_node_sidebar: OK')
