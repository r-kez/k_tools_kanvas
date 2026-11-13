"""Check Kanvas Add-menu entries and the opt-in Debug panel in Blender."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas import preferences, ui
from k_tools_kanvas.operators import ops_menu


class RecordingLayout:
    def __init__(self):
        self.operators = []
        self.menus = []
        self.properties = []
        self.operator_context = None

    def row(self, **kwargs):
        return self

    def menu(self, identifier, **kwargs):
        self.menus.append(identifier)

    def separator(self):
        pass

    def label(self, **kwargs):
        pass

    def operator(self, identifier, **kwargs):
        self.operators.append(identifier)
        return SimpleNamespace()

    def prop(self, _owner, name, **kwargs):
        self.properties.append(name)


addon.register()
try:
    tree = bpy.data.node_groups.new("Kanvas UI Test", 'KanvasNodeTree')
    prefs = SimpleNamespace(show_debug_panel=False)
    addon_entry = SimpleNamespace(preferences=prefs)
    context = SimpleNamespace(
        space_data=SimpleNamespace(type='NODE_EDITOR', edit_tree=tree),
        preferences=SimpleNamespace(addons={addon.__name__: addon_entry}),
        tool_settings=bpy.context.scene.tool_settings,
    )

    assert preferences.KanvasPreferences.bl_rna.properties['show_debug_panel'].default is False
    assert not ui.KANVAS_PT_DebugPanel.poll(context)
    prefs.show_debug_panel = True
    assert ui.KANVAS_PT_DebugPanel.poll(context)

    menu = SimpleNamespace(layout=RecordingLayout())
    ops_menu.draw_kanvas_add_menu(menu, context)
    assert menu.layout.operators == [
        'kanvas.add_image_browser',
        'kanvas.add_multiple_images',
        'kanvas.import_pureref',
        'kanvas.create_text',
        'kanvas.create_text',
        'kanvas.create_text',
        'kanvas.start_pencil',
        'kanvas.create_arrow',
        'kanvas.create_frame',
    ], menu.layout.operators
    assert menu.layout.operator_context == 'INVOKE_DEFAULT'

    empty_context = SimpleNamespace(layout=RecordingLayout())
    ops_menu.KANVAS_MT_ContextMenu.draw(empty_context, context)
    assert empty_context.layout.operators.count('kanvas.create_text') == 3

    selected = tree.kanvas_settings.images.add()
    selected.item_type = 'TEXT'
    selected.is_selected = True
    tree.kanvas_settings.active_image_index = 0
    selected_context = SimpleNamespace(layout=RecordingLayout())
    ops_menu.KANVAS_MT_ContextMenu.draw(selected_context, context)
    assert 'KANVAS_MT_add_content' in selected_context.layout.menus
    assert 'kanvas.create_frame' in selected_context.layout.operators
    assert ui.KANVAS_PT_ItemsPanel.poll(context)
    assert ui.KANVAS_PT_SelectionPanel.poll(context)
    assert not ui.KANVAS_PT_AlignPanel.poll(context)
    gizmo_header = SimpleNamespace(layout=RecordingLayout())
    ui.KANVAS_PT_GizmoPanel.draw_header(gizmo_header, context)
    assert gizmo_header.layout.properties == ['show_gizmos']
    snap_header = SimpleNamespace(layout=RecordingLayout())
    ui.KANVAS_PT_SnapPanel.draw_header(snap_header, context)
    assert snap_header.layout.properties == ['use_snap_node']

    align = SimpleNamespace(layout=RecordingLayout())
    ops_menu.KANVAS_MT_AlignMenu.draw(align, context)
    assert align.layout.operators == (
        ['kanvas.align_items'] * 6 + ['kanvas.distribute_items'] * 2)
    header = SimpleNamespace(layout=RecordingLayout())
    ops_menu.draw_kanvas_align_header(header, context)
    assert header.layout.menus == ['KANVAS_MT_align_menu']

    context.space_data.edit_tree = None
    other_menu = SimpleNamespace(layout=RecordingLayout())
    ops_menu.draw_kanvas_add_menu(other_menu, context)
    assert not other_menu.layout.operators
    print('ADD MENU AND DEBUG PANEL PASS')
finally:
    addon.unregister()
