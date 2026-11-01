"""Check that the PureRef file drop is offered only inside a Kanvas tree."""

from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_pureref import KANVAS_FH_PureRef


addon.register()
try:
    assert hasattr(bpy.types, 'KANVAS_FH_PureRef')
    assert KANVAS_FH_PureRef.bl_import_operator == 'kanvas.import_pureref'
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    region = next(region for region in area.regions if region.type == 'WINDOW')
    space = area.spaces.active
    with bpy.context.temp_override(area=area, region=region, space_data=space):
        assert not KANVAS_FH_PureRef.poll_drop(bpy.context)
        area.ui_type = 'KanvasNodeTree'
        space.node_tree = bpy.data.node_groups.new('PureRef Drop Test', 'KanvasNodeTree')
        assert KANVAS_FH_PureRef.poll_drop(bpy.context)
    print('PUREREF DROP HANDLER PASS')
finally:
    addon.unregister()
