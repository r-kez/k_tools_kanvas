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

        # --- Connecting arrows are copied with a duplicated diagram ------------------
        for item in settings.images:
            item.is_selected = False
        settings.images.clear()
        for index in range(3):
            assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(index * 300, 0)) == {'FINISHED'}
        a, b, c = [item.item_id for item in settings.images]
        a_item = settings.images[0]
        a_item.text_lines.add().line_id = 'line-a'

        def connect(start, end, **extra):
            arrow = settings.arrows.add()
            arrow.arrow_id = f'{start}-{end}'
            arrow.start_item_id, arrow.end_item_id = start, end
            arrow.start_uv, arrow.end_uv = (0.0, 0.5), (1.0, 0.5)
            arrow.label, arrow.thickness = 'edge', 4.0
            arrow.line_style, arrow.head_style = 'DASHED', 'BOTH'
            for name, value in extra.items():
                setattr(arrow, name, value)
            return arrow

        connect(a, b, start_line_id='line-a')   # both ends duplicated -> copied
        connect(b, c)                           # c is not duplicated  -> not copied
        loose = connect(a, '')                  # one loose end        -> not copied
        loose.arrow_id = 'loose'
        for item in settings.images:
            item.is_selected = item.item_id in (a, b)
        assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
        assert len(settings.arrows) == 4, [x.arrow_id for x in settings.arrows]
        new_a = next(i for i in settings.images if i.is_selected and i.item_id != b and i.item_id != a)
        new_arrow = settings.arrows[-1]
        assert new_arrow.arrow_id not in (f'{a}-{b}', f'{b}-{c}', 'loose')
        copied_ids = {i.item_id for i in settings.images if i.is_selected}
        assert {new_arrow.start_item_id, new_arrow.end_item_id} == copied_ids
        assert new_arrow.start_item_id != a and new_arrow.end_item_id != b
        assert tuple(new_arrow.start_uv) == (0.0, 0.5) and tuple(new_arrow.end_uv) == (1.0, 0.5)
        assert (new_arrow.label, new_arrow.thickness) == ('edge', 4.0)
        assert (new_arrow.line_style, new_arrow.head_style) == ('DASHED', 'BOTH')
        copied_a = next(i for i in settings.images if i.item_id == new_arrow.start_item_id)
        assert [l.line_id for l in copied_a.text_lines] == [new_arrow.start_line_id] \
            and new_arrow.start_line_id != 'line-a'
        assert new_arrow.name not in {x.name for x in settings.arrows if x != new_arrow}, 'new arrow gets a unique name'

    print('DUPLICATE SELECTION PASS')
finally:
    addon.unregister()
