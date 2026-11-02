"""Shapes: presets, kind switching, vertex editing, frames and the draw gesture."""

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.operators.ops_shape import new_shape, normalize_shape
from k_tools_kanvas.properties import set_shape_vertices
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.item_geometry import item_bounds, shape_draw_indices


class View:
    def region_to_view(self, x, y):
        return (x, y)

    def view_to_region(self, x, y, clip=False):
        return (x, y)


def area_of(triangles):
    return sum(abs(sg.signed_area(list(t))) for t in triangles)


addon.register()
try:
    tree = bpy.data.node_groups.new('Shapes test', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    context = SimpleNamespace(
        area=SimpleNamespace(tag_redraw=lambda: None),
        region=SimpleNamespace(view2d=View()),
        space_data=SimpleNamespace(edit_tree=tree),
    )

    # Every preset fills the unit box and triangulates to its own area.
    for kind, label, _, _ in sg.KINDS:
        if kind == 'POLYGON':
            continue
        vertices = sg.preset_vertices(kind)
        xs, ys = [v[0] for v in vertices], [v[1] for v in vertices]
        assert abs(min(xs) + 0.5) < 1e-6 and abs(max(xs) - 0.5) < 1e-6, kind
        assert abs(min(ys) + 0.5) < 1e-6 and abs(max(ys) - 0.5) < 1e-6, kind
        assert abs(area_of(sg.triangulate(vertices)) - abs(sg.signed_area(vertices))) < 1e-6, kind

    shape = new_shape(context, settings, 'RECTANGLE', (100.0, 50.0), 200.0, 100.0)
    assert shape.item_type == 'SHAPE' and shape.is_selected
    assert settings.active_image_index == 0 and len(shape.shape_vertices) == 4
    assert item_bounds(shape) == (0.0, 0.0, 200.0, 100.0)
    assert shape_draw_indices(settings) == [0]

    # Hit testing: filled shapes are picked inside, outline-only shapes only on the line.
    assert sg.hit_shape(shape, (100.0, 50.0), 2.0)
    assert not sg.hit_shape(shape, (300.0, 50.0), 2.0)
    shape.shape_show_fill = False
    assert not sg.hit_shape(shape, (100.0, 50.0), 2.0)
    assert sg.hit_shape(shape, (1.0, 50.0), 2.0)
    shape.shape_show_fill = True

    # Rotation and scale move the bounds; 90 degrees swaps width and height.
    shape.rotation = 90.0
    left, bottom, right, top = item_bounds(shape)
    assert abs((right - left) - 100.0) < 1e-6 and abs((top - bottom) - 200.0) < 1e-6
    shape.rotation = 0.0
    shape.scale_master = 2.0
    assert item_bounds(shape) == (-100.0, -50.0, 300.0, 150.0)
    shape.scale_master = 1.0

    # Switching the kind rebuilds the vertices inside the same box.
    shape.shape_kind = 'TRIANGLE'
    assert len(shape.shape_vertices) == 3
    shape.shape_kind = 'ELLIPSE'
    assert len(shape.shape_vertices) == sg.ELLIPSE_SEGMENTS
    shape.shape_kind = 'STAR'
    assert len(shape.shape_vertices) == 10
    assert item_bounds(shape) == (0.0, 0.0, 200.0, 100.0)
    shape.shape_kind = 'RECTANGLE'

    # Editing a vertex turns the shape into a polygon; the box follows the vertices.
    shape.shape_edit_vertices = True
    shape.shape_kind = 'POLYGON'
    assert len(shape.shape_vertices) == 4, 'Polygon keeps the current vertices'
    shape.shape_vertices[2].co = (1.0, 0.5)   # top-right corner pushed outward
    normalize_shape(shape)
    left, bottom, right, top = item_bounds(shape)
    assert abs(left - 0.0) < 1e-6 and abs(bottom - 0.0) < 1e-6, (left, bottom)
    assert abs(right - 300.0) < 1e-6 and abs(top - 100.0) < 1e-6, (right, top)
    xs = [v.co[0] for v in shape.shape_vertices]
    assert abs(min(xs) + 0.5) < 1e-6 and abs(max(xs) - 0.5) < 1e-6

    # Edge hits report the edge and the position along it.
    hit = sg.hit_edge(shape, (125.0, 1.0), 3.0)
    assert hit is not None and hit[0] == 0, hit
    assert sg.hit_vertex(shape, (0.0, 0.0), 3.0) == 0

    # The draw gesture: a drag defines the box, Shift squares it, Ctrl draws from the center.
    helper = KanvasInteractionHelpers()
    helper.keyboard_transform = False
    helper._start_shape_draw(context, settings, 'DIAMOND', (400.0, 400.0))
    drawn = helper._shape_target(settings)
    assert drawn.shape_kind == 'DIAMOND' and helper.drag_mode == 'SHAPE_DRAW'
    helper._update_shape_gesture(settings, 500.0, 460.0, False, False)
    assert (drawn.shape_width, drawn.shape_height) == (100.0, 60.0)
    assert tuple(drawn.location) == (450.0, 430.0)
    helper._update_shape_gesture(settings, 500.0, 460.0, True, False)
    assert drawn.shape_width == drawn.shape_height == 100.0
    helper._update_shape_gesture(settings, 500.0, 460.0, False, True)
    assert (drawn.shape_width, drawn.shape_height) == (200.0, 120.0)
    assert tuple(drawn.location) == (400.0, 400.0)
    helper._finish_shape_gesture(context, settings)
    assert helper.drag_mode == 'NONE' and drawn.is_selected

    # A click without a drag creates the default size, centered on the click.
    helper._start_shape_draw(context, settings, 'HEXAGON', (0.0, -300.0))
    clicked = helper._shape_target(settings)
    helper._finish_shape_gesture(context, settings)
    assert (clicked.shape_width, clicked.shape_height) == sg.DEFAULT_SIZE
    assert tuple(clicked.location) == (0.0, -300.0)

    # Escape removes the shape that was being drawn.
    count = len(settings.images)
    helper._start_shape_draw(context, settings, 'STAR', (900.0, 900.0))
    assert len(settings.images) == count + 1
    helper._cancel_shape_gesture(context, settings)
    assert len(settings.images) == count and settings.active_image_index == -1

    # Vertex drag, cancel restores the exact start; finish keeps the edit.
    target = settings.images[0]
    target.is_selected = True
    settings.active_image_index = 0
    helper.drag_mode = 'SHAPE_VERTEX'
    helper.shape_target_id = target.item_id
    helper.shape_vertex_index = 1
    before = [tuple(v.co) for v in target.shape_vertices]
    helper.shape_vertex_start = (target.shape_kind, before)
    helper._update_shape_gesture(settings, 250.0, -50.0, False, False)
    assert [tuple(v.co) for v in target.shape_vertices] != before
    helper._cancel_shape_gesture(context, settings)
    assert [tuple(v.co) for v in target.shape_vertices] == before

    # Shapes live in frames like any other item.
    from k_tools_kanvas.utils.gpu import (can_attach_to_frame, get_frame, update_frame_bounds)
    frame = settings.images.add()
    frame.item_type = 'FRAME'
    frame.item_id = 'frame-1'
    frame.frame_node_name = 'frame-1'
    frame.location = (-500.0, 500.0)
    assert can_attach_to_frame(settings, shape, 'frame-1')
    shape.parent_frame = 'frame-1'
    update_frame_bounds(tree, settings, 'frame-1')
    f = get_frame(settings, 'frame-1')
    assert f.location[0] < 0 and f.frame_width >= 250.0

    # Polygon drawn click by click, with a live preview.
    from k_tools_kanvas.operators.ops_shape import PolygonSession, constrain_to_45
    count = len(settings.images)
    session = PolygonSession()
    session.add_point(context, settings, (600.0, 600.0))
    live = session.item(settings)
    assert len(settings.images) == count + 1 and live.shape_kind == 'POLYGON'
    session.move(settings, (700.0, 600.0))
    assert len(live.shape_vertices) == 2          # placed point + the point under the cursor
    session.add_point(context, settings, (700.0, 600.0))
    session.add_point(context, settings, (700.0, 700.0))
    session.move(settings, (600.0, 700.0))
    assert len(live.shape_vertices) == 4 and not session.can_close() is False
    assert session.remove_last(settings) and len(session.points) == 2
    session.add_point(context, settings, (700.0, 700.0))
    session.add_point(context, settings, (600.0, 700.0))
    assert session.finish(context, settings)
    assert len(live.shape_vertices) == 4 and not live.shape_edit_vertices
    assert item_bounds(live) == (600.0, 600.0, 700.0, 700.0)
    assert live.shape_kind == 'POLYGON'

    # Fewer than three vertices is not a polygon: it is dropped.
    count = len(settings.images)
    short = PolygonSession()
    short.add_point(context, settings, (0.0, 900.0))
    short.add_point(context, settings, (50.0, 900.0))
    assert not short.finish(context, settings) and len(settings.images) == count

    # Escape removes the polygon in progress; Shift snaps to 45 degree steps.
    cancelled = PolygonSession()
    cancelled.add_point(context, settings, (0.0, 900.0))
    cancelled.cancel(settings)
    assert len(settings.images) == count
    x, y = constrain_to_45((0.0, 0.0), (10.0, 3.0))
    assert abs(y) < 1e-9 and x > 10.0
    x, y = constrain_to_45((0.0, 0.0), (10.0, 9.0))
    assert abs(x - y) < 1e-9

    # Fill and outline are never both off.
    shape.shape_show_outline = True
    shape.shape_show_fill = False
    shape.shape_show_outline = False
    assert shape.shape_show_outline and not shape.shape_show_fill
    shape.shape_show_outline = False
    shape.shape_show_fill = True
    shape.shape_show_fill = False
    assert shape.shape_show_outline
    shape.shape_show_fill = True

    # Copy-friendly: the item search finds text typed inside a shape.
    from k_tools_kanvas.utils.item_search import item_matches
    shape = settings.images[0]
    shape.text_body = 'Door width'
    assert item_matches(shape, 'door') and not item_matches(shape, 'window')

    # The GPU module imports and its geometry helpers work without a window.
    from k_tools_kanvas.utils.gpu import gpu_shape
    assert gpu_shape._outline_strokes(sg.outline(shape), 'SOLID', 3.0)
    assert gpu_shape._outline_strokes(sg.outline(shape), 'DASHED', 3.0)
    print('shapes ok')
finally:
    addon.unregister()
