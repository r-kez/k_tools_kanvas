"""Selected arrows follow an image/card move without moving anchors twice."""

from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import KanvasInteractionHelpers
from k_tools_kanvas.properties import suspend_selection_updates
from k_tools_kanvas.utils.arrow_geometry import endpoint


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Mixed move', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        image = settings.images.add()
        image.item_id = 'moving-image'
        image.item_type = 'IMAGE'
        image.image_data = bpy.data.images.new('Moving image', 40, 40)
        image.location = (0, 0)
        image.is_selected = True
        card = settings.images.add()
        card.item_id = 'moving-card'
        card.item_type = 'TEXT'
        card.location = (300, 100)
        card.is_selected = True
        stationary = settings.images.add()
        stationary.item_id = 'stationary-image'
        stationary.item_type = 'IMAGE'
        stationary.image_data = bpy.data.images.new('Stationary image', 40, 40)
        stationary.location = (800, 0)
        with suspend_selection_updates():
            settings.active_image_index = 0
        anchored = settings.arrows.add()
        anchored.start = (0, 0)
        anchored.end = (200, 0)
        anchored.start_item_id = image.item_id
        anchored.start_uv = (0.5, 0.5)
        anchored.is_selected = True
        free = settings.arrows.add()
        free.start = (500, 100)
        free.end = (600, 100)
        free.is_selected = True
        passive = settings.arrows.add()
        passive.start_item_id = image.item_id
        passive.start_uv = (0.5, 0.5)
        passive.end = (-200, 0)
        detached = settings.arrows.add()
        detached.start_item_id = stationary.item_id
        detached.start_uv = (0.5, 0.5)
        detached.end = (900, 0)
        detached.is_selected = True

        gesture = KanvasInteractionHelpers()
        gesture.start_drag(bpy.context, image, 'MOVE', (0, 0))
        gesture._update_drag(bpy.context, 90, 70)
        dx, dy = image.location
        assert tuple(card.location) == (300 + dx, 100 + dy)
        assert tuple(endpoint(settings, anchored, 'start')) == tuple(image.location)
        assert anchored.start_item_id == image.item_id
        assert tuple(anchored.end) == (200 + dx, dy)
        assert tuple(free.start) == (500 + dx, 100 + dy)
        assert tuple(endpoint(settings, passive, 'start')) == tuple(image.location)
        assert tuple(passive.end) == (-200, 0)
        assert not detached.start_item_id
        assert tuple(detached.start) == (800 + dx, dy)
        gesture._update_drag(bpy.context, 0, 0)
        assert tuple(image.location) == (0, 0)
        assert detached.start_item_id == stationary.item_id
        assert tuple(free.start) == (500, 100)
        gesture._update_drag(bpy.context, 90, 70)
        gesture._cancel_drag(bpy.context)
        assert tuple(image.location) == (0, 0)
        assert tuple(card.location) == (300, 100)
        assert tuple(free.start) == (500, 100)
        assert anchored.start_item_id == image.item_id
        assert tuple(anchored.end) == (200, 0)
        assert detached.start_item_id == stationary.item_id
    print('MIXED ARROW IMAGE MOVE PASS')
finally:
    addon.unregister()
