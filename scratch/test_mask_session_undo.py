"""Check per-stroke modal history and cache invalidation after Blender Undo."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_mask import KANVAS_OT_PaintImageMask
from k_tools_kanvas.operators.ops_markup import _MarkupEditProxy
from k_tools_kanvas.utils.gpu import gpu_mask, gpu_markup


class Painter:
    _stamp = KANVAS_OT_PaintImageMask._stamp
    _history_region_id = KANVAS_OT_PaintImageMask._history_region_id
    _history_target = KANVAS_OT_PaintImageMask._history_target
    _history_push = KANVAS_OT_PaintImageMask._history_push
    _begin_stroke = KANVAS_OT_PaintImageMask._begin_stroke
    _commit_stroke = KANVAS_OT_PaintImageMask._commit_stroke
    _record_polygon = KANVAS_OT_PaintImageMask._record_polygon
    _history_step = KANVAS_OT_PaintImageMask._history_step
    _polygon_commit = KANVAS_OT_PaintImageMask._polygon_commit
    _polygon_cancel = KANVAS_OT_PaintImageMask._polygon_cancel
    _clear_line = KANVAS_OT_PaintImageMask._clear_line

    def __init__(self):
        self._history = []
        self._history_index = 0
        self._stroke_start_count = None
        self._stroke_region_id = None
        self._polygon_vertices = []
        self._alt_held = False
        self._area = SimpleNamespace(tag_redraw=lambda: None)


addon.register()
try:
    assert addon.refresh_kanvas_after_undo in bpy.app.handlers.undo_post
    assert addon.refresh_kanvas_after_undo in bpy.app.handlers.redo_post
    tree = bpy.data.node_groups.new('Mask session undo', 'KanvasNodeTree')
    item = tree.kanvas_settings.images.add()
    item.item_id = 'undo-image'
    item.item_type = 'IMAGE'
    item.image_data = bpy.data.images.new('Undo source', 64, 64)
    old = item.mask_dabs.add()
    old.uv = (0.1, 0.1)
    old.sequence = 1
    item.mask_next_sequence = 2
    painter = Painter()
    geometry = (4.0, (4 / 64, 0), (0, 4 / 64))

    painter._begin_stroke(item)
    for uv in ((0.2, 0.2), (0.25, 0.2), (0.3, 0.2)):
        painter._stamp(item, uv, geometry)
    painter._commit_stroke(item)
    assert len(painter._history) == 1 and len(item.mask_dabs) == 4
    painter._begin_stroke(item)
    painter._alt_held = True
    for uv in ((0.5, 0.5), (0.55, 0.5)):
        painter._stamp(item, uv, geometry)
    painter._commit_stroke(item)
    assert len(painter._history) == 2 and len(item.mask_dabs) == 6
    assert item.mask_dabs[-1].erase
    assert painter._history_step(item, redo=False)
    assert len(item.mask_dabs) == 4 and not item.mask_dabs[-1].erase
    assert painter._history_step(item, redo=True)
    assert len(item.mask_dabs) == 6 and item.mask_dabs[-1].erase
    assert painter._history_step(item, redo=False)
    painter._alt_held = False
    painter._begin_stroke(item)
    painter._stamp(item, (0.7, 0.7), geometry)
    painter._commit_stroke(item)
    assert len(painter._history) == 2 and not painter._history_step(item, redo=True)
    assert all(abs(value - 0.1) < 1e-6 for value in item.mask_dabs[0].uv)

    painter._polygon_vertices = [(0.2, 0.2), (0.8, 0.2), (0.5, 0.8)]
    assert painter._polygon_commit(item)
    assert len(item.mask_polygons) == 1 and len(painter._history) == 3
    assert painter._history_step(item, redo=False)
    assert not item.mask_polygons
    assert painter._history_step(item, redo=True)
    assert len(item.mask_polygons[0].vertices) == 3

    first = item.markup_regions.add()
    first.region_id = 'first'
    second = item.markup_regions.add()
    second.region_id = 'second'
    color_painter = Painter()
    item.markup_active_index = 0
    color_painter._begin_stroke(_MarkupEditProxy(item))
    color_painter._stamp(_MarkupEditProxy(item), (0.2, 0.2), geometry)
    color_painter._commit_stroke(_MarkupEditProxy(item))
    item.markup_active_index = 1
    color_painter._begin_stroke(_MarkupEditProxy(item))
    color_painter._stamp(_MarkupEditProxy(item), (0.8, 0.8), geometry)
    color_painter._commit_stroke(_MarkupEditProxy(item))
    assert color_painter._history_step(_MarkupEditProxy(item), redo=False)
    assert len(second.dabs) == 0 and len(first.dabs) == 1
    assert color_painter._history_step(_MarkupEditProxy(item), redo=False)
    assert len(first.dabs) == 0
    assert color_painter._history_step(_MarkupEditProxy(item), redo=True)
    assert len(first.dabs) == 1

    gpu_mask._mask_cache[('stale-mask',)] = {'texture': None}
    gpu_markup._markup_cache[('stale-color',)] = {'texture': None}
    addon.refresh_kanvas_after_undo(None)
    assert not gpu_mask._mask_cache and not gpu_markup._markup_cache
    assert not any(i.name.lstrip('.').startswith('Kanvas ') and 'Mask' in i.name
                   for i in bpy.data.images)
    print('MASK SESSION UNDO PASS')
finally:
    addon.unregister()
