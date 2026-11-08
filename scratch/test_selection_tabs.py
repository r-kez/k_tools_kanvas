"""The Selection panel in tabs: every tab of images, shapes and text cards draws, the
tab icons exist, items with few options draw without tabs, entering a mode opens its
tab, and a narrow sidebar shows only the tab icons."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    calls = []

    class Layout:
        enabled = True
        use_property_split = False
        operator_context = ''
        alignment = 'EXPAND'
        scale_x = scale_y = 1.0
        ui_units_x = 0

        def __getattr__(self, name):
            def call(*args, **kwargs):
                calls.append((name, args, kwargs))
                return Layout()
            return call

        def __setattr__(self, name, value):
            pass

    from k_tools_kanvas.ui import tabs
    from k_tools_kanvas.ui.selection_panel import KANVAS_PT_SelectionPanel
    from k_tools_kanvas.properties import KanvasPanelTabs

    icons = set(bpy.types.UILayout.bl_rna.functions['prop'].parameters['icon'].enum_items.keys())
    for kind in ('image', 'shape', 'text'):
        items = KanvasPanelTabs.bl_rna.properties[kind].enum_items
        assert [item.identifier for item in items] == list(tabs.TABS[kind]), kind
        for item in items:
            assert item.icon in icons, (kind, item.identifier, item.icon)

    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Tabs', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    wm = bpy.context.window_manager

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        bpy.ops.kanvas.create_shape(kind='STAR', location=(0.0, 0.0), size=(100.0, 100.0))
        shape_id = settings.images[-1].item_id
        image = settings.images.add()
        image.item_type, image.item_id, image.name = 'IMAGE', 'image', 'Photo'
        image.image_data = bpy.data.images.new('photo', 8, 8)
        image.markup_regions.add().region_id = 'r'
        card = settings.images.add()
        card.item_type, card.item_id, card.name = 'TEXT', 'card', 'Note'
        checklist = settings.images.add()
        checklist.item_type, checklist.item_id, checklist.name = 'TEXT', 'list', 'Tasks'
        checklist.text_checklist = True
        checklist.text_lines.add().value = 'one'
        compare = settings.images.add()
        compare.item_type, compare.item_id, compare.text_compare = 'TEXT', 'compare', True
        frame = settings.images.add()
        frame.item_type, frame.item_id, frame.frame_node_name = 'FRAME', 'frame', 'kanvas_f'

        def by_id(item_id):
            return next(item for item in settings.images if item.item_id == item_id)

        def show(item_id):
            for index, item in enumerate(settings.images):
                item.is_selected = item.item_id == item_id
                if item.item_id == item_id:
                    settings.active_image_index = index
            calls.clear()
            KANVAS_PT_SelectionPanel.draw(SimpleNamespace(layout=Layout()), bpy.context)
            return calls

        # --- Every tab draws, through the real panel -------------------------------------
        for item_id, kind in ((shape_id, 'shape'), ('image', 'image'), ('card', 'text'),
                              ('list', 'text')):
            for tab in tabs.TABS[kind]:
                setattr(wm.kanvas_tabs, kind, tab)
                drawn = show(item_id)
                bars = [c for c in drawn if c[0] == 'prop' and c[1][1:2] == (kind,)]
                assert bars and bars[0][2].get('expand'), (item_id, tab, 'no tab bar')
                assert len(drawn) > 4, (item_id, tab, len(drawn))
        for item_id in ('compare', 'frame'):
            drawn = show(item_id)
            assert not [c for c in drawn if c[0] == 'prop' and c[1][1:2] in
                        (('image',), ('shape',), ('text',))], f'{item_id} has no tabs'

        # --- The open tab is the one drawn ----------------------------------------------
        wm.kanvas_tabs.shape = 'FILL'
        drawn = show(shape_id)
        props = {c[1][1] for c in drawn if c[0] == 'prop' and len(c[1]) > 1}
        assert 'shape_fill_type' in props and 'shape_line_join' not in props
        wm.kanvas_tabs.shape = 'LINE'
        props = {c[1][1] for c in show(shape_id) if c[0] == 'prop' and len(c[1]) > 1}
        assert 'shape_line_join' in props and 'shape_fill_type' not in props

        # --- The header says what is on in tabs you cannot see ---------------------------
        wm.kanvas_tabs.image = 'MAIN'
        by_id('image').mask_enabled = True
        by_id('image').markup_visible = True
        labels = [c[2].get('text') for c in show('image') if c[0] == 'label']
        assert 'Mask' in labels and '1 color' in labels, labels

        # --- Entering a mode opens its tab -----------------------------------------------
        wm.kanvas_tabs.image = 'ADJUST'
        by_id('image').mask_editing = True
        assert wm.kanvas_tabs.image == 'MASK'
        by_id('image').mask_editing = False
        assert wm.kanvas_tabs.image == 'MASK', 'leaving a mode keeps the tab'
        by_id('image').markup_editing = True
        assert wm.kanvas_tabs.image == 'MARKUP'
        by_id('image').markup_editing = False
        wm.kanvas_tabs.shape = 'TEXT'
        by_id(shape_id).shape_edit_vertices = True
        assert wm.kanvas_tabs.shape == 'MAIN'
        by_id(shape_id).shape_edit_vertices = False

    # --- A narrow sidebar shows only the icons -------------------------------------------
    for width, icon_only in ((200, True), (600, False)):
        calls.clear()
        context = SimpleNamespace(window_manager=wm, region=SimpleNamespace(width=width),
                                  preferences=bpy.context.preferences)
        tabs.draw_tab_bar(Layout(), context, 'image')
        bar = next(c for c in calls if c[0] == 'prop')
        assert bar[2]['icon_only'] is icon_only, (width, bar)
    print('test_selection_tabs: OK')
finally:
    addon.unregister()
