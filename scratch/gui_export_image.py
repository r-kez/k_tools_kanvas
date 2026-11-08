"""Export Image on a real GPU: a board with a shape, a gradient shape, a text card, a
frame and an arrow comes out with the right size and colors, transparent around the
items, without the selection outline, the same whether rendered in one piece or in
small tiles, and the selection is back afterwards.

    blender --factory-startup -P scratch/gui_export_image.py
Prints GUIEXPORT RESULT OK or FAIL. Needs a window (not -b). With KANVAS_SHOTS=folder
the exported PNG is kept there as board.png.
"""

import os
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def run():
    import numpy as np
    from k_tools_kanvas.utils import board_render as br
    addon.register()
    window = bpy.context.window_manager.windows[0]
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI export', 'KanvasNodeTree')
    space = area.spaces.active
    space.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
        bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 50.0), size=(200.0, 100.0))
        red_id = settings.images[-1].item_id
        bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(400.0, 50.0), size=(200.0, 100.0))
        ramp_id = settings.images[-1].item_id
        card = settings.images.add()
        card.item_type, card.item_id, card.name = 'TEXT', 'card', 'Note'
        card.location = (100.0, -150.0)
        card.text_width, card.text_height = 200.0, 100.0
        card.text_body = 'Hello board'

        def by_id(item_id):
            return next(item for item in settings.images if item.item_id == item_id)

        red = by_id(red_id)
        red.shape_fill_color, red.shape_fill_opacity = (1.0, 0.0, 0.0), 1.0
        red.shape_show_outline = False
        ramp = by_id(ramp_id)
        ramp.shape_fill_opacity = 1.0
        ramp.shape_show_outline = False
        ramp.shape_fill_type = 'LINEAR'
        first, last = ramp.shape_gradient_texture.color_ramp.elements
        first.color, last.color = (0, 0, 1, 1), (0, 1, 0, 1)
        from k_tools_kanvas.operators.ops_arrow import _create_arrow
        arrow = _create_arrow(settings, (0.0, 200.0))
        arrow.end = (500.0, 200.0)
        for item in settings.images:
            item.is_selected = item.item_id == red_id
        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_id == red_id)

        # --- Selection: the red shape alone, no outline --------------------------------
        rect = br.board_rect(settings, 'SELECTION')
        picture = br.render(settings, rect, 1.0, margin=10)
        check(picture.shape == (120, 220, 4), f'size {picture.shape}')
        middle = picture[60, 110]
        check(tuple(middle) == (255, 0, 0, 255), f'red middle {tuple(middle)}')
        check(picture[2, 2, 3] == 0, f'transparent margin {tuple(picture[2, 2])}')
        edge = picture[10:110, 10]   # the left side of the shape: no cyan outline
        check(not ((edge[:, 2] > 150) & (edge[:, 0] < 100)).any(), 'selection outline drawn')
        check(by_id(red_id).is_selected, 'the selection is back')

        # --- Whole board: gradient, text, arrow -----------------------------------------
        rect = br.board_rect(settings, 'ALL')
        full = br.render(settings, rect, 1.0, margin=0, background=(1.0, 1.0, 1.0, 1.0))
        height, width = full.shape[:2]

        def at(x, y):   # canvas point -> picture pixel
            return full[int(rect[3] - y), int(x - rect[0])]

        left, right = at(310, 50), at(490, 50)
        check(left[2] > 200 and left[1] < 60, f'gradient starts blue {tuple(left)}')
        check(right[1] > 200 and right[2] < 60, f'gradient ends green {tuple(right)}')
        text_area = full[int(rect[3] + 120):int(rect[3] + 180), int(10 - rect[0]):int(190 - rect[0])]
        check(len({tuple(p) for p in text_area.reshape(-1, 4)}) > 5, 'the card text is drawn')
        from k_tools_kanvas.utils.arrow_geometry import curve_points
        middle = curve_points(settings, arrow)[12]
        column = full[:, int(middle[0] - rect[0])]
        row = int(rect[3] - middle[1])
        near = column[max(0, row - 4):row + 5, :3]
        check((near.min(axis=1) < 200).any(), f'the arrow is drawn near row {row}')
        check(row >= 8, f'the arrow has room above it ({row} px)')
        check(full[..., 3].min() == 255, 'a color background is opaque')

        # --- Tiles join without seams ------------------------------------------------------
        old = br.TILE
        try:
            br.TILE = 64
            tiled = br.render(settings, rect, 1.0, margin=0, background=(1.0, 1.0, 1.0, 1.0))
        finally:
            br.TILE = old
        difference = np.abs(tiled.astype(int) - full.astype(int))
        check(difference.max() <= 8 and (difference > 2).mean() < 0.002,
              f'tiles differ: max {difference.max()}, {(difference > 2).mean():.4f} of pixels')

        # --- The operator writes the file and can load it ---------------------------------
        folder = os.environ.get('KANVAS_SHOTS')
        if not folder:
            temporary = tempfile.TemporaryDirectory()
            folder = temporary.name
            run.cleanup = temporary   # removed when the test ends
        path = os.path.join(folder, 'board.png')
        result = bpy.ops.kanvas.export_board_image(filepath=path, scope='ALL', scale=2.0,
                                                    margin=0, background='CANVAS',
                                                    load_image=True)
        check(result == {'FINISHED'}, f'operator {result}')
        check(os.path.exists(path), 'no file written')
        image = next((img for img in bpy.data.images if img.filepath and
                      os.path.basename(img.filepath) == 'board.png'), None)
        check(image is not None and image.packed_file is not None, 'not loaded and packed')
        if image is not None:
            check(tuple(image.size) == br.output_size(rect, 2.0, 0), f'scale 2 size {tuple(image.size)}')


def tick():
    try:
        run()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    for image in [img for img in bpy.data.images if img.name.startswith('board')]:
        bpy.data.images.remove(image)
    cleanup = getattr(run, 'cleanup', None)
    if cleanup is not None:
        cleanup.cleanup()
    print('GUIEXPORT RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(tick, first_interval=1.0)
