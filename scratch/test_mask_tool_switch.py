"""Exercise mask tool switching, polygon closure, and navigation events."""

import sys
import math
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_mask import (
    KANVAS_OT_PaintImageMask, _effective_mask_erase,
    _mask_indicator_text, _mask_shortcut_rows,
)
from k_tools_kanvas.operators.ops_modal import KANVAS_OT_Interact
from k_tools_kanvas.operators.ops_markup import _MarkupEditProxy, _add_region
from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv


class Painter:
    modal = KANVAS_OT_PaintImageMask.modal
    _sam_ready = lambda self, item: False   # Auto Select is not set up in this test
    _finish = KANVAS_OT_PaintImageMask._finish
    _clear_line = KANVAS_OT_PaintImageMask._clear_line
    _switch_tool = KANVAS_OT_PaintImageMask._switch_tool
    _polygon_cancel = KANVAS_OT_PaintImageMask._polygon_cancel
    _polygon_commit = KANVAS_OT_PaintImageMask._polygon_commit
    _polygon_target_uv = KANVAS_OT_PaintImageMask._polygon_target_uv
    _polygon_click = KANVAS_OT_PaintImageMask._polygon_click
    _rectangle_vertices = KANVAS_OT_PaintImageMask._rectangle_vertices
    _rectangle_commit = KANVAS_OT_PaintImageMask._rectangle_commit
    _rectangle_cancel = KANVAS_OT_PaintImageMask._rectangle_cancel
    _stamp = KANVAS_OT_PaintImageMask._stamp
    _paint_to = KANVAS_OT_PaintImageMask._paint_to
    _paint_line = KANVAS_OT_PaintImageMask._paint_line
    _history_region_id = KANVAS_OT_PaintImageMask._history_region_id
    _history_target = KANVAS_OT_PaintImageMask._history_target
    _history_push = KANVAS_OT_PaintImageMask._history_push
    _begin_stroke = KANVAS_OT_PaintImageMask._begin_stroke
    _commit_stroke = KANVAS_OT_PaintImageMask._commit_stroke
    _record_polygon = KANVAS_OT_PaintImageMask._record_polygon
    _history_step = KANVAS_OT_PaintImageMask._history_step

    def _item(self):
        return self.item

    def _window_region(self):
        return self.region

    def _in_canvas(self, event):
        return not getattr(event, 'outside', False)

    def _mouse_uv(self, event, item):
        self._cursor_uv = event.uv
        return event.uv

    def _pan_by(self, context, dx, dy):
        self.moves.append(('pan', dx, dy))

    def _zoom_view(self, context, direction):
        self.moves.append(('zoom', direction))

    def _zoom_from_drag(self, context, delta_y):
        self.moves.append(('drag_zoom', delta_y))


def event(kind, uv=(0.5, 0.5), value='PRESS', *, ctrl=False, shift=False,
          alt=False, outside=False, previous=None):
    x, y = round(uv[0] * 100), round(uv[1] * 100)
    px, py = previous if previous else (x, y)
    return SimpleNamespace(type=kind, value=value, uv=uv, ctrl=ctrl,
                           shift=shift, alt=alt, outside=outside,
                           mouse_x=x, mouse_y=y,
                           mouse_prev_x=px, mouse_prev_y=py)


addon.register()
try:
    tree = bpy.data.node_groups.new('Mask tool switching', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_id = 'mask-switch-image'
    item.item_type = 'IMAGE'
    item.image_data = bpy.data.images.new('Mask switch source', 100, 100)
    item.mask_enabled = True
    view = SimpleNamespace(view_to_region=lambda x, y, clip=False: (x + 50, y + 50))
    region = SimpleNamespace(x=0, y=0, width=100, height=100, view2d=view)
    area = SimpleNamespace(regions=(region,), tag_redraw=lambda: None)
    context = SimpleNamespace(area=area)
    painter = Painter()
    painter.item = item
    painter.region = region
    painter._area = area
    painter._tree = tree
    painter._draw_state = {'handler': None, 'tree': tree,
                           'item_id': item.item_id, 'painter': painter}
    painter._initial_mask_state = (0, True, item.mask_brush_size,
                                   item.mask_erase, item.mask_tool)
    painter._initial_counts = (len(item.mask_dabs), len(item.mask_polygons))
    painter._initial_next_sequence = item.mask_next_sequence
    painter._painting = False
    painter._nav_mode = None
    painter._nav_mouse = None
    painter._last_uv = None
    painter._cursor_uv = None
    painter._stroke_anchor_uv = None
    painter._line_press_uv = None
    painter._line_start_uv = None
    painter._line_preview_uv = None
    painter._line_dragging = False
    painter._line_press_mouse = None
    painter._polygon_vertices = []
    painter._polygon_cursor_uv = None
    painter._polygon_last_click = None
    painter._rectangle_start_uv = None
    painter._rectangle_end_uv = None
    painter._rectangle_press_mouse = None
    painter._rectangle_square = False
    painter._rectangle_centered = False
    painter._alt_held = False
    painter._held_alt_keys = set()
    painter._last_tool = 'BRUSH'
    painter._stroke_start_count = None
    painter._stroke_region_id = None
    painter._history = []
    painter._history_index = 0
    painter.moves = []
    key_context = SimpleNamespace(
        space_data=SimpleNamespace(type='NODE_EDITOR', edit_tree=tree),
        region=SimpleNamespace(type='WINDOW'))
    assert KANVAS_OT_Interact.poll(key_context)
    item.mask_editing = True
    assert not KANVAS_OT_Interact.poll(key_context)
    assert 'Brush' in _mask_indicator_text(item)
    assert 'Reveal' in _mask_indicator_text(item)
    assert _effective_mask_erase(item, True)
    assert 'Erase (Alt)' in _mask_indicator_text(item, alt_held=True)
    assert ('Tab', 'Next tool') in _mask_shortcut_rows(item)
    assert all(key and description for key, description in _mask_shortcut_rows(item))

    assert painter.modal(context, event('TAB')) == {'RUNNING_MODAL'}
    assert item.mask_tool == 'POLYGON'
    assert painter._polygon_cursor_uv == (0.5, 0.5)
    assert 'Polygon' in _mask_indicator_text(item)
    assert any('Double-click' in key for key, _ in _mask_shortcut_rows(item))
    item.mask_erase = True
    assert 'Erase' in _mask_indicator_text(item)
    assert 'Reveal (Alt)' in _mask_indicator_text(item, alt_held=True)
    assert len(_mask_shortcut_rows(item, compact=True)) < len(_mask_shortcut_rows(item))
    item.mask_erase = False
    for uv in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)):
        painter.modal(context, event('LEFTMOUSE', uv))
    assert len(painter._polygon_vertices) == 3
    assert painter.modal(context, event('LEFTMOUSE', (0.8, 0.8), 'DOUBLE_CLICK')) == {'RUNNING_MODAL'}
    assert len(item.mask_polygons) == 1
    assert len(item.mask_polygons[0].vertices) == 3
    assert not painter._polygon_vertices
    assert painter._history_index == 1
    painter.modal(context, event('Z', ctrl=True))
    assert len(item.mask_polygons) == 0 and painter._history_index == 0
    painter.modal(context, event('Z', ctrl=True, shift=True))
    assert len(item.mask_polygons) == 1 and painter._history_index == 1

    for uv in ((0.2, 0.2), (0.8, 0.2)):
        painter.modal(context, event('LEFTMOUSE', uv))
    painter.modal(context, event('LEFTMOUSE', (0.8, 0.8), 'DOUBLE_CLICK'))
    assert len(item.mask_polygons) == 2
    assert len(item.mask_polygons[1].vertices) == 3

    for uv in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)):
        painter.modal(context, event('LEFTMOUSE', uv))
    painter.modal(context, event('LEFTMOUSE', (0.8, 0.8)))
    assert len(item.mask_polygons) == 3
    assert len(item.mask_polygons[2].vertices) == 3

    painter.modal(context, event('LEFTMOUSE', (0.2, 0.2)))
    painter.modal(context, event('LEFTMOUSE', (0.8, 0.2)))
    painter.modal(context, event('MOUSEMOVE', (0.6, 0.43), shift=True))
    preview = painter._polygon_cursor_uv
    origin = image_point_from_uv(item, painter._polygon_vertices[-1])
    destination = image_point_from_uv(item, preview)
    assert abs(abs(destination[0] - origin[0]) - abs(destination[1] - origin[1])) < 1e-5
    painter.modal(context, event('LEFTMOUSE', (0.6, 0.43), shift=True))
    assert tuple(painter._polygon_vertices[-1]) == tuple(preview)
    painter.modal(context, event('RET'))
    assert len(item.mask_polygons) == 4

    for uv in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)):
        painter.modal(context, event('LEFTMOUSE', uv))
    painter.modal(context, event('LEFTMOUSE', (0.2, 0.2)))
    assert len(item.mask_polygons) == 5
    assert not painter._polygon_vertices

    for uv in ((0.2, 0.2), (0.8, 0.2)):
        painter.modal(context, event('LEFTMOUSE', uv))
    painter.modal(context, event('MIDDLEMOUSE', (0.5, 0.5)))
    painter.modal(context, event('MOUSEMOVE', (0.6, 0.6)))
    painter.modal(context, event('MIDDLEMOUSE', (0.6, 0.6), 'RELEASE'))
    painter.modal(context, event('WHEELUPMOUSE', (0.5, 0.5)))
    painter.modal(context, event('TRACKPADPAN', (0.6, 0.6), previous=(50, 50)))
    painter.modal(context, event('MIDDLEMOUSE', (0.5, 0.5), ctrl=True))
    painter.modal(context, event('MOUSEMOVE', (0.5, 0.65), ctrl=True))
    painter.modal(context, event('MIDDLEMOUSE', (0.5, 0.65), 'RELEASE', ctrl=True))
    assert len(painter._polygon_vertices) == 2
    assert any(move[0] == 'pan' for move in painter.moves)
    assert any(move[0] == 'zoom' for move in painter.moves)
    assert any(move[0] == 'drag_zoom' for move in painter.moves)

    assert painter.modal(context, event('TAB')) == {'RUNNING_MODAL'}
    assert item.mask_tool == 'RECTANGLE' and not painter._polygon_vertices
    assert painter._cursor_uv == (0.5, 0.5)
    painter.modal(context, event('LEFTMOUSE', (0.2, 0.2)))
    painter.modal(context, event('MOUSEMOVE', (0.7, 0.4), shift=True))
    assert len(painter._rectangle_vertices(item, painter._rectangle_end_uv, True)) == 4
    wide_source = SimpleNamespace(image_data=SimpleNamespace(size=(200, 100)))
    square = painter._rectangle_vertices(wide_source, painter._rectangle_end_uv, True)
    assert math.isclose(abs((square[1][0] - square[0][0]) * 200),
                        abs((square[2][1] - square[1][1]) * 100),
                        abs_tol=1e-5)
    centered = painter._rectangle_vertices(item, (0.4, 0.3), centered=True)
    expected = [(0.0, 0.1), (0.4, 0.1),
                (0.4, 0.3), (0.0, 0.3)]
    assert all(math.isclose(actual, desired, abs_tol=1e-6)
               for vertex, target in zip(centered, expected)
               for actual, desired in zip(vertex, target))
    centered_square = painter._rectangle_vertices(
        wide_source, (0.4, 0.3), square=True, centered=True)
    assert math.isclose((centered_square[1][0] - centered_square[0][0]) * 200,
                        (centered_square[2][1] - centered_square[1][1]) * 100,
                        abs_tol=1e-5)
    assert all(0 <= coordinate <= 1 for vertex in centered_square
               for coordinate in vertex)
    painter._rectangle_start_uv = (0.05, 0.06)
    edge_square = painter._rectangle_vertices(
        wide_source, (0.8, 0.7), square=True, centered=True)
    assert math.isclose((edge_square[0][0] + edge_square[2][0]) / 2,
                        0.05, abs_tol=1e-6)
    assert math.isclose((edge_square[0][1] + edge_square[2][1]) / 2,
                        0.06, abs_tol=1e-6)
    assert math.isclose((edge_square[1][0] - edge_square[0][0]) * 200,
                        (edge_square[2][1] - edge_square[1][1]) * 100,
                        abs_tol=1e-5)
    painter._rectangle_start_uv = (0.2, 0.2)
    painter.modal(context, event('LEFTMOUSE', (0.7, 0.4), 'RELEASE', shift=True))
    assert len(item.mask_polygons) == 6
    assert len(item.mask_polygons[-1].vertices) == 4
    painter.modal(context, event('Z', ctrl=True))
    assert len(item.mask_polygons) == 5
    painter.modal(context, event('Z', ctrl=True, shift=True))
    assert len(item.mask_polygons) == 6
    assert painter.modal(context, event('TAB')) == {'RUNNING_MODAL'}
    assert item.mask_tool == 'BRUSH'
    painter.modal(context, event('LEFTMOUSE', (0.5, 0.5)))
    painter.modal(context, event('LEFTMOUSE', (0.5, 0.5), 'RELEASE'))
    assert len(item.mask_dabs) >= 1
    brush_count = len(item.mask_dabs)
    painter.modal(context, event('Z', ctrl=True))
    assert len(item.mask_dabs) < brush_count
    painter.modal(context, event('Z', ctrl=True, shift=True))
    assert len(item.mask_dabs) == brush_count
    painter.modal(context, event('LEFT_ALT', alt=True))
    assert painter._alt_held and not item.mask_erase
    painter.modal(context, event('LEFTMOUSE', (0.4, 0.4), alt=True))
    painter.modal(context, event('LEFTMOUSE', (0.4, 0.4), 'RELEASE', alt=True))
    assert item.mask_dabs[-1].erase
    painter.modal(context, event('LEFT_ALT', value='RELEASE'))
    assert not painter._alt_held and not item.mask_erase
    painter.modal(context, event('LEFTMOUSE', (0.3, 0.3)))
    painter.modal(context, event('LEFTMOUSE', (0.3, 0.3), 'RELEASE'))
    assert not item.mask_dabs[-1].erase
    painter.modal(context, event('E'))
    assert item.mask_erase
    painter.modal(context, event('LEFT_ALT', alt=True))
    painter.modal(context, event('LEFTMOUSE', (0.6, 0.6), alt=True))
    painter.modal(context, event('LEFTMOUSE', (0.6, 0.6), 'RELEASE', alt=True))
    assert not item.mask_dabs[-1].erase
    painter.modal(context, event('LEFT_ALT', value='RELEASE'))
    assert item.mask_erase
    painter.modal(context, event('E'))
    assert not item.mask_erase
    item.mask_tool = 'POLYGON'  # Same change made by the sidebar radio control.
    painter.modal(context, event('MOUSEMOVE', (0.5, 0.5)))
    assert painter._last_tool == 'POLYGON'
    for uv in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)):
        painter.modal(context, event('LEFTMOUSE', uv))
    assert painter.modal(context, event('RET')) == {'RUNNING_MODAL'}
    assert len(item.mask_polygons) == 7
    painter.modal(context, event('LEFT_ALT', alt=True))
    for uv in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)):
        painter.modal(context, event('LEFTMOUSE', uv, alt=True))
    painter.modal(context, event('RET', alt=True))
    assert item.mask_polygons[-1].erase and not item.mask_erase
    painter.modal(context, event('LEFT_ALT', value='RELEASE'))
    for uv in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)):
        painter.modal(context, event('LEFTMOUSE', uv))
    painter.modal(context, event('RET'))
    assert not item.mask_polygons[-1].erase and not item.mask_erase
    painter.modal(context, event('LEFTMOUSE', (0.3, 0.3)))
    assert painter.modal(context, event('ESC')) == {'RUNNING_MODAL'}
    assert not painter._polygon_vertices
    assert len(item.mask_polygons) == 9
    item.mask_tool = 'RECTANGLE'
    painter.modal(context, event('MOUSEMOVE', (0.5, 0.5)))
    painter.modal(context, event('LEFTMOUSE', (0.5, 0.5), ctrl=True))
    painter.modal(context, event('MOUSEMOVE', (0.7, 0.6), ctrl=True))
    painter.modal(context, event('LEFT_CTRL', (0.7, 0.6), 'RELEASE'))
    assert not painter._rectangle_centered
    painter.modal(context, event('LEFT_CTRL', (0.7, 0.6), ctrl=True))
    assert painter._rectangle_centered
    painter.modal(context, event('LEFTMOUSE', (0.7, 0.6), 'RELEASE', ctrl=True))
    assert len(item.mask_polygons) == 10
    vertices = [tuple(vertex.uv) for vertex in item.mask_polygons[-1].vertices]
    assert math.isclose((vertices[0][0] + vertices[2][0]) / 2, 0.5, abs_tol=1e-6)
    assert math.isclose((vertices[0][1] + vertices[2][1]) / 2, 0.5, abs_tol=1e-6)
    assert painter.modal(context, event('M')) == {'FINISHED'}
    assert not item.mask_editing
    _add_region(item)
    color = _MarkupEditProxy(item)
    painter.item = color
    painter._last_tool = 'BRUSH'
    painter._history = []
    painter._history_index = 0
    assert painter.modal(context, event('TAB')) == {'RUNNING_MODAL'}
    assert item.markup_tool == 'POLYGON'
    assert painter.modal(context, event('TAB')) == {'RUNNING_MODAL'}
    assert item.markup_tool == 'RECTANGLE'
    painter.modal(context, event('LEFTMOUSE', (0.5, 0.5), ctrl=True, shift=True))
    painter.modal(context, event('MOUSEMOVE', (0.7, 0.6), ctrl=True, shift=True))
    painter.modal(context, event('LEFTMOUSE', (0.7, 0.6), 'RELEASE', ctrl=True, shift=True))
    assert len(item.markup_regions[0].polygons) == 1
    color_vertices = [tuple(vertex.uv) for vertex in item.markup_regions[0].polygons[0].vertices]
    assert math.isclose((color_vertices[0][0] + color_vertices[2][0]) / 2,
                        0.5, abs_tol=1e-6)
    assert math.isclose((color_vertices[0][1] + color_vertices[2][1]) / 2,
                        0.5, abs_tol=1e-6)
    assert math.isclose(color_vertices[1][0] - color_vertices[0][0],
                        color_vertices[2][1] - color_vertices[1][1], abs_tol=1e-6)
    painter.modal(context, event('Z', ctrl=True))
    assert len(item.markup_regions[0].polygons) == 0
    painter.modal(context, event('Z', ctrl=True, shift=True))
    assert len(item.markup_regions[0].polygons) == 1
    assert painter.modal(context, event('TAB')) == {'RUNNING_MODAL'}
    assert item.markup_tool == 'BRUSH'
    print('MASK TOOL SWITCH PASS')
finally:
    addon.unregister()
