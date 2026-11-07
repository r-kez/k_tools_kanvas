"""Connect Selected: arrows between the facing sides of shapes, images and cards."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.arrow_geometry import endpoint, facing_anchors, side_midpoints

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Connect', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        kinds = ('RECTANGLE', 'DIAMOND', 'ELLIPSE', 'TRIANGLE')
        for kind, location in zip(kinds, ((0, 0), (600, 0), (0, -500), (600, 500))):
            assert bpy.ops.kanvas.create_shape(kind=kind, location=location) == {'FINISHED'}
        rect, diamond, ellipse, triangle = list(settings.images)

        # Side by side: the right side of the first meets the left side of the second.
        (uv_a, point_a), (uv_b, point_b) = facing_anchors(rect, diamond)
        assert uv_a == (1.0, 0.5) and uv_b == (0.0, 0.5), (uv_a, uv_b)   # diamond's left tip
        assert point_a[0] < point_b[0]
        # Stacked: the bottom of the upper item meets the top of the lower one.
        (uv_a, _), (uv_b, _) = facing_anchors(ellipse, rect)
        assert uv_a[1] > uv_b[1] or abs(uv_a[1] - 1.0) < 1e-6 or abs(uv_b[1] - 0.0) < 1e-6
        assert len(side_midpoints(rect)) == 4 and len(side_midpoints(ellipse)) == 8
        assert len(side_midpoints(triangle)) == 6, 'three corners and three edge middles'

        # Nothing selected, or one item: refuse without touching the board.
        for item in settings.images:
            item.is_selected = False
        assert bpy.ops.kanvas.connect_items() == {'CANCELLED'}
        rect.is_selected = True
        assert bpy.ops.kanvas.connect_items() == {'CANCELLED'} and len(settings.arrows) == 0

        # Two items: one arrow attached to both, ending exactly on the chosen sides.
        diamond.is_selected = True
        assert bpy.ops.kanvas.connect_items() == {'FINISHED'}
        arrow = settings.arrows[0]
        assert (arrow.start_item_id, arrow.end_item_id) == (rect.item_id, diamond.item_id)
        assert tuple(arrow.start_uv) == (1.0, 0.5) and tuple(arrow.end_uv) == (0.0, 0.5)
        start, end = endpoint(settings, arrow, 'start'), endpoint(settings, arrow, 'end')
        assert abs(start[0] - point_a[0]) < 1e-4 and abs(end[0] - point_b[0]) < 1e-4

        # The same pair is not connected twice.
        assert bpy.ops.kanvas.connect_items() == {'CANCELLED'} and len(settings.arrows) == 1

        # Three or more are chained in list order, reusing the pair that already exists.
        for item in (ellipse, triangle):
            item.is_selected = True
        assert bpy.ops.kanvas.connect_items() == {'FINISHED'}
        assert len(settings.arrows) == 3
        chain = [(a.start_item_id, a.end_item_id) for a in settings.arrows]
        assert chain[1:] == [(diamond.item_id, ellipse.item_id), (ellipse.item_id, triangle.item_id)]

        # A moved shape drags its arrow end along.
        before = endpoint(settings, settings.arrows[0], 'end')
        diamond.location = (diamond.location[0] + 100.0, diamond.location[1])
        after = endpoint(settings, settings.arrows[0], 'end')
        assert abs(after[0] - before[0] - 100.0) < 1e-4

    print('CONNECT ITEMS PASS')
finally:
    addon.unregister()
