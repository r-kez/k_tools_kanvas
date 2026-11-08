"""Preferences and panel drawing for Auto Select, in every state."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import sam_engine

addon.register()
try:
    calls = []

    class Layout:
        enabled = True
        operator_context = ''
        def __getattr__(self, name):
            def call(*args, **kwargs):
                calls.append((name, kwargs.get('text', args[0] if args and isinstance(args[0], str) else '')))
                return Layout()
            return call
        def __setattr__(self, name, value):
            pass

    from k_tools_kanvas.preferences import KanvasPreferences
    from k_tools_kanvas.ui.tabs.auto_select import draw_auto_select as _draw_auto_select
    from k_tools_kanvas.ui.tabs.image_mask import draw_mask_properties
    from k_tools_kanvas.ui.tabs.image_markup import draw_color_properties

    tree = bpy.data.node_groups.new('ui', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_type = 'IMAGE'
    item.image_data = bpy.data.images.new('x', 8, 8)
    item.markup_regions.add().region_id = 'a'

    states = [
        ('nothing installed', dict()),
        ('installing', dict(engine={'state': 'working', 'message': 'Installing ONNX Runtime...'})),
        ('install failed', dict(engine={'state': 'error', 'message': 'pip failed: no network'})),
        ('downloading', dict(model={'state': 'working', 'message': 'Downloading x', 'progress': 0.4})),
        ('download failed', dict(model={'state': 'error', 'message': 'Download failed: timeout', 'progress': 0.0})),
        ('analyze error', dict(analyze={'state': 'error', 'message': 'Analysis failed: x', 'image': 'x'})),
    ]
    for label, override in states:
        for section, values in override.items():
            sam_engine.status[section].update(values)
        calls.clear()
        KanvasPreferences._draw_segmentation(None, Layout())
        draw_mask_properties(Layout(), item)
        draw_color_properties(Layout(), item)
        assert any(name == 'operator' for name, _ in calls) or label != 'nothing installed'
        print(f'drew "{label}": {len(calls)} UI calls')
        for section in ('engine', 'model', 'analyze'):
            sam_engine.status[section].update(state='idle', message='', progress=0.0)

    # Ready + analyzed: the tool toggle is offered and enabled.
    sam_engine.ready = lambda: True
    sam_engine.is_analyzed = lambda image: True
    calls.clear()
    _draw_auto_select(Layout(), item, 'mask_tool')
    names = [name for name, _ in calls]
    assert 'operator' in names and 'prop_enum' in names, names
    assert 'Analyze Again' in [text for _, text in calls]
    for operator in ('sam_install_engine', 'sam_download_model', 'sam_remove_files', 'sam_analyze_image'):
        assert hasattr(bpy.ops.kanvas, operator), operator
    print('AUTO SELECT UI OK')
finally:
    addon.unregister()
