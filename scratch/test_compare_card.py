"""Comparison card: creation, geometry helpers, side lookup, drawing path, Check Board."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.board_check import find_problems, fix_problems
from k_tools_kanvas.utils.gpu import gpu_compare
from k_tools_kanvas.utils.gpu.gpu_compare import (compare_layout, crop_to_range, divider_x,
                                                  fit_rect, hit_compare_button, side_item)

# --- pure geometry -----------------------------------------------------------
card = SimpleNamespace(text_width=400.0, text_font_size=14)
bounds = (100.0, 100.0, 500.0, 400.0)                       # a 1:1 card, 400 x 300 px
layout = compare_layout(card, bounds)
assert layout and layout['size'] == 14 and layout['A'][2] < layout['B'][0], 'A sits left of B'
assert layout['B'][2] < bounds[2] and layout['B'][3] < bounds[3], 'buttons stay inside the card'
content = layout['content']
assert bounds[0] < content[0] and content[2] < bounds[2] and content[3] < layout['A'][1], 'content is below the buttons'
assert compare_layout(card, (0, 0, 40, 30)) is None, 'tiny cards show nothing'
center = layout['A']
assert hit_compare_button(card, bounds, ((center[0] + center[2]) / 2, (center[1] + center[3]) / 2)) == 'A'
assert hit_compare_button(card, bounds, (200.0, 200.0)) is None

wide = fit_rect((0.0, 0.0, 200.0, 100.0), 400, 100)          # 4:1 fits the width
assert wide == (0.0, 25.0, 200.0, 75.0), wide
tall = fit_rect((0.0, 0.0, 200.0, 100.0), 100, 400)          # 1:4 fits the height
assert tall == (87.5, 0.0, 112.5, 100.0), tall
assert fit_rect((0, 0, 0, 100), 10, 10) is None

assert divider_x((10.0, 0.0, 110.0, 50.0), 0.25) == 35.0 and divider_x((10, 0, 110, 50), 5) == 110
rect = (0.0, 0.0, 100.0, 50.0)
shown, uv = crop_to_range(rect, 0.0, 25.0)
assert shown == (0.0, 0.0, 25.0, 50.0) and uv == (0.0, 0.0, 0.25, 1.0), (shown, uv)
shown, uv = crop_to_range(rect, 25.0, 500.0)
assert shown == (25.0, 0.0, 100.0, 50.0) and uv == (0.25, 0.0, 1.0, 1.0)
assert crop_to_range(rect, 200.0, 300.0) is None, 'nothing visible outside the image'

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
    assert cmp_card.compare_split == 0.5 and side_item(settings, cmp_card, 'A') is None

    cmp_card.compare_a_id = 'one'
    assert side_item(settings, cmp_card, 'A').name == 'one'
    cmp_card.compare_b_id = 'two'
    assert side_item(settings, cmp_card, 'B').name == 'two'
    assert find_problems(settings) == []

    # An image that is no longer on the board is reported and cleared, never deleted.
    settings.images.remove(1)                                   # 'two'
    assert side_item(settings, cmp_card, 'B') is None, 'a missing image just shows empty'
    problems = [p.kind for p in find_problems(settings)]
    assert problems == ['COMPARE'], problems
    count = len(settings.images)
    assert fix_problems(settings) == 1 and len(settings.images) == count
    cmp_card = next(i for i in settings.images if i.item_id == 'cmp')
    assert cmp_card.compare_b_id == '' and cmp_card.compare_a_id == 'one', 'only the broken side is cleared'

    # Drawing path with a recording stand-in for the GPU.
    drawn = []

    class Texture:
        def draw_rect(self, rect, uv, *args):
            drawn.append((rect, uv))

    class Shader:
        def bind(self): pass
        def uniform_float(self, *a): pass

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
    gpu_compare.blf = SimpleNamespace(size=lambda *a: None, dimensions=lambda *a: (10.0, 8.0),
                                      enable=lambda *a: None, disable=lambda *a: None,
                                      clipping=lambda *a: None, CLIPPING=1)
    import k_tools_kanvas.utils.gpu.gpu_image as gpu_image
    gpu_image.get_kanvas_texture = lambda image: Texture()
    two = add_image('two')
    cmp_card = next(i for i in settings.images if i.item_id == 'cmp')
    cmp_card.compare_b_id = 'two'
    cmp_card.text_width, cmp_card.text_height = 400.0, 300.0
    gpu_compare.draw_compare_card(cmp_card, None, settings, (100.0, 100.0, 500.0, 400.0))
    assert len(drawn) == 2, 'both halves were drawn'
    (a_rect, a_uv), (b_rect, b_uv) = drawn
    assert a_rect[2] <= b_rect[0] + 1e-6 and a_uv[2] < 1.0 and b_uv[0] > 0.0, 'A is cut at the divider, B starts there'
    drawn.clear()
    cmp_card.compare_split = 1.0
    gpu_compare.draw_compare_card(cmp_card, None, settings, (100.0, 100.0, 500.0, 400.0))
    assert len(drawn) == 1 and drawn[0][1][2] == 1.0, 'with the divider at the end only A shows, fully'

    assert hasattr(bpy.ops.kanvas, 'pick_compare_side')
    print('COMPARE CARD OK')
finally:
    addon.unregister()
