"""Check card text scaling, overflow, and viewport clipping without a GPU window."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from k_tools_kanvas.utils.gpu import gpu_text


class FakeBLF:
    CLIPPING = 1

    def __init__(self):
        self.font_size = 0
        self.drawn = []
        self.clip = None
        self.clips = []

    def size(self, _font, size):
        self.font_size = size

    def dimensions(self, _font, value):
        return (len(value) * self.font_size * 0.5, self.font_size)

    def color(self, *_args):
        pass

    def enable(self, *_args):
        pass

    def disable(self, *_args):
        pass

    def clipping(self, _font, *rect):
        self.clip = rect
        self.clips.append(rect)

    def position(self, _font, x, y, _z):
        self.position_xy = x, y

    def draw(self, _font, value):
        self.drawn.append((value, self.position_xy))


class View:
    def __init__(self, zoom, offset_x=0, offset_y=0):
        self.zoom = zoom
        self.offset_x = offset_x
        self.offset_y = offset_y

    def view_to_region(self, x, y, clip=False):
        return (round(x * self.zoom + self.offset_x),
                round(y * self.zoom + self.offset_y))


card = SimpleNamespace(
    item_type='TEXT', name='Text Note', text_show_header=False, is_selected=False,
    location=(160, 90), text_width=320, text_height=180,
    text_scale=1.0, text_font_size=18, text_color=(1, 1, 1),
    text_header='', text_checklist=False, text_markdown=False,
    text_scroll=0.0,
    text_lines=[SimpleNamespace(value='First line'),
                SimpleNamespace(value='Second line')],
)
original_blf = gpu_text.blf
original_draw_canvas_text = gpu_text.draw_canvas_text
original_underline = gpu_text._draw_overflow_underline
original_colored_rule = gpu_text._draw_colored_rule
original_continuation = gpu_text._draw_scroll_continuation
original_enable_scissor = gpu_text._enable_body_scissor
original_disable_scissor = gpu_text._disable_body_scissor
original_checkbox = gpu_text._draw_checkbox
fake = FakeBLF()
gpu_text.blf = fake
gpu_text.draw_canvas_text = lambda font, value, x, y, color, size: (
    fake.position(font, x, y, 0), fake.draw(font, value))
underlines = []
gpu_text._draw_overflow_underline = underlines.append
gpu_text._draw_colored_rule = lambda vertices, color: None
continuations = []
gpu_text._draw_scroll_continuation = lambda layout, rects, item: continuations.append(layout)
scissors = []
gpu_text._enable_body_scissor = lambda rect: scissors.append(rect)
gpu_text._disable_body_scissor = lambda: None
gpu_text._draw_checkbox = lambda *args: None
try:
    for zoom, expected_size in ((0.5, 9), (1, 18), (2, 36)):
        fake.drawn.clear()
        region = SimpleNamespace(view2d=View(zoom), width=1200, height=900)
        gpu_text.draw_text_label(card, region)
        assert fake.font_size == expected_size, (zoom, fake.font_size)
        assert len(fake.drawn) == 2, (zoom, fake.drawn)
    assert not underlines

    card.text_scale = 2.0
    fake.drawn.clear()
    gpu_text.draw_text_label(card, SimpleNamespace(
        view2d=View(1), width=1200, height=900))
    assert fake.font_size == 36
    card.text_scale = 1.0

    fake.drawn.clear()
    gpu_text.draw_text_label(card, SimpleNamespace(
        view2d=View(0.1), width=1200, height=900))
    assert not fake.drawn  # Do not hold text at a fixed minimum screen size.

    card.text_height = 60
    card.text_lines = [SimpleNamespace(value='One two three four five six seven eight'),
                       SimpleNamespace(value='Another paragraph must be cut')]
    fake.drawn.clear()
    gpu_text.draw_text_label(card, SimpleNamespace(
        view2d=View(1), width=1200, height=900))
    assert fake.drawn and not any(value.endswith('…') for value, _ in fake.drawn)
    assert not underlines
    assert fake.clip == (2, 72.0, 318, 108.0), fake.clip
    assert scissors[-1] == fake.clip
    assert continuations[-1]['max_scroll'] > 0

    fake.drawn.clear()
    gpu_text.draw_text_label(card, SimpleNamespace(
        view2d=View(1, -100, -50), width=200, height=100))
    assert fake.clip == (0, 22.0, 200, 58.0), fake.clip

    assert gpu_text._subtract_rect((0, 0, 100, 100), (25, 25, 75, 75)) == [
        (0, 0, 25, 100), (75, 0, 100, 100),
        (25, 0, 75, 25), (25, 75, 75, 100),
    ]
    fake.clips.clear()
    gpu_text.draw_text_label(card, SimpleNamespace(
        view2d=View(1), width=1200, height=900),
        occluders=[(100, 60, 220, 120)])
    assert fake.clips == [
        (2, 62, 100, 118), (2, 72.0, 100, 108.0),
        (220, 62, 318, 118), (220, 72.0, 318, 108.0),
    ], fake.clips
    assert gpu_text._underline_triangles(
        [(0, 0, 40, 20), (60, 0, 100, 20)], 20, 80, 10, 2) == [
            (20, 9), (40, 9), (40, 11), (20, 9), (40, 11), (20, 11),
            (60, 9), (80, 9), (80, 11), (60, 9), (80, 11), (60, 11),
        ]

    card.text_font_size = 72
    fake.drawn.clear()
    gpu_text.draw_text_label(card, SimpleNamespace(
        view2d=View(1), width=1200, height=900))
    assert [value for value, _ in fake.drawn] == ['…'], fake.drawn

    card.text_font_size = 18
    card.text_height = 100
    card.text_show_header = True
    card.text_scroll = 15
    fake.drawn.clear()
    scissors.clear()
    header_region = SimpleNamespace(view2d=View(1), width=1200, height=900)
    gpu_text.draw_text_label(card, header_region)
    body_top = gpu_text._scroll_layout(card, header_region)['top']
    assert scissors and all(rect[3] == body_top for rect in scissors), scissors

    card.text_markdown = True
    card.text_show_header = False
    card.text_height = 180
    card.text_scroll = 0
    card.text_lines = [SimpleNamespace(value=line) for line in (
        '#### Heading', '> Quote', '- **bold** and *italic*',
        '---', '~~gone~~ [link](https://a.com)')]
    fake.drawn.clear()
    gpu_text.draw_text_label(card, header_region)
    assert fake.drawn and any('H' in value for value, _ in fake.drawn)

    card.text_lines = [SimpleNamespace(value=line) for line in (
        '| Name | Count | Cost |', '| --- | :---: | ---: |',
        '| Widgets | 12 | $1600 |')]
    fake.drawn.clear()
    gpu_text.draw_text_label(card, header_region)
    assert fake.drawn and any('W' in value for value, _ in fake.drawn)
    assert any(len(value) > 1 for value, _ in fake.drawn)

    card.text_markdown = False
    card.text_checklist = True
    card.text_lines = [SimpleNamespace(value='**Bold** [link](https://example.com) *note*',
                                       done=False)]
    fake.drawn.clear()
    gpu_text.draw_text_label(card, header_region)
    assert any(value == 'Bold' for value, _ in fake.drawn)
    assert any(value == 'link' for value, _ in fake.drawn)
    assert not any('**' in value for value, _ in fake.drawn)
finally:
    gpu_text.blf = original_blf
    gpu_text.draw_canvas_text = original_draw_canvas_text
    gpu_text._draw_overflow_underline = original_underline
    gpu_text._draw_colored_rule = original_colored_rule
    gpu_text._draw_scroll_continuation = original_continuation
    gpu_text._enable_body_scissor = original_enable_scissor
    gpu_text._disable_body_scissor = original_disable_scissor
    gpu_text._draw_checkbox = original_checkbox

print('PASS text zoom, overflow, and clipping')
