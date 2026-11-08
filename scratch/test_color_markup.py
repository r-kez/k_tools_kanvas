"""Check named color regions, shared drawing data, duplication, and save/load."""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_markup import _MarkupEditProxy, _color_popup_region
from k_tools_kanvas.operators.ops_mask import KANVAS_OT_PaintImageMask, _mask_shortcut_rows
from k_tools_kanvas.keymap import UI_ACTIONS
from k_tools_kanvas.utils.gpu.gpu_markup import rasterize_markup, _region_masks
from k_tools_kanvas.utils.gpu.gpu_mask import rasterize_mask


addon.register()
try:
    # Mask and Markup are tabs of the Selection panel.
    from k_tools_kanvas.ui.tabs import TABS
    assert {'MASK', 'MARKUP'} <= set(TABS['image'])
    assert hasattr(bpy.types, 'KANVAS_UL_markup_regions')
    assert ('Color Mode', 'COLOR') in UI_ACTIONS
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Color Markup Test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    item = tree.kanvas_settings.images.add()
    item.item_id = 'color-markup-test'
    item.item_type = 'IMAGE'
    item.image_data = bpy.data.images.new('Color Markup source', 64, 64)
    item.is_selected = True
    tree.kanvas_settings.active_image_index = 0
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.add_markup_region() == {'FINISHED'}
        assert bpy.ops.kanvas.add_markup_region() == {'FINISHED'}
        assert bpy.ops.kanvas.edit_color_markup.poll()
        item.markup_editing = True
        assert bpy.ops.kanvas.add_markup_region.poll()
        assert bpy.ops.kanvas.add_markup_region_in_edit.poll()
        assert bpy.ops.kanvas.add_markup_region_in_edit() == {'FINISHED'}
        assert len(item.markup_regions) == 3 and item.markup_active_index == 2
        item.markup_editing = False
        assert bpy.ops.kanvas.remove_markup_region() == {'FINISHED'}
    assert len(item.markup_regions) == 2
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.edit_markup_color_popup.poll()
        assert (_color_popup_region(bpy.context, item.item_id,
                                    item.markup_regions[0].region_id)
                == item.markup_regions[0])
    shortcuts = _mask_shortcut_rows(_MarkupEditProxy(item), color_mode=True)
    assert ('Shift+C', 'Add color') in shortcuts
    assert ('Shift+E', 'Edit color') in shortcuts
    assert ('< / >', 'Previous / next color') in shortcuts
    assert ('C', 'Finish Color Mode') in shortcuts
    assert {entry.identifier for entry in item.bl_rna.properties['markup_tool'].enum_items} == {
        'BRUSH', 'POLYGON', 'RECTANGLE', 'AUTO'}
    item.markup_tool = 'RECTANGLE'
    assert ('Drag', 'Draw rectangle') in _mask_shortcut_rows(
        _MarkupEditProxy(item), color_mode=True)
    item.markup_tool = 'BRUSH'
    first, second = item.markup_regions[0], item.markup_regions[1]
    first.name = 'Body'
    first.color = (1.0, 0.0, 0.0)
    first.opacity = 0.5
    second.name = 'Handle'
    second.color = (0.0, 0.0, 1.0)
    second.opacity = 0.5
    for target, bounds in ((first, (0.1, 0.9)), (second, (0.3, 0.7))):
        polygon = target.polygons.add()
        polygon.sequence = 1
        low, high = bounds
        for uv in ((low, low), (high, low), (high, high), (low, high)):
            polygon.vertices.add().uv = uv
        target.next_sequence = 2
    rgba = rasterize_markup(item.markup_regions, 64, 64)
    assert abs(float(rgba[32, 32, 3]) - 0.75) < 1e-5
    assert abs(float(rgba[32, 32, 0]) - 0.25) < 1e-5
    assert abs(float(rgba[32, 32, 2]) - 0.5) < 1e-5
    second.visible = False
    assert abs(float(rasterize_markup(item.markup_regions, 64, 64)[32, 32, 3]) - 0.5) < 1e-5
    second.visible = True

    proxy = _MarkupEditProxy(item)
    painter = SimpleNamespace(_alt_held=False)
    KANVAS_OT_PaintImageMask._stamp(
        painter, proxy, (0.5, 0.5), (4.0, (4 / 64, 0), (0, 4 / 64)))
    assert len(second.dabs) == 1 and len(item.mask_dabs) == 0
    assert item.markup_revision >= 3
    painter._alt_held = True
    KANVAS_OT_PaintImageMask._stamp(
        painter, proxy, (0.5, 0.5), (4.0, (4 / 64, 0), (0, 4 / 64)))
    assert second.dabs[-1].erase and not item.markup_erase
    painter._alt_held = False
    painter._polygon_vertices = [(0.35, 0.35), (0.65, 0.35), (0.5, 0.65)]
    painter._polygon_cancel = lambda: painter._polygon_vertices.clear()
    painter._record_polygon = lambda item, polygon: None
    assert KANVAS_OT_PaintImageMask._polygon_commit(painter, proxy)
    assert len(second.polygons) == 2 and not painter._polygon_vertices
    painter._rectangle_start_uv = (0.8, 0.8)
    painter._rectangle_vertices = lambda target, end_uv, square, centered=False: (
        KANVAS_OT_PaintImageMask._rectangle_vertices(
            painter, target, end_uv, square, centered))
    assert KANVAS_OT_PaintImageMask._rectangle_commit(
        painter, proxy, (0.9, 0.95), square=True)
    assert len(second.polygons) == 3
    vertices = [tuple(vertex.uv) for vertex in second.polygons[-1].vertices]
    assert abs((vertices[1][0] - vertices[0][0])
               - (vertices[2][1] - vertices[1][1])) < 1e-6
    old_masks = _region_masks(item.markup_regions, 64, 64)
    first_mask = old_masks[0]['pixels']
    second.color = (0.0, 1.0, 0.0)
    reused_masks = _region_masks(item.markup_regions, 64, 64,
                                 {'region_masks': old_masks})
    assert reused_masks[0]['pixels'] is first_mask
    assert reused_masks[1]['pixels'] is old_masks[1]['pixels']
    extra = second.dabs.add()
    extra.uv = (0.6, 0.6)
    extra.radius_uv = (0.04, 0.04)
    extra.sequence = second.next_sequence
    second.next_sequence += 1
    second.revision += 1
    item.markup_revision += 1
    updated_masks = _region_masks(item.markup_regions, 64, 64,
                                  {'region_masks': reused_masks})
    assert updated_masks[0]['pixels'] is first_mask
    assert (updated_masks[1]['pixels'] == rasterize_mask(
        second.dabs, 64, 64, polygons=second.polygons)).all()
    shifted_masks = _region_masks((second,), 64, 64,
                                  {'region_masks': updated_masks})
    assert shifted_masks[0]['pixels'] is not first_mask
    assert (shifted_masks[0]['pixels'] == updated_masks[1]['pixels']).all()
    plain = SimpleNamespace(region_id='plain', revision=0,
                            dabs=[second.dabs[0]], polygons=[])
    plain_old = _region_masks((plain,), 64, 64)
    plain.dabs.append(second.dabs[1])
    plain.revision += 1
    plain_updated = _region_masks((plain,), 64, 64,
                                  {'region_masks': plain_old})
    assert (plain_updated[0]['pixels'] == rasterize_mask(
        plain.dabs, 64, 64)).all()
    expected_center = tuple(rasterize_markup(item.markup_regions, 64, 64)[32, 32])
    item.markup_tool = 'RECTANGLE'

    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
    copy = tree.kanvas_settings.images[1]
    assert copy.markup_tool == 'RECTANGLE'
    assert [part.name for part in copy.markup_regions] == ['Body', 'Handle']
    assert len(copy.markup_regions[1].dabs) == 3
    assert len(copy.markup_regions[1].polygons) == 3
    assert len(copy.markup_regions[0].polygons) == 1
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        path = Path(folder) / 'color_markup.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        loaded = bpy.data.node_groups['Color Markup Test'].kanvas_settings.images[0]
        assert loaded.markup_tool == 'RECTANGLE'
        assert [part.name for part in loaded.markup_regions] == ['Body', 'Handle']
        assert loaded.markup_regions[1].dabs[1].erase
        actual_center = rasterize_markup(loaded.markup_regions, 64, 64)[32, 32]
        assert all(abs(float(a) - float(b)) < 1e-5
                   for a, b in zip(actual_center, expected_center))
    print('COLOR MARKUP PASS')
finally:
    addon.unregister()
