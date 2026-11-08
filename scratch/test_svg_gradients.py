"""SVG gradients: linear and radial fills come in as shape gradients (box and user
units, href inheritance, gradientTransform, spread, one or no stops), and a shape with a
gradient goes out and back in unchanged."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import shape_gradient as sg
from k_tools_kanvas.utils.svg_shapes import export_svg, parse_svg


def close(a, b, tol=1e-3):
    return all(abs(x - y) < tol for x, y in zip(a, b))


SVG = '''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs>
    <linearGradient id="base">
      <stop offset="0" stop-color="#ff0000"/>
      <stop offset="100%" style="stop-color:#0000ff;stop-opacity:0.5"/>
    </linearGradient>
    <linearGradient id="down" xlink:href="#base" x1="0" y1="0" x2="0" y2="1"
                    spreadMethod="reflect"/>
    <linearGradient id="user" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="50" y2="0"
                    gradientTransform="translate(10 0)">
      <stop offset="0.2" stop-color="white"/><stop offset="0.1" stop-color="black"/>
    </linearGradient>
    <radialGradient id="glow"><stop offset="0" stop-color="#fff"/>
      <stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>
    <linearGradient id="one"><stop offset="0" stop-color="#00ff00" stop-opacity="0.5"/></linearGradient>
    <linearGradient id="empty"/>
  </defs>
  <rect id="across" x="0" y="0" width="200" height="100" fill="url(#base)"/>
  <rect id="downward" x="0" y="200" width="100" height="100" fill="url(#down)"/>
  <rect id="user" x="0" y="400" width="100" height="100" fill="url(#user)"/>
  <circle id="glow" cx="500" cy="50" r="40" fill="url(#glow)"/>
  <rect id="one" x="0" y="600" width="10" height="10" fill="url( #one )"/>
  <rect id="empty" x="0" y="700" width="10" height="10" fill="url(#empty)" stroke="black"/>
</svg>'''

# --- Parsing (canvas points, y up) ---------------------------------------------------
outlines = {outline['name']: outline for outline in parse_svg(SVG)}
across = outlines['across']['gradient']
assert across['type'] == 'LINEAR' and across['spread'] == 'PAD'
assert close(across['start'], (0, 0)) and close(across['end'], (200, 0)), across
assert close(across['stops'][1], (0, 0, 1, 0.5, 1.0)), across['stops']
down = outlines['downward']['gradient']
assert down['spread'] == 'REFLECT' and len(down['stops']) == 2, 'stops come from href'
assert close(down['start'], (0, -200)) and close(down['end'], (0, -300)), down
user = outlines['user']['gradient']
assert close(user['start'], (10, 0)) and close(user['end'], (60, 0)), user
assert user['stops'][1][4] == 0.2, 'offsets never go back'
glow = outlines['glow']['gradient']
assert glow['type'] == 'RADIAL' and close(glow['start'], (500, -50))
assert close(glow['end'], (540, -50)), glow
assert outlines['one']['gradient'] is None and close(outlines['one']['fill'], (0, 1, 0))
assert abs(outlines['one']['fill_opacity'] - 0.5) < 1e-6, 'one stop is a flat fill'
assert outlines['empty']['fill'] is None, 'no stops paints nothing'

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('SVG gradients', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        from k_tools_kanvas.operators.ops_shape import import_svg_shapes
        shapes, skipped = import_svg_shapes(bpy.context, settings, SVG, (0.0, 0.0))
        by_name = {shape.name: shape for shape in shapes}
        rect = by_name['across']
        assert rect.shape_fill_type == 'LINEAR'
        # SVG's default line runs along the top of the box (y1 = y2 = 0%).
        assert close(tuple(rect.shape_gradient_start), (-0.5, 0.5))
        assert close(tuple(rect.shape_gradient_end), (0.5, 0.5))
        circle = by_name['glow']
        assert circle.shape_fill_type == 'RADIAL'
        assert close(tuple(circle.shape_gradient_start), (0.0, 0.0))
        assert close(tuple(circle.shape_gradient_end), (0.5, 0.0), 1e-2)
        assert by_name['one'].shape_fill_type == 'SOLID'

        # --- Round trip ------------------------------------------------------------------
        rect.rotation = 30.0
        rect.shape_gradient_spread = 'REPEAT'
        text = export_svg([rect, circle])
        assert '<defs>' in text and 'url(#kanvas-gradient-1)' in text
        again = {outline['name']: outline for outline in parse_svg(text)}
        for shape in (rect, circle):
            gradient = again[shape.name]['gradient']
            start, end = sg.canvas_points(shape)
            assert gradient['type'] == shape.shape_fill_type
            assert gradient['spread'] == shape.shape_gradient_spread
            assert close(gradient['start'], start, 1e-2) and close(gradient['end'], end, 1e-2), \
                (shape.name, gradient, start, end)
            ours = sg.stop_records(shape)
            assert len(gradient['stops']) == len(ours)
            assert all(close(a, b, 3e-3) for a, b in zip(gradient['stops'], ours)),                 (gradient['stops'], ours)
    print('test_svg_gradients: OK')
finally:
    addon.unregister()
