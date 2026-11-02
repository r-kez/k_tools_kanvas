"""Arrows attach to shapes at corners, side middles, the outline, or anywhere inside."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_arrow import _create_arrow
from k_tools_kanvas.operators.ops_shape import normalize_shape
from k_tools_kanvas.utils.arrow_geometry import (anchor_candidate, detach_item_anchors,
                                                 endpoint, set_endpoint)

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Arrow shapes', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    def close(a, b, tol=1e-4):
        return math.dist(a, b) < tol

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 50.0),
                                           size=(200.0, 100.0)) == {'FINISHED'}
        shape = settings.images[0]            # box (0, 0) to (200, 100)
        arrow = _create_arrow(settings, (0.0, 0.0))

        # A corner: snaps within the radius and reports the corner's box position.
        candidate = anchor_candidate(settings, (205.0, 104.0), 1.0)
        assert candidate and candidate[0] == shape.item_id
        assert close(candidate[2], (200.0, 100.0)) and close(candidate[1], (1.0, 1.0))

        # The middle of a side.
        candidate = anchor_candidate(settings, (101.0, -3.0), 1.0)
        assert close(candidate[2], (100.0, 0.0)) and close(candidate[1], (0.5, 0.0))

        # Near the outline but not on an anchor: attaches to the nearest outline point.
        candidate = anchor_candidate(settings, (50.0, 6.0), 1.0)
        assert candidate and close(candidate[2], (50.0, 0.0)), candidate

        # Anywhere inside: attaches exactly where the point is.
        candidate = anchor_candidate(settings, (60.0, 40.0), 1.0)
        assert candidate and close(candidate[2], (60.0, 40.0)) and close(candidate[1], (0.3, 0.4))

        # Outside everything: no anchor.
        assert anchor_candidate(settings, (400.0, 400.0), 1.0) is None

        # The attached end follows the shape through every transform.
        set_endpoint(arrow, 'end', candidate[2], candidate)
        assert close(endpoint(settings, arrow, 'end'), (60.0, 40.0)), (endpoint(settings, arrow, 'end'), tuple(arrow.end_uv), arrow.end_item_id, candidate, shape.location, shape.shape_width)
        shape.location = (300.0, 250.0)
        assert close(endpoint(settings, arrow, 'end'), (260.0, 240.0))
        shape.location = (100.0, 50.0)
        shape.scale_master = 2.0
        assert close(endpoint(settings, arrow, 'end'), (20.0, 30.0)), endpoint(settings, arrow, 'end')
        shape.scale_master = 1.0
        shape.shape_width = 400.0                      # resized: the end keeps its place in the box
        assert close(endpoint(settings, arrow, 'end'), (100.0 - 200.0 + 0.3 * 400.0, 40.0))
        shape.shape_width = 200.0
        shape.rotation = 90.0                          # turns around the center
        assert close(endpoint(settings, arrow, 'end'), (100.0 - (40.0 - 50.0), 50.0 + (60.0 - 100.0)))
        shape.rotation = 0.0

        # A snapped corner stays on the corner when the shape kind changes box shape.
        corner = anchor_candidate(settings, (0.0, 0.0), 1.0)
        set_endpoint(arrow, 'start', corner[2], corner)
        shape.location = (500.0, 500.0)
        assert close(endpoint(settings, arrow, 'start'), (400.0, 450.0))
        shape.location = (100.0, 50.0)

        # Editing a vertex refits the box; the ends stay where they were on the canvas.
        before_start = endpoint(settings, arrow, 'start')
        before_end = endpoint(settings, arrow, 'end')
        shape.shape_kind = 'POLYGON'
        shape.shape_vertices[2].co = (1.0, 0.5)    # pull the top-right corner out
        normalize_shape(shape)
        assert close(endpoint(settings, arrow, 'start'), before_start, 1e-4)
        assert close(endpoint(settings, arrow, 'end'), before_end, 1e-4)

        # Ellipses offer eight snap points; a triangle offers corners and side middles.
        assert len(__import__('k_tools_kanvas.utils.shape_geometry', fromlist=['x']).anchor_points(shape)) == 8
        assert bpy.ops.kanvas.create_shape(kind='ELLIPSE', location=(900.0, 0.0)) == {'FINISHED'}
        ellipse = settings.images[-1]
        from k_tools_kanvas.utils import shape_geometry as sg
        assert len(sg.anchor_points(ellipse)) == 8
        assert bpy.ops.kanvas.create_shape(kind='TRIANGLE', location=(1500.0, 0.0)) == {'FINISHED'}
        assert len(sg.anchor_points(settings.images[-1])) == 6

        # Deleting the shape leaves the arrow where it was.
        stay = endpoint(settings, arrow, 'end')
        detach_item_anchors(settings, shape.item_id)
        assert close(endpoint(settings, arrow, 'end'), stay)
        assert arrow.end_item_id == ''

    print('ARROW SHAPES PASS')
finally:
    addon.unregister()
