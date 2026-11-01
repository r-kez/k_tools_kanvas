"""Dashed/dotted lines and head placement: geometry helpers and the property defaults."""

import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.arrow_geometry import (dash_pattern, dash_polylines, head_reach,
                                                 polyline_length, slice_polyline)

line = [(0.0, 0.0), (50.0, 0.0), (50.0, 50.0)]           # length 100, with a corner
assert polyline_length(line) == 100
part = slice_polyline(line, 40, 60)
assert part == [(40.0, 0.0), (50.0, 0.0), (50.0, 10.0)], part
assert slice_polyline(line, 0, 100) == line
assert slice_polyline(line, 120, 200) == [] and slice_polyline(line, 30, 30) == []
assert slice_polyline(line, -10, 5) == [(0.0, 0.0), (5.0, 0.0)], 'clamped to the start'

dashes = dash_polylines(line, 10, 5)
assert len(dashes) == 7 and all(abs(polyline_length(d) - 10) < 1e-6 for d in dashes[:-1]), len(dashes)
assert abs(polyline_length(dashes[-1]) - 10) < 1e-6 or polyline_length(dashes[-1]) <= 10
assert dash_polylines(line, 0, 0) == [line], 'no pattern means the whole line'
dash, gap = dash_pattern('DASHED', 2.5)
assert dash > gap > 0 and dash_pattern('SOLID', 2.5) == (0.0, 0.0)
dots = dash_polylines([(0.0, 0.0), (100.0, 0.0)], *dash_pattern('DOTTED', 2.5))
assert len(dots) > 10 and all(polyline_length(d) < 0.1 for d in dots), 'dots are tiny dashes'
assert head_reach(2.5) > head_reach(1.0) or head_reach(1.0) > 0
assert math.isfinite(head_reach(20.0))

addon.register()
try:
    tree = bpy.data.node_groups.new('Style', 'KanvasNodeTree')
    arrow = tree.kanvas_settings.arrows.add()
    assert arrow.line_style == 'SOLID' and arrow.head_style == 'END', 'old arrows look unchanged'
    arrow.line_style, arrow.head_style = 'DOTTED', 'BOTH'

    # Run the drawing code with a recording stand-in for the GPU.
    from types import SimpleNamespace
    from k_tools_kanvas.utils.gpu import gpu_arrow

    drawn = []

    class Batch:
        def __init__(self, count):
            self.count = count

        def draw(self, shader):
            drawn.append(self.count)

    class Shader:
        def bind(self): pass
        def uniform_float(self, *args): pass

    gpu_arrow.batch_for_shader = lambda shader, kind, data: Batch(len(data['pos']))
    points = [(0.0, 0.0), (60.0, 20.0), (120.0, 0.0), (180.0, 30.0)]
    length = polyline_length(points)
    sizes = {}
    for style in ('FILLED', 'ROUNDED'):
        prefs = SimpleNamespace(arrow_style='ROUNDED' if style == 'ROUNDED' else 'SOLID')
        for line_style in ('SOLID', 'DASHED', 'DOTTED'):
            for heads in ('END', 'BOTH', 'NONE'):
                arrow.line_style, arrow.head_style = line_style, heads
                drawn.clear()
                gpu_arrow._draw_arrow_body(Shader(), Shader(), points, arrow, length,
                                           1.0, (1, 1, 1, 1), prefs)
                assert sum(drawn) > 0, (style, line_style, heads)
                sizes[(style, line_style, heads)] = sum(drawn)
    assert sizes[('FILLED', 'DASHED', 'END')] != sizes[('FILLED', 'SOLID', 'END')]
    assert sizes[('FILLED', 'SOLID', 'BOTH')] > sizes[('FILLED', 'SOLID', 'END')] > 0
    print('ARROW LINE STYLE OK')
finally:
    addon.unregister()
