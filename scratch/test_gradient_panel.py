"""The shape panel draws with Solid, Linear and Radial fills: Blender's color ramp
widget and the gradient buttons appear only for a gradient, and a shape without a ramp
yet (saved by an older version) offers Edit Colors instead."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    calls = []

    class Layout:
        enabled = True
        use_property_split = False
        ui_units_x = 0

        def __getattr__(self, name):
            def call(*args, **kwargs):
                calls.append((name, args, kwargs))
                return Layout()
            return call

        def __setattr__(self, name, value):
            pass

    from k_tools_kanvas.ui.sections.shape_properties import draw_shape_properties
    tree = bpy.data.node_groups.new('ui', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    item = settings.images.add()
    item.item_type, item.item_id, item.name = 'SHAPE', 'shape', 'Shape'
    for kind in ('SOLID', 'LINEAR', 'RADIAL'):
        item.shape_fill_type = kind
        calls.clear()
        draw_shape_properties(Layout(), settings, item)
        ramps = [c for c in calls if c[0] == 'template_color_ramp']
        operators = {c[1][0] for c in calls if c[0] == 'operator'}
        if kind == 'SOLID':
            assert not ramps and 'kanvas.gradient_rotate' not in operators
        else:
            assert ramps and ramps[0][1][1] == 'color_ramp'
            assert ramps[0][1][0] == item.shape_gradient_texture
            assert {'kanvas.gradient_rotate', 'kanvas.gradient_reset_points'} <= operators
            labels = [c[2].get('text') for c in calls if c[0] == 'label']
            assert ('Center' in labels) == (kind == 'RADIAL'), labels
        print(f'{kind}: {len(calls)} UI calls')
    item.shape_gradient_texture = None
    calls.clear()
    draw_shape_properties(Layout(), settings, item)
    assert not [c for c in calls if c[0] == 'template_color_ramp']
    assert 'kanvas.gradient_edit_colors' in {c[1][0] for c in calls if c[0] == 'operator'}
    print('test_gradient_panel: OK')
finally:
    addon.unregister()
