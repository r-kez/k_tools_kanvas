"""Linking a checklist to an image that already has colors: the colors become tasks."""

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
    tree = bpy.data.node_groups.new('Adopt test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(part for part in area.regions if part.type == 'WINDOW')
    settings = tree.kanvas_settings

    card = settings.images.add()
    card.item_type, card.item_id, card.name, card.text_checklist = 'TEXT', 'card', 'List', True
    line = card.text_lines.add()
    line.line_id, line.value = 'task-wall', 'Wall'          # has no color of its own
    line = card.text_lines.add()
    line.line_id, line.value = 'task-door', 'Door'
    line.color = (0.1, 0.2, 0.3)

    image = settings.images.add()
    image.item_type, image.item_id, image.name = 'IMAGE', 'img', 'Image'
    image.image_data = bpy.data.images.new('pixels', 16, 16)
    image.is_selected = True
    for name, color in (('Wall', (0.9, 0.1, 0.1)), ('Roof', (0.1, 0.9, 0.1)),
                        ('Door', (0.5, 0.5, 0.5))):
        part = image.markup_regions.add()
        part.region_id, part.name, part.color = 'r-' + name, name, color
    card.is_selected = True
    settings.active_image_index = 0

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.associate_checklist() == {'FINISHED'}
    values = [line.value for line in card.text_lines]
    assert values == ['Wall', 'Door', 'Roof'], values            # Roof added, others joined
    roof = card.text_lines[2]
    assert tuple(round(v, 3) for v in roof.color) == (0.1, 0.9, 0.1), tuple(roof.color)
    wall = card.text_lines[0]
    assert tuple(round(v, 3) for v in wall.color) == (0.9, 0.1, 0.1), 'Wall took the paint color'
    assert len(image.markup_regions) == 3
    assert {part.name: part.checklist_line_id for part in image.markup_regions} == {
        'Wall': 'task-wall', 'Door': 'task-door', 'Roof': roof.line_id}
    print('CHECKLIST ADOPT PASS')
finally:
    addon.unregister()
