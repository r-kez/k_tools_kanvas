"""Selecting an image does not change its canvas layer or UI List order."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings


addon.register()
try:
    settings = get_settings(bpy.context)
    for name in ('A', 'B', 'C'):
        item = settings.images.add()
        item.name = name
        item.item_type = 'IMAGE'
        item.image_data = bpy.data.images.new(name, 32, 32)

    settings.active_image_index = 0
    assert [item.z_index for item in settings.images] == [0, 0, 0]
    settings.active_image_index = 1
    assert [item.z_index for item in settings.images] == [0, 0, 0]
    assert [item.name for item in settings.images] == ['A', 'B', 'C']

    # Shift addition must keep the existing layer order.
    previous = [item.z_index for item in settings.images]
    settings.shift_is_held = True
    settings.images[2].is_selected = True
    settings.active_image_index = 2
    assert [item.z_index for item in settings.images] == previous

    settings.shift_is_held = False
    settings.images[0].is_selected = False
    settings.images[1].is_selected = False
    settings.active_image_index = 0
    assert [item.z_index for item in settings.images] == [0, 0, 0]
    assert [item.name for item in settings.images] == ['A', 'B', 'C']
    print('image selection layer check passed')
finally:
    addon.unregister()
