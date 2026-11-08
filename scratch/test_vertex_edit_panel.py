"""Edit Vertices: mode badge, shared Shortcuts panel, panel toggle and Esc to exit."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu import gpu_shape, gpu_shortcuts

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Vertex panel', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(0, 0)) == {'FINISHED'}
        shape = settings.images[0]

        # Not editing: nothing to show and the panel cannot be hit.
        shape.is_selected = True
        settings.active_image_index = 0
        shape.shape_edit_vertices = False
        assert gpu_shape.vertex_edit_shape(settings) is None

        # Editing needs exactly one selected, unlocked, visible shape.
        shape.shape_edit_vertices = True
        assert gpu_shape.vertex_edit_shape(settings).item_id == shape.item_id
        assert 'EDIT VERTICES' in gpu_shape.vertex_edit_title(shape) and '4 vertices' in gpu_shape.vertex_edit_title(shape)
        shape.is_locked = True
        assert gpu_shape.vertex_edit_shape(settings) is None
        shape.is_locked = False
        shape_id = shape.item_id
        assert bpy.ops.kanvas.create_text(location=(900, 0)) == {'FINISHED'}
        # Adding an item can move the collection in memory: look the shape up again.
        shape = next(item for item in settings.images if item.item_id == shape_id)
        for item in settings.images:
            item.is_selected = True
        assert gpu_shape.vertex_edit_shape(settings) is None, 'two selected items: not editing'
        for item in settings.images:
            item.is_selected = item.item_id == shape.item_id
        settings.active_image_index = 0
        assert gpu_shape.vertex_edit_shape(settings).item_id == shape.item_id

        # Every shortcut row is a (key, description) pair with text in both.
        assert all(len(row) == 2 and all(row) for row in gpu_shape.VERTEX_EDIT_ROWS)
        keys = [key for key, _ in gpu_shape.VERTEX_EDIT_ROWS]
        assert 'E / Esc' in keys and 'Ctrl+Click vertex' in keys

        # The overlay uses the shared badge and panel; stand-ins record the calls.
        calls = []
        original = (gpu_shortcuts.draw_mode_badge, gpu_shortcuts.draw_shortcut_panel)
        gpu_shortcuts.draw_mode_badge = lambda reg, title, *a, **k: calls.append(('badge', title))
        gpu_shortcuts.draw_shortcut_panel = lambda ar, reg, rows, *a: (
            calls.append(('panel', tuple(rows))) or (10, 10, 110, 36))
        try:
            gpu_shape.draw_vertex_edit_overlay(settings, area, region)
            assert [kind for kind, _ in calls] == ['badge', 'panel'], calls
            assert calls[1][1] == gpu_shape.VERTEX_EDIT_ROWS

            # Clicking the panel header collapses it; clicks elsewhere do not.
            assert gpu_shape.hit_vertex_panel_toggle(settings, 50, 20)
            assert not gpu_shape.hit_vertex_panel_toggle(settings, 500, 500)
            before = gpu_shortcuts.PANEL_STATE['collapsed']
            gpu_shortcuts.toggle_collapsed()
            assert gpu_shortcuts.PANEL_STATE['collapsed'] is (not before)
            gpu_shortcuts.toggle_collapsed()

            # Leaving the mode clears the panel, so a stale rectangle cannot eat clicks.
            shape.shape_edit_vertices = False
            calls.clear()
            gpu_shape.draw_vertex_edit_overlay(settings, area, region)
            assert calls == [] and not gpu_shape.hit_vertex_panel_toggle(settings, 50, 20)
        finally:
            gpu_shortcuts.draw_mode_badge, gpu_shortcuts.draw_shortcut_panel = original

        # The badge never overlaps the Edit | Move switch: it sits just below it, or at the
        # very top when the switch is hidden.
        from k_tools_kanvas.utils.gpu.gpu_mode_switch import mode_switch_layout
        fake_area = SimpleNamespace(regions=[])
        fake_region = SimpleNamespace(x=0, y=0, width=1000, height=600)
        layout = mode_switch_layout(fake_area, fake_region)
        assert layout is not None
        bx, by = gpu_shortcuts.badge_rect(fake_area, fake_region, 300.0, 31.0)
        assert by + 31.0 <= layout['bounds'][1], 'badge is below the switch'
        assert abs((bx + 150.0) - 500.0) < 1e-6, 'centered like the switch'
        from k_tools_kanvas.utils.gpu import gpu_common
        real_get_prefs = gpu_common.get_prefs
        gpu_common.get_prefs = lambda: SimpleNamespace(show_mode_overlay=False)
        try:
            _bx, top_y = gpu_shortcuts.badge_rect(fake_area, fake_region, 300.0, 31.0)
        finally:
            gpu_common.get_prefs = real_get_prefs
        assert top_y > by, 'with the switch hidden the badge moves up'
        narrow = gpu_shortcuts.badge_rect(fake_area, SimpleNamespace(x=0, y=0, width=200, height=600), 300.0, 31.0)
        assert narrow[0] >= 4.0, 'a wide badge stays inside a narrow canvas'

        # The Mask panel shares the same collapsed state.
        from k_tools_kanvas.operators import ops_mask
        assert ops_mask._shortcut_panel is gpu_shortcuts.PANEL_STATE

        # Esc leaves Edit Vertices; the panel header click is consumed, not a canvas click.
        import k_tools_kanvas.operators.ops_modal as modal_module
        from k_tools_kanvas.operators.ops_modal import KANVAS_OT_Interact, KanvasInteractionHelpers

        class Dummy(KanvasInteractionHelpers):
            def __init__(self, action):
                self.action = action

            def _begin_gesture(self, context):
                return {'RUNNING_MODAL'}

        def press(action, x, y, value='PRESS'):
            event = SimpleNamespace(type='LEFTMOUSE' if action == 'CLICK' else 'ESC', value=value,
                                    shift=False, alt=False, ctrl=False, oskey=False,
                                    mouse_x=region.x + x, mouse_y=region.y + y,
                                    mouse_region_x=x, mouse_region_y=y)
            return KANVAS_OT_Interact.invoke(Dummy(action), bpy.context, event)

        original_prefs = modal_module.get_prefs
        modal_module.get_prefs = lambda: SimpleNamespace(box_select_alt_drag=True, box_select_on_drag=True)
        try:
            shape.shape_edit_vertices = True
            gpu_shape._vertex_panel['toggle'] = (10, 10, 110, 36)
            before = gpu_shortcuts.PANEL_STATE['collapsed']
            assert press('CLICK', 50, 20) == {'CANCELLED'}
            assert gpu_shortcuts.PANEL_STATE['collapsed'] is (not before), 'header click toggles the panel'
            gpu_shortcuts.PANEL_STATE['collapsed'] = before
            assert shape.shape_edit_vertices, 'the click did not leave the mode'

            assert press('CANCEL_BOX', 50, 50) == {'CANCELLED'}
            assert not shape.shape_edit_vertices, 'Esc leaves Edit Vertices'
            assert press('CANCEL_BOX', 50, 50) == {'PASS_THROUGH'}, 'Esc passes through otherwise'
        finally:
            modal_module.get_prefs = original_prefs

    print('VERTEX EDIT PANEL PASS')
finally:
    addon.unregister()
