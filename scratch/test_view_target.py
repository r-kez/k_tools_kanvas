"""Choosing which 3D View shows an overlay or live reference (per entry), and turning a
reference image into an overlay and back.

    blender -b --factory-startup -P scratch/test_view_target.py
"""
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


from k_tools_kanvas.utils import view_target as vt
from k_tools_kanvas.ui import view3d_references as ui

scene = bpy.context.scene

# --- Per entry view -------------------------------------------------------------------
entry = scene.kanvas_references.add()
entry.kind = 'OVERLAY'
check(entry.limit_view is False, 'default is every view')
check(vt.shows_here(entry, None), 'every view by default')
entry.limit_view = True
entry.view_id = 5
check(not vt.shows_here(entry, None), 'no area shows nothing when limited')
check(not vt.target_exists(entry), 'missing target is reported')
areas = vt.view_areas()
if areas:
    entry.view_id = 0
    check(vt.shows_here(entry, areas[0][1]), 'target view shows')
for cls in (ui.KANVAS_PT_References3D, ui.KANVAS_PT_Reference3DSettings):
    check(cls.bl_category == 'K-Tools', f'{cls.__name__} category')
check(not hasattr(bpy.types.Scene, 'kanvas_view_choose'), 'no scene-wide choice left')
scene.kanvas_references.clear()

# --- Reference image <-> overlay ------------------------------------------------------
from k_tools_kanvas.operators import ops_reference_3d as ops
from k_tools_kanvas.utils import reference_3d as ref

tree = bpy.data.node_groups.new('Board', 'KanvasNodeTree')
settings = tree.kanvas_settings
image = bpy.data.images.new('pic', 8, 8)
item = settings.images.add()
item.item_id, item.image_data, item.name = 'abc', image, 'pic'
check(ref.board_item(tree, 'abc') is not None, 'board item found')
holder, placeholder = ops._live_placeholder(tree, ops._Options(
    item_id='abc', crop_to_mask=True, keep_stretch=False))
obj = ref.create_empty(bpy.context, placeholder, 'pic', 'FRONT', (1.0, 2.0, 3.0), 2.0,
                       'DEFAULT', 1.0, False, True)
entry = scene.kanvas_references.add()
entry.kind, entry.object, entry.board, entry.item_id = 'EMPTY', obj, tree, 'abc'
entry.live, entry.name = True, 'pic'
scene.kanvas_reference_index = 0

check(bpy.ops.kanvas.convert_3d_reference.poll(), 'convert poll')
bpy.ops.kanvas.convert_3d_reference()
entry = scene.kanvas_references[0]
check(entry.kind == 'OVERLAY' and entry.object is None, 'became an overlay')
check('pic' not in [o.name for o in bpy.data.objects], 'empty removed')
bpy.ops.kanvas.convert_3d_reference()
entry = scene.kanvas_references[0]
check(entry.kind == 'EMPTY' and entry.object is not None and entry.live, 'back to a reference')
check(tuple(round(v, 4) for v in entry.object.matrix_world.translation) == (1.0, 2.0, 3.0),
      'back where it was')
check(len(scene.kanvas_references) == 1, 'still one entry')

addon.unregister()
print('VIEWTARGET RESULT', 'FAIL ' + '; '.join(errors) if errors else 'OK')
