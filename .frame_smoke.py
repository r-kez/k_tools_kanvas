import sys, bpy
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))
import k_tools_kanvas as addon
addon.register()
tree = bpy.data.node_groups.new('Kanvas smoke', 'KanvasNodeTree')
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
area.type = 'NODE_EDITOR'
area.ui_type = 'KanvasNodeTree'
area.spaces.active.node_tree = tree
scene = bpy.context.scene
settings = scene.kanvas_settings
img = settings.images.add()
img.item_type = 'IMAGE'
img.name = 'Test image'
img.image_data = bpy.data.images.new('Smoke image', 100, 80)
img.location = (100, 100)
img.is_selected = True
with bpy.context.temp_override(area=area, space_data=area.spaces.active):
    print('POLL', bpy.ops.kanvas.create_frame.poll())
    result = bpy.ops.kanvas.create_frame()
    print('CREATE', result)
    frames = [item for item in settings.images if item.item_type == 'FRAME']
    assert len(frames) == 1, len(frames)
    frame = frames[0]
    print("ITEMS", [(i.item_type, i.name, i.frame_node_name, i.parent_frame, i.is_selected) for i in settings.images]); assert any(i.item_type == "IMAGE" and i.parent_frame == frame.frame_node_name for i in settings.images)
    assert len(tree.nodes) == 0
    frame.frame_color = (0.8, 0.2, 0.1)
    frame.frame_opacity = 0.4
    frame.frame_width = 420
    print('CUSTOM', frame.name, tuple(frame.location), frame.frame_width, frame.frame_opacity)
    from k_tools_kanvas.utils.gpu import sync_kanvas_frames, is_sync_needed
    assert not is_sync_needed(tree, settings)
    legacy = tree.nodes.new('NodeFrame')
    legacy.label = 'Old Frame'
    legacy.location = (200, 300)
    legacy.width = 210
    legacy.height = 160
    img.parent_frame = legacy.name
    sync_kanvas_frames(tree, settings)
    assert all(node.type != 'FRAME' for node in tree.nodes)
    imported = next(item for item in settings.images if item.item_type == 'FRAME' and item.name == 'Old Frame')
    assert img.parent_frame == imported.frame_node_name
    print('MIGRATED', imported.name, tuple(imported.location), imported.frame_width, imported.frame_height)
    from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
    helper = KanvasInteractionHelpers()
    frame_id = frames[0].frame_node_name
    custom = next(item for item in settings.images if item.item_type == 'FRAME' and item.frame_node_name == frame_id)
    child = next(item for item in settings.images if item.item_type == 'IMAGE')
    child.parent_frame = frame_id
    original = tuple(child.location)
    origin = tuple(custom.location)
    helper._start_frame_drag(bpy.context, custom, 'MOVE', (0, 0))
    helper._update_drag(bpy.context, 30, -20)
    assert tuple(child.location) == (original[0] + 30, original[1] - 20)
    assert tuple(custom.location) == (origin[0] + 30, origin[1] - 20)
    helper._cancel_drag(bpy.context)
    assert tuple(child.location) == original
    helper._start_frame_drag(bpy.context, custom, 'RESIZE', (0, 0))
    old_width = custom.frame_width
    helper._update_drag(bpy.context, 25, -15)
    assert custom.frame_width == old_width + 25
    assert tuple(child.location) == original
    helper._cancel_drag(bpy.context)
    print('DRAG AND RESIZE OK')
    from k_tools_kanvas import keymap
    from k_tools_kanvas.utils.gpu import gpu_common
    old_prefs = gpu_common.get_prefs
    from types import SimpleNamespace
    gpu_common.get_prefs = lambda: SimpleNamespace()
    try:
        keymap.rebuild()
        assert any(item.properties.action == 'CREATE_FRAME' and item.type == 'F'
                   for _, item in keymap._items)
        print('F BINDING OK')
    finally:
        keymap.unregister()
        gpu_common.get_prefs = old_prefs
    print('KEY F OK')
addon.unregister()
print('PASS')
