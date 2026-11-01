"""Verify that image appearance controls update only selected images."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings


addon.register()
try:
    settings = get_settings(bpy.context)
    images = [settings.images.add() for _ in range(3)]
    for image in images:
        image.item_type = 'IMAGE'
    images[0].is_selected = True
    images[1].is_selected = True
    images[2].is_selected = False
    settings.active_image_index = 0

    changes = {
        'flip_h': True,
        'flip_v': True,
        'brightness': 2.0,
        'contrast': 1.5,
        'saturation': 0.5,
        'opacity': 0.6,
        'color_tint': (0.2, 0.4, 0.8),
        'use_color_correction': False,
    }
    for name, value in changes.items():
        setattr(settings, 'batch_' + name, value)
        for actual in [getattr(settings, 'batch_' + name),
                       *(getattr(image, name) for image in images[:2])]:
            if name == 'color_tint':
                assert all(abs(a - b) < 0.0001 for a, b in zip(actual, value)), (name, actual)
            elif isinstance(value, float):
                assert abs(actual - value) < 0.0001, (name, actual)
            else:
                assert actual == value, (name, actual)

    assert images[2].flip_h is False
    assert images[2].brightness == 1.0
    assert images[2].use_color_correction is True
    print('BATCH IMAGE ADJUSTMENTS PASS')
finally:
    addon.unregister()
