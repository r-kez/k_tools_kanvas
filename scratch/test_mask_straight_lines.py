"""Headless checks for Shift-click and angle-constrained mask strokes."""

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_mask import (
    KANVAS_OT_PaintImageMask, snapped_line_endpoint,
)
from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv


class Painter:
    modal = KANVAS_OT_PaintImageMask.modal
    _shortcut_toggle_hit = KANVAS_OT_PaintImageMask._shortcut_toggle_hit
    _paint_to = KANVAS_OT_PaintImageMask._paint_to
    _paint_line = KANVAS_OT_PaintImageMask._paint_line
    _stamp = KANVAS_OT_PaintImageMask._stamp
    _clear_line = KANVAS_OT_PaintImageMask._clear_line
    _history_region_id = KANVAS_OT_PaintImageMask._history_region_id
    _history_target = KANVAS_OT_PaintImageMask._history_target
    _history_push = KANVAS_OT_PaintImageMask._history_push
    _begin_stroke = KANVAS_OT_PaintImageMask._begin_stroke
    _commit_stroke = KANVAS_OT_PaintImageMask._commit_stroke
    _history_step = KANVAS_OT_PaintImageMask._history_step

    def _item(self):
        return self.item

    def _mouse_uv(self, event, item):
        self._cursor_uv = event.uv
        return event.uv

    def _in_canvas(self, event):
        return True


def event(kind, uv, value='PRESS', shift=False):
    return SimpleNamespace(type=kind, value=value, uv=uv, shift=shift,
                           mouse_x=round(uv[0] * 1000), mouse_y=round(uv[1] * 1000),
                           alt=False, ctrl=False)


addon.register()
try:
    tree = bpy.data.node_groups.new('Straight mask strokes', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_id = 'straight-mask-image'
    item.item_type = 'IMAGE'
    item.image_data = bpy.data.images.new('Straight mask source', 200, 200)
    area = SimpleNamespace(tag_redraw=lambda: None)
    context = SimpleNamespace(area=area)
    painter = Painter()
    painter.item = item
    painter._area = area
    painter._cursor_uv = None
    painter._painting = False
    painter._last_uv = None
    painter._stroke_anchor_uv = None
    painter._line_press_uv = None
    painter._line_start_uv = None
    painter._line_preview_uv = None
    painter._line_press_mouse = None
    painter._line_dragging = False
    painter._nav_mode = None
    painter._stroke_start_count = None
    painter._stroke_region_id = None
    painter._history = []
    painter._history_index = 0

    painter.modal(context, event('LEFTMOUSE', (0.2, 0.5)))
    painter.modal(context, event('MOUSEMOVE', (0.25, 0.5)))
    painter.modal(context, event('LEFTMOUSE', (0.25, 0.5), 'RELEASE'))
    assert tuple(painter._stroke_anchor_uv) == (0.25, 0.5)

    before = len(item.mask_dabs)
    painter.modal(context, event('LEFTMOUSE', (0.7, 0.5), shift=True))
    assert len(item.mask_dabs) == before
    painter.modal(context, event('LEFTMOUSE', (0.7, 0.5), 'RELEASE', shift=True))
    assert len(item.mask_dabs) > before
    assert tuple(round(v, 4) for v in item.mask_dabs[before].uv) == (0.25, 0.5)
    assert tuple(round(v, 4) for v in item.mask_dabs[-1].uv) == (0.7, 0.5)
    assert tuple(painter._stroke_anchor_uv) == (0.7, 0.5)

    before = len(item.mask_dabs)
    painter.modal(context, event('LEFTMOUSE', (0.3, 0.3), shift=True))
    painter.modal(context, event('MOUSEMOVE', (0.65, 0.42), shift=True))
    assert len(item.mask_dabs) == before  # preview has no permanent marks
    assert painter._line_dragging
    assert abs(painter._line_preview_uv[1] - 0.3) < 1e-5
    painter.modal(context, event('LEFTMOUSE', (0.65, 0.42), 'RELEASE', shift=True))
    assert len(item.mask_dabs) > before
    assert abs(painter._stroke_anchor_uv[1] - 0.3) < 1e-5

    before = len(item.mask_dabs)
    painter.modal(context, event('LEFTMOUSE', (0.4, 0.4), shift=True))
    painter.modal(context, event('MOUSEMOVE', (0.6, 0.6), shift=True))
    assert painter.modal(context, event('ESC', (0.6, 0.6))) == {'RUNNING_MODAL'}
    assert len(item.mask_dabs) == before and painter._line_press_uv is None

    diagonal = snapped_line_endpoint(item, (0.5, 0.5), (0.65, 0.63))
    vertical = snapped_line_endpoint(item, (0.5, 0.5), (0.52, 0.8))
    assert abs((diagonal[0] - 0.5) - (diagonal[1] - 0.5)) < 1e-5
    assert abs(vertical[0] - 0.5) < 1e-5

    item.scale_xy = (1.5, 0.8)
    item.rotation = 23.0
    item.shear_xy = (0.12, -0.07)
    start_uv = (0.5, 0.5)
    end_uv = snapped_line_endpoint(item, start_uv, (0.7, 0.62))
    start = image_point_from_uv(item, start_uv)
    end = image_point_from_uv(item, end_uv)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    assert abs(angle / (math.pi / 4) - round(angle / (math.pi / 4))) < 1e-5
    print('MASK_STRAIGHT_LINES_OK')
finally:
    addon.unregister()
