"""Island labels and checklist 'done' lines on Color Markup."""

import sys
import time
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_markup import (
    done_line_opacities, rasterize_markup, _composite_regions, _region_masks)
from k_tools_kanvas.utils.gpu.gpu_markup_labels import (
    label_islands, region_label_text)
from k_tools_kanvas.utils.gpu.gpu_markup import checklist_cards

addon.register()
try:
    # --- islands: two squares and a "C" whose centroid lies outside the paint
    mask = np.zeros((128, 128), dtype=np.float32)
    mask[10:40, 10:40] = 1.0          # square A
    mask[10:40, 80:120] = 1.0         # square B
    mask[60:120, 10:20] = 1.0         # C: left bar ...
    mask[60:70, 10:60] = 1.0          # ... top arm
    mask[110:120, 10:60] = 1.0        # ... bottom arm
    mask[3, 3] = 1.0                  # speck, must be ignored
    started = time.perf_counter()
    islands = label_islands(mask)
    elapsed = (time.perf_counter() - started) * 1000
    assert len(islands) == 3, islands
    for island in islands:
        u, v = island['uv']
        assert mask[int(v * 128), int(u * 128)] > 0.5, f'center outside paint: {island}'
    print(f'ISLANDS OK ({elapsed:.1f} ms for 128x128)')

    big = np.zeros((512, 512), dtype=np.float32)
    big[20:490, 20:490] = 1.0
    big[100:400, 100:400] = 0.0
    started = time.perf_counter()
    ring = label_islands(big)
    print(f'RING OK {len(ring)} island, {(time.perf_counter() - started) * 1000:.1f} ms for 512x512')
    assert len(ring) == 1
    u, v = ring[0]['uv']
    assert big[int(v * 512), int(u * 512)] > 0.5

    # --- done lines only for linked + done tasks
    tree = bpy.data.node_groups.new('Names', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    card = settings.images.add()
    card.item_type = 'TEXT'
    card.item_id = 'card-1'
    card.text_checklist = True
    task = card.text_lines.add()
    task.value = 'Paint the roof'
    task.line_id = 'line-1'
    image = bpy.data.images.new('names', 64, 64)
    item = settings.images.add()
    item.item_type = 'IMAGE'
    item.item_id = 'img-1'
    item.image_data = image
    linked = item.markup_regions.add()
    linked.region_id = 'r-linked'
    linked.name = 'Roof'
    linked.checklist_card_id = 'card-1'
    linked.checklist_line_id = 'line-1'
    linked.opacity = 1.0
    plain = item.markup_regions.add()
    plain.region_id = 'r-plain'
    plain.name = 'Chimney'
    plain.opacity = 1.0
    for target in (linked, plain):
        polygon = target.polygons.add()
        polygon.sequence = 1
        for uv in ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)):
            polygon.vertices.add().uv = uv
        target.next_sequence = 2

    assert not item.markup_show_names, 'names are off by default'
    assert item.markup_show_done_lines
    assert done_line_opacities(item) == (0.0, 0.0), 'task not done yet'
    task.done = True
    lines = done_line_opacities(item)
    assert lines == (0.5, 0.0), lines
    item.markup_done_line_opacity = 0.8
    first, second = done_line_opacities(item)
    assert abs(first - 0.8) < 1e-6 and second == 0.0
    item.markup_show_done_lines = False
    assert done_line_opacities(item) == ()
    item.markup_show_done_lines = True
    item.markup_done_line_opacity = 0.5

    masks = _region_masks(item.markup_regions, 64, 64)
    plain_pixels = _composite_regions([plain], masks[1:], 64, 64)
    striped = _composite_regions([linked], masks[:1], 64, 64, (0.5,))
    flat = _composite_regions([linked], masks[:1], 64, 64)
    assert np.allclose(plain_pixels[32, 32], flat[32, 32])
    assert not np.allclose(striped, flat), 'lines must change the texture'
    assert np.allclose(striped[0, 0], 0.0), 'nothing outside the island'
    darker = (striped[:, :, :3].sum() < flat[:, :, :3].sum())
    assert darker

    cards = checklist_cards(settings)
    assert region_label_text(cards, linked) == 'Paint the roof'
    assert region_label_text(cards, plain) == 'Chimney'
    print('NAMES + DONE LINES OK')
finally:
    addon.unregister()
