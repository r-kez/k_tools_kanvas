"""A PureRef scene dropped on the board lands with its middle under the pointer, keeping
the layout; imported from the menu it keeps the scene's own coordinates."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_pureref import _move_to
from k_tools_kanvas.utils.item_geometry import item_bounds


addon.register()
try:
    tree = bpy.data.node_groups.new('PureRef drop', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    old = settings.images.add()
    old.item_type, old.item_id = 'TEXT', 'old'
    old.location = (-5000.0, 0.0)
    image = bpy.data.images.new('pur', 100, 50)
    spots = [(1000.0, 1000.0), (1400.0, 1200.0)]
    for n, spot in enumerate(spots):
        item = settings.images.add()
        item.item_type, item.item_id, item.image_data = 'IMAGE', f'i{n}', image
        item.location = spot

    _move_to(settings, 1, None)
    assert tuple(settings.images[1].location) == spots[0], 'menu import keeps coordinates'

    _move_to(settings, 1, (10.0, 20.0))
    boxes = [item_bounds(settings.images[i]) for i in (1, 2)]
    middle = ((min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2,
              (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2)
    assert math.dist(middle, (10.0, 20.0)) < 1e-4, middle
    gap = (settings.images[2].location[0] - settings.images[1].location[0],
           settings.images[2].location[1] - settings.images[1].location[1])
    assert math.dist(gap, (400.0, 200.0)) < 1e-4, 'the layout is kept'
    assert tuple(settings.images[0].location) == (-5000.0, 0.0), 'older items stay'
    print('test_pureref_drop_location: OK')
finally:
    addon.unregister()
