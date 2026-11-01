"""No-op Kanvas input must not become an Undo step."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators import ops_modal


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Undo noise', 'KanvasNodeTree')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = area.spaces.active.edit_tree.kanvas_settings
    card = settings.images.add()
    card.item_id = 'undo-card'
    card.item_type = 'TEXT'
    card.is_selected = True
    settings.active_image_index = 0

    class Gesture(ops_modal.KanvasInteractionHelpers):
        invoke = ops_modal.KANVAS_OT_Interact.invoke
        modal = ops_modal.KANVAS_OT_Interact.modal
        _end = ops_modal.KANVAS_OT_Interact._end

        def _begin_gesture(self, context):
            return {'RUNNING_MODAL'}

        def report(self, *args):
            pass

    original_get_prefs = ops_modal.get_prefs
    ops_modal.get_prefs = lambda: SimpleNamespace(
        show_text_edit_button=False, box_select_on_drag=True,
        box_select_alt_drag=False, wheel_opacity_mod='ALT',
        wheel_scale_mod='CTRL', wheel_layer_mod='SHIFT', key_shear_mod='ALT')
    try:
        with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
            cx, cy = region.view2d.view_to_region(*card.location, clip=False)

            def event(kind, value='PRESS', x=cx, y=cy):
                return SimpleNamespace(type=kind, value=value,
                                       mouse_x=region.x + x, mouse_y=region.y + y,
                                       mouse_region_x=x, mouse_region_y=y,
                                       shift=False, ctrl=False, alt=False)

            for action, kind in [('MODIFIER', 'LEFT_SHIFT'),
                                 ('F_PRESS', 'F'), ('F_RELEASE', 'F')]:
                op = Gesture()
                op.action = action
                assert 'FINISHED' not in op.invoke(bpy.context, event(kind)), action

            click = Gesture()
            click.action = 'CLICK'
            assert click.invoke(bpy.context, event('LEFTMOUSE')) == {'RUNNING_MODAL'}
            assert click.modal(bpy.context, event('LEFTMOUSE', 'RELEASE')) == {'CANCELLED'}

            moved = Gesture()
            moved.action = 'CLICK'
            assert moved.invoke(bpy.context, event('LEFTMOUSE')) == {'RUNNING_MODAL'}
            assert moved.modal(bpy.context, event('MOUSEMOVE', x=cx + 30)) == {'RUNNING_MODAL'}
            assert moved.modal(bpy.context, event('LEFTMOUSE', 'RELEASE', x=cx + 30)) == {'FINISHED'}

            duplicate = Gesture()
            duplicate.action = 'DUPLICATE'
            assert duplicate.invoke(bpy.context, event('D')) == {'RUNNING_MODAL'}
            assert duplicate.modal(bpy.context, event('LEFTMOUSE', 'RELEASE')) == {'FINISHED'}
            assert len(settings.images) == 2
            for item in settings.images:
                item.is_selected = True
            assert bpy.ops.kanvas.align_items(mode='CENTER_Y') == {'CANCELLED'}
            assert bpy.ops.kanvas.reset_transform(transform_type='ROTATION') == {'CANCELLED'}
        print('UNDO_NOISE_OK')
    finally:
        ops_modal.get_prefs = original_get_prefs
finally:
    addon.unregister()
