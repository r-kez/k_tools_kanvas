"""Duplicating a selection copies every selected item, not only the active one."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Duplicate selection', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        for index, kind in enumerate(('RECTANGLE', 'TRIANGLE', 'DIAMOND')):
            assert bpy.ops.kanvas.create_shape(kind=kind, location=(index * 300, 0)) == {'FINISHED'}
        assert bpy.ops.kanvas.create_text(location=(900, 0)) == {'FINISHED'}
        original_ids = {item.item_id for item in settings.images}
        assert len(original_ids) == 4

        # Select all four and duplicate: four copies, all selected, none of the originals.
        for item in settings.images:
            item.is_selected = True
        assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
        assert len(settings.images) == 8
        copies = [item for item in settings.images if item.item_id not in original_ids]
        assert len(copies) == 4 and all(item.is_selected for item in copies)
        assert not any(item.is_selected for item in settings.images
                       if item.item_id in original_ids)
        assert settings.images[settings.active_image_index].item_id not in original_ids
        assert sorted(item.item_type for item in copies) == ['SHAPE', 'SHAPE', 'SHAPE', 'TEXT']
        assert len({item.name for item in settings.images}) == 8
        for copy in copies:
            if copy.item_type == 'SHAPE':
                assert len(copy.shape_vertices) >= 3, (copy.name, copy.shape_kind, len(copy.shape_vertices), [len(i.shape_vertices) for i in settings.images])

        # Locked items are skipped; a single selection still copies once.
        for item in settings.images:
            item.is_selected = False
        first, second = settings.images[0], settings.images[1]
        first.is_selected = second.is_selected = True
        second.is_locked = True
        second.is_selected = False
        count = len(settings.images)
        assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
        assert len(settings.images) == count + 1

    print('DUPLICATE SELECTION PASS')
finally:
    addon.unregister()
