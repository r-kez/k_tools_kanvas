"""Comparison card: geometry, modes, divider drag math, drawing path, Check Board."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.board_check import find_problems, fix_problems
from k_tools_kanvas.utils.gpu import gpu_compare
from k_tools_kanvas.utils.gpu.gpu_compare import (
    compare_layout, crop_to_range, divider_x, fit_rect, hit_compare_button, hit_compare_divider,
    next_mode, side_item, split_from_position, uv_window)

# --- pure geometry -----------------------------------------------------------
card = SimpleNamespace(text_width=400.0, text_font_size=18, compare_mode='SPLIT', compare_split=0.5)
bounds = (100.0, 100.0, 500.0, 400.0)
layout = compare_layout(card, bounds)
assert layout['size'] >= 30, 'buttons are large enough to click'
assert layout['MODE'][2] < layout['A'][0] < layout['A'][2] < layout['B'][0], 'order is mode, A, B'
assert layout['B'][2] < bounds[2] and layout['B'][3] < bounds[3], 'buttons stay inside the card'
content = layout['content']
assert bounds[0] < content[0] and content[2] < bounds[2] and content[3] < layout['A'][1]
assert compare_layout(card, (0, 0, 40, 30))['size'] < gpu_compare.MIN_BUTTON_PIXELS, 'tiny cards hide their buttons'
narrow = compare_layout(card, (0.0, 0.0, 130.0, 400.0))
assert narrow is None or narrow['MODE'] is None or narrow['MODE'][0] >= 0


def center(rect):
    return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


for name in ('A', 'B', 'MODE'):
    assert hit_compare_button(card, bounds, center(layout[name])) == name, name
assert hit_compare_button(card, bounds, (200.0, 200.0)) is None

split_x = divider_x(content, 0.5)
assert hit_compare_divider(card, bounds, (split_x + 5, 200.0), 9)
assert not hit_compare_divider(card, bounds, (split_x + 40, 200.0), 9)
assert not hit_compare_divider(card, bounds, (split_x, content[3] + 5), 9), 'only within the image area'
card.compare_mode = 'FADE'
assert not hit_compare_divider(card, bounds, (split_x, 200.0), 9), 'no divider outside split mode'
card.compare_mode = 'SPLIT'
assert split_from_position(card, bounds, content[0]) == 0.0
assert split_from_position(card, bounds, content[2] + 999) == 1.0
assert abs(split_from_position(card, bounds, split_x) - 0.5) < 1e-9

assert [next_mode(m) for m in ('SPLIT', 'FADE', 'DIFF')] == ['FADE', 'DIFF', 'SPLIT']
assert next_mode('SPLIT', -1) == 'DIFF'

assert fit_rect((0.0, 0.0, 200.0, 100.0), 400, 100) == (0.0, 25.0, 200.0, 75.0)
assert fit_rect((0.0, 0.0, 200.0, 100.0), 100, 400) == (87.5, 0.0, 112.5, 100.0)
assert fit_rect((0, 0, 0, 100), 10, 10) is None
assert divider_x((10.0, 0.0, 110.0, 50.0), 0.25) == 35.0 and divider_x((10, 0, 110, 50), 5) == 110
rect = (0.0, 0.0, 100.0, 50.0)
shown, uv = crop_to_range(rect, 0.0, 25.0)
assert shown == (0.0, 0.0, 25.0, 50.0) and uv == (0.0, 0.0, 0.25, 1.0), (shown, uv)
assert crop_to_range(rect, 200.0, 300.0) is None
window, area = uv_window((0.0, 0.0, 100.0, 50.0), (50.0, 10.0, 200.0, 30.0))
assert window == (0.5, 0.2, 1.0, 0.6) and area == (50.0, 10.0, 100.0, 30.0), (window, area)

# --- add-on behaviour ----------------------------------------------------------
addon.register()
try:
    tree = bpy.data.node_groups.new('Compare', 'KanvasNodeTree')
    settings = tree.kanvas_settings

    def add_image(name):
        item = settings.images.add()
        item.item_type, item.item_id, item.name = 'IMAGE', name, name
        item.image_data = bpy.data.images.new(name, 8, 4)
        return item

    one, two = add_image('one'), add_image('two')
    cmp_card = settings.images.add()
    cmp_card.item_type, cmp_card.item_id, cmp_card.name = 'TEXT', 'cmp', 'Compare'
    cmp_card.text_compare = True
    assert cmp_card.compare_mode == 'SPLIT' and cmp_card.compare_split == 0.5
    assert cmp_card.compare_blend == 0.5 and cmp_card.compare_gain == 1.0
    cmp_card.compare_a_id, cmp_card.compare_b_id = 'one', 'two'
    assert side_item(settings, cmp_card, 'A').name == 'one'
    assert find_problems(settings) == []
    settings.images.remove(1)
    assert side_item(settings, cmp_card, 'B') is None
    assert [p.kind for p in find_problems(settings)] == ['COMPARE']
    count = len(settings.images)
    assert fix_problems(settings) == 1 and len(settings.images) == count
    cmp_card = next(i for i in settings.images if i.item_id == 'cmp')
    assert cmp_card.compare_b_id == '' and cmp_card.compare_a_id == 'one'

    # --- drawing path with a recording stand-in for the GPU ------------------------
    drawn, diff_calls = [], []

    class Texture:
        texture = object()

        def draw_rect(self, rect, uv, opacity, *args):
            drawn.append((rect, uv, opacity))

    class Shader:
        def bind(self): pass
        def uniform_float(self, *a): pass
        def uniform_sampler(self, *a): diff_calls.append(a[0])

    class Batch:
        def draw(self, shader): pass

    gpu_compare.batch_for_shader = lambda *a, **k: Batch()
    gpu_compare.draw_canvas_text = lambda *a, **k: None
    gpu_compare.draw_rounded_fill = lambda *a, **k: None
    gpu_compare.draw_rounded_border = lambda *a, **k: None
    gpu_compare.gpu = SimpleNamespace(
        shader=SimpleNamespace(from_builtin=lambda name: Shader()),
        state=SimpleNamespace(blend_get=lambda: 'NONE', blend_set=lambda mode: None))
    gpu_compare.selection_color = lambda: (0.0, 0.8, 1.0, 1.0)
    gpu_compare.studio_enabled = lambda: False
    gpu_compare.get_diff_shader = lambda: Shader()
    gpu_compare.blf = SimpleNamespace(size=lambda *a: None, dimensions=lambda *a: (10.0, 8.0),
                                      enable=lambda *a: None, disable=lambda *a: None,
                                      clipping=lambda *a: None, CLIPPING=1)
    import k_tools_kanvas.utils.gpu.gpu_image as gpu_image
    import k_tools_kanvas.utils.gpu.gpu_text as gpu_text
    gpu_image.get_kanvas_texture = lambda image: Texture()
    gpu_text.draw_text_card = lambda *a, **k: None

    add_image('two')
    cmp_card = next(i for i in settings.images if i.item_id == 'cmp')
    cmp_card.compare_b_id = 'two'
    cmp_card.text_width, cmp_card.text_height = 400.0, 300.0
    cmp_card.location = (0.0, 0.0)

    gpu_compare.draw_compare_content(cmp_card, settings, 1.0)
    assert len(drawn) == 2, 'split draws both halves'
    (a_rect, a_uv, _), (b_rect, b_uv, _) = drawn
    assert a_rect[2] <= b_rect[0] + 1e-6 and a_uv[2] < 1.0 and b_uv[0] > 0.0

    drawn.clear()
    cmp_card.compare_split = 1.0
    gpu_compare.draw_compare_content(cmp_card, settings, 1.0)
    assert len(drawn) == 1 and drawn[0][1][2] == 1.0, 'divider at the end shows only A, whole'

    drawn.clear()
    cmp_card.compare_mode, cmp_card.compare_blend = 'FADE', 0.3
    gpu_compare.draw_compare_content(cmp_card, settings, 1.0)
    assert len(drawn) == 2 and drawn[0][2] == 1.0 and abs(drawn[1][2] - 0.3) < 1e-6, drawn

    drawn.clear()
    cmp_card.compare_mode = 'DIFF'
    gpu_compare.draw_compare_content(cmp_card, settings, 1.0)
    assert diff_calls == ['image_a', 'image_b'] and not drawn, 'difference uses its own shader'

    # Without the difference shader the card falls back to Fade.
    gpu_compare.get_diff_shader = lambda: None
    drawn.clear()
    gpu_compare.draw_compare_content(cmp_card, settings, 1.0)
    assert len(drawn) == 2, 'Diff falls back to Fade'

    for mode in ('SPLIT', 'FADE', 'DIFF'):
        cmp_card.compare_mode = mode
        gpu_compare.draw_compare_overlay(cmp_card, None, settings, (100.0, 100.0, 500.0, 400.0))

    assert hasattr(bpy.ops.kanvas, 'pick_compare_side') and hasattr(bpy.ops.kanvas, 'drag_compare_divider')
    print('COMPARE CARD OK')
finally:
    addon.unregister()
