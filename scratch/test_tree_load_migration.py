"""Opening an old scene board migrates it to a Kanvas Tree once."""

import sys
import uuid
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon


addon.register()
filepath = Path(__file__).with_name(f'.legacy-load-{uuid.uuid4().hex}.blend')
try:
    scene = bpy.context.scene
    legacy = scene.kanvas_settings
    image = legacy.images.add()
    image.item_id = 'old-item'
    image.name = 'Old reference'
    image.item_type = 'IMAGE'
    image.image_data = bpy.data.images.new('Old pixels', 24, 24)
    image.location = (37, 91)
    tree = bpy.data.node_groups.new('Old board', 'KanvasNodeTree')
    assert not scene.kanvas_tree_migrated
    bpy.ops.wm.save_as_mainfile(filepath=str(filepath))
    bpy.ops.wm.open_mainfile(filepath=str(filepath))
    scene = bpy.context.scene
    tree = bpy.data.node_groups['Old board']
    assert scene.kanvas_tree_migrated
    assert len(tree.kanvas_settings.images) == 1
    assert tree.kanvas_settings.images[0].name == 'Old reference'
    assert tuple(tree.kanvas_settings.images[0].location) == (37, 91)
    assert len(scene.kanvas_settings.images) == 1  # rollback source is retained
    print('legacy load migration check passed')
finally:
    filepath.unlink(missing_ok=True)
    addon.unregister()
