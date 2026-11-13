"""Removing a checklist task removes its color, and removing the color removes the task."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Remove sync test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(part for part in area.regions if part.type == 'WINDOW')
    settings = tree.kanvas_settings

    card = settings.images.add()
    card.item_type, card.item_id, card.name, card.text_checklist = 'TEXT', 'card', 'List', True
    for line_id, value in (('a', 'Wall'), ('b', 'Roof'), ('c', 'Door')):
        line = card.text_lines.add()
        line.line_id, line.value = line_id, value
    images = []
    for index in range(2):
        image = settings.images.add()
        image.item_type, image.item_id, image.name = 'IMAGE', f'img{index}', f'Image {index}'
        image.image_data = bpy.data.images.new(f'pixels{index}', 16, 16)
        image.is_selected = True
        images.append(image)
    card.is_selected = True
    settings.active_image_index = 0

    def names(image):
        return [part.name for part in image.markup_regions]

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.associate_checklist() == {'FINISHED'}
        assert names(images[0]) == ['Wall', 'Roof', 'Door']

        # Task -> color, on every linked image.
        assert bpy.ops.kanvas.remove_text_line(index=1) == {'FINISHED'}
        assert [l.value for l in card.text_lines] == ['Wall', 'Door']
        assert names(images[0]) == ['Wall', 'Door'] and names(images[1]) == ['Wall', 'Door']

        # Color -> task.
        settings.active_image_index = list(settings.images).index(images[0])
        images[0].markup_active_index = 1
        assert bpy.ops.kanvas.remove_markup_region() == {'FINISHED'}
        assert [l.value for l in card.text_lines] == ['Wall'], [l.value for l in card.text_lines]
        assert names(images[0]) == ['Wall'] and names(images[1]) == ['Wall']

        # A plain color, linked to nothing, just goes.
        extra = images[0].markup_regions.add()
        extra.region_id, extra.name = 'x', 'Loose'
        images[0].markup_active_index = 1
        assert bpy.ops.kanvas.remove_markup_region() == {'FINISHED'}
        assert names(images[0]) == ['Wall'] and len(card.text_lines) == 1

        # The last task is emptied, not left to paint a nameless color.
        images[0].markup_active_index = 0
        assert bpy.ops.kanvas.remove_markup_region() == {'FINISHED'}
        assert len(card.text_lines) == 1 and card.text_lines[0].value == ''
        assert names(images[0]) == [] and names(images[1]) == []
    print('CHECKLIST REMOVE SYNC PASS')
finally:
    addon.unregister()
