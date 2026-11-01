"""Check polygon mask storage, draw order, duplication, and .blend persistence."""

from pathlib import Path
import sys
import tempfile

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_mask import rasterize_mask

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Polygon Mask Test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    item = tree.kanvas_settings.images.add()
    item.item_id = 'polygon-test'
    item.item_type = 'IMAGE'
    item.image_data = bpy.data.images.new('Polygon test pixels', 100, 100)
    item.is_selected = True
    item.mask_enabled = True
    item.mask_tool = 'POLYGON'
    polygon = item.mask_polygons.add()
    polygon.sequence = 1
    for uv in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)):
        polygon.vertices.add().uv = uv
    erase = item.mask_dabs.add()
    erase.sequence = 2
    erase.uv = (0.5, 0.5)
    erase.radius_uv = (0.1, 0.1)
    erase.erase = True
    pixels = rasterize_mask(item.mask_dabs, 100, 100, polygons=item.mask_polygons)
    assert pixels[50, 50] == 0 and pixels[50, 70] == 1 and pixels[10, 10] == 0
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        tree.kanvas_settings.active_image_index = 0
        assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
    copy = tree.kanvas_settings.images[1]
    assert len(copy.mask_polygons) == 1 and len(copy.mask_polygons[0].vertices) == 4
    assert copy.mask_tool == 'POLYGON'
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        path = Path(folder) / 'polygon.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        loaded = bpy.data.node_groups['Polygon Mask Test'].kanvas_settings.images[0]
        assert len(loaded.mask_polygons) == 1
        assert loaded.mask_tool == 'POLYGON'
        assert rasterize_mask(loaded.mask_dabs, 100, 100,
                              polygons=loaded.mask_polygons)[50, 50] == 0
    print('POLYGON MASK PASS')
finally:
    addon.unregister()
