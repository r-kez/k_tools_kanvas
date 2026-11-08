"""Board pictures without a GPU: the area to export, the picture size, the tiles, straight
alpha, and a PNG that Blender reads back with the right size and colors."""
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import board_render as br

# --- Size and tiles --------------------------------------------------------------------
assert br.output_size((0, 0, 100, 50), 1.0, 0) == (100, 50)
assert br.output_size((0, 0, 100, 50), 2.0, 10) == (220, 120)
assert br.output_size((0, 0, 100.2, 50), 1.0, 0) == (101, 50), 'rounds up'
pieces = br.tiles(10000, 5000)
assert sum(w * h for _, _, w, h in pieces) == 10000 * 5000
assert max(max(w, h) for _, _, w, h in pieces) <= br.TILE
assert (8192, 4096, 1808, 904) in pieces

view = br._View2D(100.0, 50.0, 0.5)
assert view.view_to_region(101.0, 51.0) == (2.0, 2.0)
assert view.region_to_view(2.0, 2.0) == (101.0, 51.0)

# --- Straight alpha ----------------------------------------------------------------------
premultiplied = np.array([[[100, 50, 0, 128], [0, 0, 0, 0], [255, 255, 255, 255]]], np.uint8)
straight = br.unpremultiply(premultiplied)
assert tuple(straight[0, 0]) == (199, 100, 0, 128), straight[0, 0]
assert tuple(straight[0, 1]) == (0, 0, 0, 0) and tuple(straight[0, 2]) == (255, 255, 255, 255)

addon.register()
try:
    tree = bpy.data.node_groups.new('Render', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    assert br.board_rect(settings, 'ALL') is None, 'an empty board has nothing'
    card = settings.images.add()
    card.item_type, card.item_id = 'TEXT', 'card'
    card.location = (0.0, 0.0)
    card.text_width, card.text_height, card.text_scale = 200.0, 100.0, 1.0
    other = settings.images.add()
    other.item_type, other.item_id = 'TEXT', 'other'
    other.location = (1000.0, 0.0)
    other.text_width, other.text_height, other.text_scale = 100.0, 100.0, 1.0
    card.is_selected = True
    assert br.board_rect(settings, 'SELECTION') == (-100.0, -50.0, 100.0, 50.0)
    assert br.board_rect(settings, 'ALL') == (-100.0, -50.0, 1050.0, 50.0)
    other.show_in_editor = False
    assert br.board_rect(settings, 'ALL') == (-100.0, -50.0, 100.0, 50.0), 'hidden items stay out'

    # --- What a picture of the selection shows ------------------------------------------
    other.show_in_editor = True
    frame = settings.images.add()
    frame.item_type, frame.item_id, frame.frame_node_name = 'FRAME', 'frame', 'kanvas_frame'
    frame.location, frame.frame_width, frame.frame_height = (-300.0, 300.0), 800.0, 600.0
    card.parent_frame = 'kanvas_frame'
    inner = settings.images.add()
    inner.item_type, inner.item_id, inner.parent_frame = 'TEXT', 'inner', 'kanvas_frame'
    inner.show_in_editor = False
    arrows = settings.arrows
    linked = arrows.add()
    linked.start_item_id, linked.end_item_id = 'card', 'card'
    half = arrows.add()
    half.start_item_id, half.end_item_id = 'card', 'other'
    loose = arrows.add()
    loose.start, loose.end = (0.0, 0.0), (10.0, 10.0)
    for item in settings.images:
        item.is_selected = item.item_id == 'card'
    items, kept_arrows = br.selection_contents(settings)
    assert {item.item_id for item in items} == {'card'}, 'the frame around it stays out'
    assert [a.as_pointer() for a in kept_arrows] == [linked.as_pointer()], \
        'only arrows between kept items'
    assert br.board_rect(settings, 'SELECTION', only_selected=False) == (-100.0, -50.0, 100.0, 50.0)
    for item in settings.images:
        item.is_selected = item.item_id == 'frame'
    items, kept_arrows = br.selection_contents(settings)
    assert {item.item_id for item in items} == {'frame', 'card'}, \
        'a selected frame brings its content, not what is hidden'
    loose.is_selected = True
    assert loose.as_pointer() in {a.as_pointer() for a in br.selection_contents(settings)[1]}

    # --- PNG written by hand, read back by Blender -------------------------------------
    picture = np.zeros((3, 5, 4), np.uint8)
    picture[0, 0] = (255, 0, 0, 255)        # top left: red
    picture[2, 4] = (0, 0, 255, 128)        # bottom right: half blue
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        path = str(Path(folder) / 'board.png')
        br.write_png(path, picture)
        image = bpy.data.images.load(path)
        assert tuple(image.size) == (5, 3)
        pixels = np.array(image.pixels[:]).reshape(3, 5, 4)   # Blender: bottom row first
        assert np.allclose(pixels[2, 0], (1, 0, 0, 1), atol=1 / 255)
        assert np.allclose(pixels[0, 4, 2:], (1, 128 / 255), atol=1 / 255)
        bpy.data.images.remove(image)
    assert hasattr(bpy.ops.kanvas, 'export_board_image')
    print('test_board_render: OK')
finally:
    addon.unregister()
