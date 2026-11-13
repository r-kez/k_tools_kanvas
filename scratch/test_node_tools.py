"""The Kanvas toolbar: a board lists only kanvas.* tools, other trees none of them."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.ui import node_tools

helper = bpy.types.NODE_PT_tools_active
before = helper.__dict__['tools_from_context']


def ids(items):
    out = []
    for item in items:
        out.append(None if item is None else
                   tuple(t.idname for t in item if t) if type(item) is tuple else item.idname)
    return out


def context(idname):
    return SimpleNamespace(
        space_data=SimpleNamespace(edit_tree=SimpleNamespace(bl_idname=idname), tree_type=idname),
        workspace=None)


addon.register()
try:
    board = ids(helper.tools_from_context(context('KanvasNodeTree')))
    flat = [i for i in board if i is not None]
    assert flat == ['kanvas.edit', 'kanvas.pencil', 'kanvas.eraser'], board
    assert board == ['kanvas.edit', None, 'kanvas.pencil', None, 'kanvas.eraser'], board

    other = ids(helper.tools_from_context(context('GeometryNodeTree')))
    assert other and not any(
        i and (i if isinstance(i, str) else i[0]).startswith('kanvas.') for i in other), other
    assert not hasattr(bpy.types, 'KANVAS_OT_arm_shape')
finally:
    addon.unregister()

assert helper.__dict__['tools_from_context'] is before
assert not hasattr(helper, node_tools._ORIGINAL)
after = [i for i in ids(helper.tools_from_context(context('GeometryNodeTree'))) if i]
assert not any((i if isinstance(i, str) else i[0]).startswith('kanvas.') for i in after)
print('test_node_tools: OK')
