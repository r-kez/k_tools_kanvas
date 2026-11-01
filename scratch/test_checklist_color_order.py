"""Checklist order and Color Markup order remain in sync."""

import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Checklist color order test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(part for part in area.regions if part.type == 'WINDOW')
    settings = tree.kanvas_settings
    card = settings.images.add()
    card.item_type = 'TEXT'
    card.item_id = 'checklist'
    card.text_checklist = True
    card.is_selected = True
    for name in 'ABC':
        line = card.text_lines.add()
        line.line_id = name
        line.value = name
    for index in range(2):
        image = settings.images.add()
        image.item_type = 'IMAGE'
        image.item_id = f'image-{index}'
        image.image_data = bpy.data.images.new(f'Order pixels {index}', 8, 8)
        image.is_selected = True
    settings.active_image_index = 0
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.associate_checklist() == {'FINISHED'}
    first, second = settings.images[1], settings.images[2]
    painted_id = first.markup_regions[1].region_id
    first.markup_regions[1].dabs.add().uv = (0.5, 0.5)
    manual = first.markup_regions.add()
    manual.region_id = 'manual'
    manual.name = 'Independent'
    first.markup_regions.move(3, 1)
    first.markup_active_index = 2  # Task B
    assert [part.name for part in first.markup_regions] == ['A', 'Independent', 'B', 'C']

    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.move_checklist_task(index=1, direction=-1) == {'FINISHED'}
    assert [line.value for line in card.text_lines] == ['B', 'A', 'C']
    assert [part.name for part in first.markup_regions] == ['B', 'Independent', 'A', 'C']
    assert [part.name for part in second.markup_regions] == ['B', 'A', 'C']
    assert first.markup_regions[first.markup_active_index].region_id == painted_id
    assert len(first.markup_regions[0].dabs) == 1

    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.sort_checklist(mode='ALPHA_ASC') == {'FINISHED'}
    assert [part.name for part in first.markup_regions] == ['A', 'Independent', 'B', 'C']
    assert [part.name for part in second.markup_regions] == ['A', 'B', 'C']

    settings.active_image_index = 1
    first.markup_active_index = 2  # Task B
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.move_markup_region(direction=1) == {'FINISHED'}
    assert [line.value for line in card.text_lines] == ['A', 'C', 'B']
    assert [part.name for part in first.markup_regions] == ['A', 'Independent', 'C', 'B']
    assert [part.name for part in second.markup_regions] == ['A', 'C', 'B']
    assert first.markup_regions[first.markup_active_index].region_id == painted_id

    first.markup_active_index = 1  # Independent color
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.move_markup_region(direction=1) == {'FINISHED'}
    assert [part.name for part in first.markup_regions] == ['A', 'C', 'Independent', 'B']
    assert [line.value for line in card.text_lines] == ['A', 'C', 'B']
    assert [part.name for part in second.markup_regions] == ['A', 'C', 'B']

    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        blend = str(Path(folder) / 'color_order.blend')
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        bpy.ops.wm.open_mainfile(filepath=blend)
        loaded = bpy.data.node_groups['Checklist color order test'].kanvas_settings
        assert [part.name for part in loaded.images[1].markup_regions] == [
            'A', 'C', 'Independent', 'B']
        assert len(next(part for part in loaded.images[1].markup_regions
                        if part.region_id == painted_id).dabs) == 1
    print('CHECKLIST COLOR ORDER PASS')
finally:
    addon.unregister()
