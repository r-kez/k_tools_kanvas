"""Smoke test for Blender-style keyboard transforms in Kanvas."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.operators import ops_modal


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Keyboard transforms', 'KanvasNodeTree')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = area.spaces.active.edit_tree.kanvas_settings
    image = settings.images.add()
    image.item_type = 'IMAGE'
    image.image_data = bpy.data.images.new('Shortcut test', 100, 100)
    image.is_selected = True
    settings.active_image_index = 0

    original_prefs = ops_modal.get_prefs
    ops_modal.get_prefs = lambda: SimpleNamespace()

    class Gesture(ops_modal.KanvasInteractionHelpers):
        invoke = ops_modal.KANVAS_OT_Interact.invoke
        modal = ops_modal.KANVAS_OT_Interact.modal

        def _begin_gesture(self, context):
            return {'RUNNING_MODAL'}

        def _end(self, context, result):
            return result

    try:
        with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
            rx, ry = region.width // 2, region.height // 2
            vx, vy = region.view2d.region_to_view(rx, ry)
            image.location = (vx, vy)

            def event(kind, value='PRESS', x=rx, y=ry):
                return SimpleNamespace(type=kind, value=value, mouse_x=region.x + x,
                                       mouse_y=region.y + y, mouse_region_x=x,
                                       mouse_region_y=y, shift=False, ctrl=False, alt=False)

            for action, key, xdelta, attr in (('MOVE', 'G', 35, 'location'),
                                              ('ROTATE', 'R', 35, 'rotation'),
                                              ('SCALE', 'S', 35, 'scale_master')):
                op = Gesture()
                op.action = action
                before = tuple(image.location) if attr == 'location' else getattr(image, attr)
                assert op.invoke(bpy.context, event(key)) == {'RUNNING_MODAL'}, action
                assert op.modal(bpy.context, event('MOUSEMOVE', x=rx + xdelta)) == {'RUNNING_MODAL'}
                after = tuple(image.location) if attr == 'location' else getattr(image, attr)
                assert after != before, (action, before, after)
                assert op.modal(bpy.context, event('RET')) == {'FINISHED'}, action
                image.location = (vx, vy)
                image.rotation = 0
                image.scale_master = 1
    finally:
        ops_modal.get_prefs = original_prefs
    print('KEYBOARD SHORTCUTS PASS')
finally:
    addon.unregister()
