"""Shapes and SVG: reading paths (every command, arcs, transforms, CSS classes), turning
outlines into shapes with vertex types, export/import round trip, and the per-shape
curve resolution."""
import math
import os
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_shape import (import_svg_shapes, normalize_shape,
                                                set_vertex_type)
from k_tools_kanvas.properties import set_vertex_records
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils import svg_shapes as svg


def close(a, b, tol=1e-3):
    return math.dist(a, b) < tol


addon.register()
try:
    # --- pure parsing -----------------------------------------------------------------
    assert svg.parse_color('#f80') == (1.0, 0x88 / 255, 0.0)
    assert svg.parse_color('#FF000080') == (1.0, 0.0, 0.0)
    assert svg.parse_color('rgb(255, 0, 51)') == (1.0, 0.0, 0.2)
    assert svg.parse_color('rgb(100%,50%,0%)') == (1.0, 0.5, 0.0)
    assert svg.parse_color('none') is None and svg.parse_color('navy') == (0.0, 0.0, 128 / 255)
    assert svg.parse_color('url(#grad)') == svg.GRADIENT_FALLBACK

    [(segments, closed)] = svg.parse_path('M0 0 H10 V10 H0 Z')
    assert closed and len(segments) == 4 and segments[2][3] == (0.0, 10.0)
    [(segments, closed)] = svg.parse_path('m10 10 20 0 0 20z')     # implicit relative lines
    assert closed and [s[3] for s in segments] == [(30.0, 10.0), (30.0, 30.0), (10.0, 10.0)]
    [(segments, _)] = svg.parse_path('M0 0a5 5 0 1010 0')           # compact arc flags
    assert close(segments[-1][3], (10.0, 0.0)) and len(segments) == 2
    for segment in segments:                                       # a half circle of radius 5
        for t in (0.25, 0.5, 0.75):
            assert abs(math.dist(sg.cubic(segment, t), (5.0, 0.0)) - 5.0) < 0.01
    [(segments, _)] = svg.parse_path('M0 0 Q5 10 10 0 T20 0')
    assert len(segments) == 2 and close(sg.cubic(segments[0], 0.5), (5.0, 5.0))
    assert close(segments[1][1], (10 + (10 / 3), -10 * 2 / 3)), segments[1][1]
    [(segments, _)] = svg.parse_path('M0 0 C0 10 10 10 10 0 S20 -10 20 0')
    assert segments[1][1] == (10.0, -10.0)
    two = svg.parse_path('M0 0 L10 0 L10 10 Z M2 2 L8 2 L8 8 Z')
    assert len(two) == 2 and all(c for _, c in two)

    document = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <style>.warm { fill: #ff8800; stroke: #000; stroke-width: 2 }</style>
      <defs><rect id="hidden" width="5" height="5"/></defs>
      <g transform="translate(10 20) scale(2)">
        <rect id="box" class="warm" x="0" y="0" width="10" height="5"/>
        <circle id="dot" cx="20" cy="0" r="5" fill="blue" stroke-dasharray="2 2" stroke="red"/>
      </g>
      <polyline points="0,0 10,0 10,10" fill="none" stroke="green"/>
      <line x1="0" y1="0" x2="5" y2="5" stroke="black"/>
      <path d="M0 0 L5 5" fill="none" stroke="black"/>
    </svg>'''
    outlines = svg.parse_svg(document)
    names = [o['name'] for o in outlines]
    assert names[:2] == ['box', 'dot'] and 'hidden' not in names, names
    box = outlines[0]
    assert box['fill'] == (1.0, 0x88 / 255, 0.0) and box['stroke'] == (0.0, 0.0, 0.0)
    assert box['stroke_width'] == 4.0, 'stroke width scales with the transform'
    corners = sorted({p for segment in box['segments'] for p in (segment[0], segment[3])})
    assert corners == sorted([(10.0, -20.0), (30.0, -20.0), (30.0, -30.0), (10.0, -30.0)]), corners
    dot = outlines[1]
    assert dot['fill'] == (0.0, 0.0, 1.0) and dot['dashed']
    records = svg.outline_records(dot['segments'])
    assert len(records) == 4 and all(kind == 'MIRRORED' for _, kind, _, _ in records)
    assert all(kind == 'SHARP' for _, kind, _, _ in svg.outline_records(box['segments']))
    # An open polyline is closed; a two-point path has no area and is dropped.
    assert len(svg.outline_records(outlines[2]['segments'])) == 3
    assert svg.outline_records(outlines[-1]['segments']) == []

    # --- into the board ---------------------------------------------------------------
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('SVG', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        shapes, skipped = import_svg_shapes(bpy.context, settings, document, (500.0, 500.0), 300.0)
        assert len(shapes) == 3 and skipped == 1, (len(shapes), skipped)  # <line> has no outline at all
        assert all(item.is_selected for item in shapes)
        box_shape, dot_shape, open_shape = shapes
        assert box_shape.name == 'box' and dot_shape.name == 'dot'
        assert tuple(round(c, 4) for c in box_shape.shape_fill_color) == (1.0, round(0x88 / 255, 4), 0.0)
        assert dot_shape.shape_line_style == 'DASHED'
        assert not open_shape.shape_show_fill and open_shape.shape_show_outline
        # Fit size: the larger side of the whole drawing is 300, centered on the point.
        xs = [x for item in shapes for x, _ in sg.outline(item)]
        ys = [y for item in shapes for _, y in sg.outline(item)]
        assert abs(max(max(xs) - min(xs), max(ys) - min(ys)) - 300.0) < 1.0
        # The circle stays a circle: every outline point at the same distance from its center.
        center = dot_shape.location
        radii = [math.dist(p, center) for p in sg.outline(dot_shape)]
        assert max(radii) - min(radii) < 0.01 * max(radii), (min(radii), max(radii))

        # Per-shape curve resolution.
        assert dot_shape.shape_curve_resolution == 16
        assert len(sg.outline(dot_shape)) == 4 * 16
        dot_shape.shape_curve_resolution = 4
        assert len(sg.outline(dot_shape)) == 4 * 4
        dot_shape.shape_curve_resolution = 16

        # Round trip: a curved shape saved and read back lands on the same outline.
        for item in list(settings.images):
            item.is_selected = False
        assert bpy.ops.kanvas.create_shape(kind='HEXAGON', location=(-300.0, 100.0),
                                           size=(200.0, 120.0)) == {'FINISHED'}
        hexagon = settings.images[-1]
        hexagon.rotation = 25.0
        set_vertex_type(hexagon, [0, 2], 'AUTO')
        set_vertex_type(hexagon, [3], 'FREE')
        hexagon.shape_vertices[3].handle_right = (0.2, -0.7)
        normalize_shape(hexagon)
        hexagon.shape_fill_color = (0.2, 0.4, 0.6)
        hexagon.text_lines.add().value = 'Hello <&>'
        before = sg.outline(hexagon)
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, 'hexagon.svg')
        assert bpy.ops.kanvas.export_shapes_svg(filepath=path) == {'FINISHED'}
        text = open(path, encoding='utf-8').read()
        assert 'Hello &lt;&amp;&gt;' in text and '#336699' in text and ' C ' in text

        records = sg.item_records(hexagon)
        handles = sg.effective_handles(records)
        points = [sg.unit_to_canvas(hexagon, p) for (co, _, _, _), (l, r) in zip(records, handles)
                  for p in (co, l, r)]
        middle = ((max(p[0] for p in points) + min(p[0] for p in points)) / 2,
                  (max(p[1] for p in points) + min(p[1] for p in points)) / 2)
        copies, _ = import_svg_shapes(bpy.context, settings, text, middle, 0.0)
        assert len(copies) == 1
        after = sg.outline(copies[0])
        assert len(after) == len(before), (len(after), len(before))
        assert all(any(close(a, b, 0.05) for b in after) for a in before), 'same outline'
        kinds = [v.handle_type for v in copies[0].shape_vertices]
        assert kinds.count('SHARP') == 6 - 3, kinds

        # The import operator reads a file; a broken file is reported, not raised.
        count = len(settings.images)
        assert bpy.ops.kanvas.import_shapes_svg(filepath=path, fit_size=False) == {'FINISHED'}
        assert len(settings.images) == count + 1
        broken = os.path.join(folder, 'broken.svg')
        open(broken, 'w', encoding='utf-8').write('<svg><path d="M0 0 L')
        # Run execute on a stand-in that records the report, so no error is printed.
        from types import SimpleNamespace
        from k_tools_kanvas.operators.ops_shape import KANVAS_OT_ImportShapesSVG
        reports = []
        stand_in = SimpleNamespace(filepath=broken, fit_size=True, size=400.0, group=True,
                                   report=lambda kind, message: reports.append((kind, message)))
        assert KANVAS_OT_ImportShapesSVG.execute(stand_in, bpy.context) == {'CANCELLED'}
        assert reports and reports[0][0] == {'ERROR'} and 'Could not read' in reports[0][1]
        assert len(settings.images) == count + 1, 'nothing added'
        empty = os.path.join(folder, 'empty.svg')
        open(empty, 'w', encoding='utf-8').write('<svg xmlns="http://www.w3.org/2000/svg"/>')
        assert bpy.ops.kanvas.import_shapes_svg(filepath=empty) == {'CANCELLED'}

        # Several outlines are grouped.
        count = len(settings.images)
        multi = os.path.join(folder, 'multi.svg')
        open(multi, 'w', encoding='utf-8').write(document)
        assert bpy.ops.kanvas.import_shapes_svg(filepath=multi) == {'FINISHED'}
        groups = [item for item in settings.images if item.item_type == 'FRAME' and item.frame_is_group]
        assert len(groups) == 1, 'groups are kept at the start of the list'
        members = [item for item in settings.images if item.parent_frame == groups[0].frame_node_name]
        assert len(members) == 3 and len(settings.images) == count + 4

        # Export needs a selected shape.
        for item in settings.images:
            item.is_selected = False
        assert not bpy.ops.kanvas.export_shapes_svg.poll()

    print('SVG SHAPES PASS')
finally:
    addon.unregister()
