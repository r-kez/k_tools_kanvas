"""Exercise legacy migration, new boards, and Blender's tree duplication."""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings, migrate_legacy_scenes


addon.register()
try:
    scene = bpy.context.scene
    legacy = scene.kanvas_settings
    image_data = bpy.data.images.new('Shared pixels', 32, 32)
    image = legacy.images.add()
    image.item_id = 'legacy-image'
    image.item_type = 'IMAGE'
    image.name = 'Legacy image'
    image.image_data = image_data
    image.location = (125, 250)
    frame = legacy.images.add()
    frame.item_id = 'legacy-frame'
    frame.item_type = 'FRAME'
    frame.frame_node_name = 'frame-1'
    frame.name = 'References'
    frame.frame_width = 350
    frame.frame_height = 250
    card = legacy.images.add()
    card.item_id = 'legacy-card'
    card.item_type = 'TEXT'
    card.name = 'Note'
    card.text_lines.add().value = 'First line'
    card.text_lines.add().value = 'Second line'
    card.parent_frame = frame.frame_node_name
    arrow = legacy.arrows.add()
    arrow.arrow_id = 'legacy-arrow'
    arrow.label = 'Points here'
    arrow.start_item_id = image.item_id
    arrow.curve_offset = (15, 25)

    original = bpy.data.node_groups.new('Legacy Board', 'KanvasNodeTree')
    empty = bpy.data.node_groups.new('Other Board', 'KanvasNodeTree')
    migrate_legacy_scenes()
    assert scene.kanvas_tree_migrated
    assert len(original.kanvas_settings.images) == 3
    assert len(original.kanvas_settings.arrows) == 1
    assert len(empty.kanvas_settings.images) == 0
    assert original.kanvas_settings.images[0].image_data == image_data
    assert tuple(original.kanvas_settings.images[0].location) == (125, 250)
    assert original.kanvas_settings.arrows[0].start_item_id == 'legacy-image'
    assert original.kanvas_settings.arrows[0].label == 'Points here'
    first_area = SimpleNamespace(scene=scene,
                                 space_data=SimpleNamespace(edit_tree=original))
    second_area = SimpleNamespace(scene=scene,
                                  space_data=SimpleNamespace(edit_tree=original))
    other_area = SimpleNamespace(scene=scene,
                                 space_data=SimpleNamespace(edit_tree=empty))
    assert get_settings(first_area).as_pointer() == get_settings(second_area).as_pointer()
    assert get_settings(first_area).as_pointer() != get_settings(other_area).as_pointer()
    copied_card = next(item for item in original.kanvas_settings.images
                       if item.item_type == 'TEXT')
    assert copied_card.parent_frame == 'frame-1'
    assert [line.value for line in copied_card.text_lines] == ['First line', 'Second line']

    original.annotation = bpy.data.annotations.new('Board annotation')
    original.annotation.layers.new('Marks', set_active=True)

    duplicate = original.copy()
    duplicate.name = 'Duplicate Board'
    assert len(duplicate.kanvas_settings.images) == 3
    assert len(duplicate.kanvas_settings.arrows) == 1
    duplicate.kanvas_settings.images[0].location = (900, 900)
    duplicate.kanvas_settings.arrows[0].label = 'Changed'
    assert tuple(original.kanvas_settings.images[0].location) == (125, 250)
    assert original.kanvas_settings.arrows[0].label == 'Points here'
    assert duplicate.kanvas_settings.images[0].image_data == image_data
    get_settings(SimpleNamespace(scene=scene,
                                 space_data=SimpleNamespace(edit_tree=duplicate)))
    assert duplicate.annotation is not None
    assert duplicate.annotation != original.annotation
    duplicate.annotation.layers[0].color = (0.2, 0.7, 0.1)
    assert tuple(original.annotation.layers[0].color) != tuple(
        duplicate.annotation.layers[0].color)

    migrate_legacy_scenes()
    assert len(original.kanvas_settings.images) == 3

    filepath = Path(__file__).with_name(f'.tree-migration-{uuid.uuid4().hex}.blend')
    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(filepath))
        bpy.ops.wm.open_mainfile(filepath=str(filepath))
        original = bpy.data.node_groups['Legacy Board']
        duplicate = bpy.data.node_groups['Duplicate Board']
        empty = bpy.data.node_groups['Other Board']
        assert len(original.kanvas_settings.images) == 3
        assert len(duplicate.kanvas_settings.images) == 3
        assert len(empty.kanvas_settings.images) == 0
        assert original.kanvas_settings.images[0].name == 'Legacy image'
        assert tuple(original.kanvas_settings.images[0].location) == (125, 250)
        assert tuple(duplicate.kanvas_settings.images[0].location) == (900, 900)
        assert bpy.context.scene.kanvas_tree_migrated
    finally:
        filepath.unlink(missing_ok=True)
    print('tree migration and isolation check passed')
finally:
    addon.unregister()
