"""Checks for collapsed frame rows and frame-title occlusion."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
import k_tools_kanvas.utils.gpu as gpu_module
from k_tools_kanvas.ui import KANVAS_UL_image_list
from k_tools_kanvas.utils.gpu import frame_header_open_spans, visible_frames_in_draw_order


addon.register()
try:
    tree = bpy.data.node_groups.new('Label dispatch test', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    image = bpy.data.images.new('layer-test', 40, 40)
    back = settings.images.add()
    back.item_type = 'FRAME'
    back.name = 'Back'
    back.frame_node_name = 'back'
    back.location = (0, 100)
    back.frame_width = 200
    back.frame_height = 100
    back.z_index = 0
    back.auto_resize = False
    front = settings.images.add()
    front.item_type = 'FRAME'
    front.name = 'Front'
    front.frame_node_name = 'front'
    front.location = (100, 90)
    front.frame_width = 200
    front.frame_height = 100
    front.z_index = 1
    front.auto_resize = False
    child = settings.images.add()
    child.name = 'child'
    child.image_data = image
    child.location = (100, -100)
    child.parent_frame = 'back'
    child.is_selected = True
    orphan = settings.images.add()
    orphan.name = 'orphan'
    orphan.image_data = image
    orphan.location = (400, 0)

    spans = frame_header_open_spans(settings, back, 60, 140, 70, 90)
    assert spans == [(60, 100)], spans
    front.location = (250, 90)
    assert frame_header_open_spans(settings, back, 60, 140, 70, 90) == [(60, 140)]
    child.location = (100, 80)
    assert frame_header_open_spans(settings, back, 60, 140, 70, 90) == [
        (60, 80), (120, 140)]
    child.show_in_editor = False
    assert frame_header_open_spans(settings, back, 60, 140, 70, 90) == [(60, 140)]
    child.show_in_editor = True
    child.location = (100, -100)
    assert [item.frame_node_name for _, item in visible_frames_in_draw_order(settings)] == [
        'back', 'front']

    active = next(i for i, item in enumerate(settings.images) if item.name == 'child')
    settings.active_image_index = active
    back.list_collapsed = True
    flags, order = KANVAS_UL_image_list.filter_items(
        SimpleNamespace(bitflag_filter_item=1), bpy.context, settings, 'images')
    # The list shows the stacking tree, top in front: the front frame, then the back
    # frame with its child right under it, then the loose image.
    assert flags == [1, 1, 0, 1] and order == [1, 0, 2, 3], (flags, order)
    assert settings.active_image_index == active and child.is_selected
    assert child.show_in_editor
    settings.list_search = 'child'
    flags, _ = KANVAS_UL_image_list.filter_items(
        SimpleNamespace(bitflag_filter_item=1), bpy.context, settings, 'images')
    assert flags == [1, 0, 1, 0], flags
    settings.list_search = 'BACK'
    flags, _ = KANVAS_UL_image_list.filter_items(
        SimpleNamespace(bitflag_filter_item=1), bpy.context, settings, 'images')
    assert flags == [1, 0, 1, 0], flags
    settings.list_search = 'orphan'
    flags, _ = KANVAS_UL_image_list.filter_items(
        SimpleNamespace(bitflag_filter_item=1), bpy.context, settings, 'images')
    assert flags == [0, 0, 0, 1], flags
    assert child.show_in_editor and settings.active_image_index == active
    settings.list_search = ''
    back.list_collapsed = False
    flags, _ = KANVAS_UL_image_list.filter_items(
        SimpleNamespace(bitflag_filter_item=1), bpy.context, settings, 'images')
    assert flags == [1, 1, 1, 1], flags

    # Text labels must be dispatched by the actual POST_PIXEL draw callback.
    back.show_in_editor = False
    front.show_in_editor = False
    card = settings.images.add()
    card.item_type = 'TEXT'
    card.name = 'Card label'
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    import gpu
    if hasattr(gpu, 'init'):
        gpu.init()   # Blender 5.2 can draw without a window once the gpu module is started
    calls = []
    original_draw_text_label = gpu_module.draw_text_label
    gpu_module.draw_text_label = lambda item, region, *args: calls.append(item.name)
    try:
        with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
            gpu_module.draw_frame_labels()
    finally:
        gpu_module.draw_text_label = original_draw_text_label
    assert calls == ['Card label'], calls

    print('Frame layer and list checks passed')
finally:
    addon.unregister()
