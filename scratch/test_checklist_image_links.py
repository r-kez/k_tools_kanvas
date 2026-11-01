"""Checklist to image association and task color persistence."""

import sys
import tempfile
from pathlib import Path

import bpy
import gpu
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_checklist import sync_checklist_regions
from k_tools_kanvas.utils.gpu.gpu_checklist import (
    _append_soft_line, _boundary_point, draw_checklist_links,
)
from k_tools_kanvas.ui.markup_list import checklist_task_done


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Checklist links test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(part for part in area.regions if part.type == 'WINDOW')
    settings = tree.kanvas_settings

    card = settings.images.add()
    card.item_type = 'TEXT'
    card.item_id = 'card-a'
    card.name = 'Review'
    card.text_checklist = True
    card.location = (0, 0)
    for line_id, value in (('task-a', 'Wall'), ('task-b', 'Window')):
        line = card.text_lines.add()
        line.line_id = line_id
        line.value = value
    for index in range(2):
        image = settings.images.add()
        image.item_type = 'IMAGE'
        image.item_id = f'image-{index}'
        image.name = f'Image {index}'
        image.image_data = bpy.data.images.new(f'Test pixels {index}', 16, 16)
        image.location = (300, index * 250)
        image.is_selected = True
    card.is_selected = True
    settings.active_image_index = 0

    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.associate_checklist.poll()
        assert bpy.ops.kanvas.associate_checklist() == {'FINISHED'}
    for image in list(settings.images)[1:]:
        assert len(image.checklist_associations) == 1
        assert image.checklist_associations[0].card_id == card.item_id
        assert [part.name for part in image.markup_regions] == ['Wall', 'Window']
        assert [part.checklist_line_id for part in image.markup_regions] == ['task-a', 'task-b']
        assert not checklist_task_done(image, image.markup_regions[0])
    card.text_lines[0].done = True
    assert checklist_task_done(settings.images[1], settings.images[1].markup_regions[0])
    assert not checklist_task_done(settings.images[1], settings.images[1].markup_regions[1])
    card.text_lines[0].done = False
    assert _boundary_point((-10, -10, 10, 10), (100, 0)) == (10, 0)
    vertices, colors = [], []
    _append_soft_line(vertices, colors, (0, 0), (100, 20),
                      (0.28, 0.74, 1.0, 0.75), 1.0)
    assert len(vertices) == len(colors) == 18
    assert any(color[3] == 0.0 for color in colors)
    assert any(color[3] == 0.75 for color in colors)
    gpu.init()
    offscreen = gpu.types.GPUOffScreen(512, 512)
    try:
        with offscreen.bind():
            gpu.matrix.push_projection()
            try:
                gpu.matrix.load_projection_matrix(Matrix((
                    (2 / 512, 0, 0, -1), (0, 2 / 512, 0, -1),
                    (0, 0, 1, 0), (0, 0, 0, 1),
                )))
                draw_checklist_links(settings)
            finally:
                gpu.matrix.pop_projection()
    finally:
        offscreen.free()

    first = settings.images[1]
    card.text_lines[0].color = (0.1, 0.2, 0.3)
    assert all(abs(actual - expected) < 1e-5 for actual, expected in
               zip(settings.images[2].markup_regions[0].color, (0.1, 0.2, 0.3)))
    dab = first.markup_regions[0].dabs.add()
    dab.uv = (0.5, 0.5)
    painted_first_id = first.markup_regions[0].region_id
    card.text_lines[0].value = 'Wall revised'
    assert first.markup_regions[0].name == 'Wall revised'
    card.text_lines.move(0, 1)
    assert not checklist_task_done(first, first.markup_regions[0])
    sync_checklist_regions(settings, first)
    painted_first = next(part for part in first.markup_regions
                         if part.region_id == painted_first_id)
    assert painted_first.name == 'Wall revised'
    assert len(painted_first.dabs) == 1
    assert all(abs(actual - expected) < 1e-5 for actual, expected in
               zip(painted_first.color, (0.1, 0.2, 0.3)))

    line = card.text_lines.add()
    line.line_id = 'task-c'
    line.value = 'Door'
    sync_checklist_regions(settings, first)
    assert len(first.markup_regions) == 3
    assert first.markup_regions[-1].checklist_line_id == 'task-c'
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.remove_text_line(index=2) == {'FINISHED'}
    assert first.markup_regions[-1].checklist_line_id == ''

    second = settings.images[2]
    second.markup_regions[0].dabs.add().uv = (0.25, 0.25)
    painted_second_id = second.markup_regions[0].region_id
    original_region_ids = {part.region_id for part in second.markup_regions}
    first.is_selected = False
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.dissociate_checklist.poll()
        assert bpy.ops.kanvas.dissociate_checklist() == {'FINISHED'}
    assert len(second.checklist_associations) == 0
    assert len(second.markup_regions[0].dabs) == 1
    assert second.markup_regions[0].checklist_card_id == ''
    assert second.markup_regions[0].checklist_origin_card_id == 'card-a'
    assert second.markup_regions[0].checklist_origin_line_id == 'task-a'
    card.text_lines[1].value = 'Wall after unlink'
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.associate_checklist() == {'FINISHED'}
    assert {part.region_id for part in second.markup_regions} == original_region_ids
    painted_second = next(part for part in second.markup_regions
                          if part.region_id == painted_second_id)
    assert painted_second.name == 'Wall after unlink'
    assert len(painted_second.dabs) == 1

    # Older versions erased the origin IDs. A unique task name recovers its paint.
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.dissociate_checklist() == {'FINISHED'}
    for part in second.markup_regions:
        part.checklist_origin_card_id = ''
        part.checklist_origin_line_id = ''
    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.associate_checklist() == {'FINISHED'}
    assert {part.region_id for part in second.markup_regions} == original_region_ids
    assert len(next(part for part in second.markup_regions
                    if part.region_id == painted_second_id).dabs) == 1

    with bpy.context.temp_override(area=area, region=region,
                                   space_data=area.spaces.active):
        assert bpy.ops.kanvas.dissociate_checklist() == {'FINISHED'}

    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        blend = str(Path(folder) / 'checklist_links.blend')
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        bpy.ops.wm.open_mainfile(filepath=blend)
        loaded = bpy.data.node_groups['Checklist links test'].kanvas_settings
        assert loaded.images[1].checklist_associations[0].card_id == 'card-a'
        assert next(part for part in loaded.images[1].markup_regions
                    if part.region_id == painted_first_id).checklist_line_id == 'task-a'
        assert len(next(part for part in loaded.images[1].markup_regions
                        if part.region_id == painted_first_id).dabs) == 1
        assert len(loaded.images[2].checklist_associations) == 0
        assert len(next(part for part in loaded.images[2].markup_regions
                        if part.region_id == painted_second_id).dabs) == 1
        assert next(part for part in loaded.images[2].markup_regions
                    if part.region_id == painted_second_id).checklist_origin_line_id == 'task-a'
        area = next(area for area in bpy.context.screen.areas if area.type == 'NODE_EDITOR')
        area.ui_type = 'KanvasNodeTree'
        area.spaces.active.node_tree = bpy.data.node_groups['Checklist links test']
        region = next(part for part in area.regions if part.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region,
                                       space_data=area.spaces.active):
            assert bpy.ops.kanvas.associate_checklist() == {'FINISHED'}
        assert {part.region_id for part in loaded.images[2].markup_regions} == original_region_ids
        assert len(next(part for part in loaded.images[2].markup_regions
                        if part.region_id == painted_second_id).dabs) == 1
    print('CHECKLIST LINKS PASS')
finally:
    addon.unregister()
