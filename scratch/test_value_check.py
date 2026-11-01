"""Grayscale / posterize value check: properties, batch, shader assembly and fallback."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu import gpu_common

addon.register()
try:
    tree = bpy.data.node_groups.new('Values', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    items = []
    for index in range(2):
        item = settings.images.add()
        item.item_type, item.item_id = 'IMAGE', f'img{index}'
        item.image_data = bpy.data.images.new(f'v{index}', 4, 4)
        items.append(item)

    # ---- per image ---------------------------------------------------------
    first = items[0]
    assert not first.value_gray and first.value_levels == 0
    assert gpu_common.value_view_uniforms(first) == (0.0, 0.0), 'off by default'
    first.value_gray = True
    assert gpu_common.value_view_uniforms(first) == (1.0, 0.0)
    first.value_levels = 4
    assert gpu_common.value_view_uniforms(first) == (2.0, 4.0), 'posterize wins over plain grayscale'
    first.value_levels = 1
    assert gpu_common.value_view_uniforms(first) == (1.0, 0.0), 'a single tone is not a valid posterize'
    first.value_gray, first.value_levels = False, 0
    print('PER IMAGE OK')

    # ---- batch over the selection ----------------------------------------------
    for item in items:
        item.is_selected = True
    settings.active_image_index = 0
    settings.batch_value_gray = True
    assert all(item.value_gray for item in items)
    settings.batch_value_levels = 3
    assert all(item.value_levels == 3 for item in items)
    items[1].is_selected = False
    settings.batch_value_levels = 0
    assert items[0].value_levels == 0 and items[1].value_levels == 3, 'only the selection changes'
    print('BATCH OK')

    # ---- shader assembly with a stand-in GPU -------------------------------------
    built = []

    class Info:
        def __init__(self):
            self.constants, self.source = [], ''
        def push_constant(self, kind, name): self.constants.append(name)
        def sampler(self, *a): pass
        def vertex_in(self, *a): pass
        def vertex_out(self, *a): pass
        def fragment_out(self, *a): pass
        def vertex_source(self, text): pass
        def fragment_source(self, text): self.source = text

    class Iface:
        def __init__(self, name): pass
        def smooth(self, *a): pass

    state = {'fail_first': False, 'calls': 0}

    def create_from_info(info):
        state['calls'] += 1
        if state['fail_first'] and state['calls'] == 1:
            raise RuntimeError('simulated compile error')
        built.append(info)
        return SimpleNamespace(program=True)

    fake_gpu = SimpleNamespace(
        types=SimpleNamespace(GPUStageInterfaceInfo=Iface, GPUShaderCreateInfo=Info),
        shader=SimpleNamespace(create_from_info=create_from_info))
    real_gpu = gpu_common.gpu
    gpu_common.gpu = fake_gpu
    try:
        gpu_common._custom_shader, gpu_common._value_view_supported = None, True
        assert gpu_common.get_kanvas_shader() is not None
        info = built[-1]
        assert 'value_mode' in info.constants and 'value_levels' in info.constants
        assert 'value_mode > 1.5' in info.source and 'floor(' in info.source
        assert info.source.count('{') == info.source.count('}'), 'balanced braces in the fragment code'
        assert gpu_common.shader_supports_value_view()
        print('SHADER WITH VALUE CHECK OK')

        # The extended shader is rejected: fall back to the basic one.
        gpu_common._custom_shader, gpu_common._value_view_supported = None, True
        state.update(fail_first=True, calls=0)
        assert gpu_common.get_kanvas_shader() is not None, 'images must still be drawn'
        basic = built[-1]
        assert 'value_mode' not in basic.constants and 'value_mode' not in basic.source
        assert not gpu_common.shader_supports_value_view()
        print('FALLBACK OK')
    finally:
        gpu_common.gpu = real_gpu
        gpu_common._custom_shader, gpu_common._value_view_supported = None, True

    # ---- the panel draws ---------------------------------------------------------
    calls = []

    class Layout:
        enabled = True
        operator_context = ''
        def __getattr__(self, name):
            def call(*args, **kwargs):
                calls.append((name, args, kwargs))
                return Layout()
            return call
        def __setattr__(self, name, value): pass

    from k_tools_kanvas.ui.sections.image_properties import draw_image_properties
    items[1].is_selected = True
    draw_image_properties(Layout(), settings, items[0])
    drawn = [args[1] for name, args, kwargs in calls if name == 'prop' and len(args) > 1]
    assert 'batch_value_gray' in drawn and 'batch_value_levels' in drawn, drawn
    items[1].is_selected = False
    calls.clear()
    draw_image_properties(Layout(), settings, items[0])
    drawn = [args[1] for name, args, kwargs in calls if name == 'prop' and len(args) > 1]
    assert 'value_gray' in drawn and 'value_levels' in drawn, drawn
    print('VALUE CHECK OK')
finally:
    addon.unregister()
