"""Read-only large-board benchmark for checklist link drawing."""

import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy
import gpu
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_checklist import draw_checklist_links
from k_tools_kanvas.operators.ops_checklist import sync_checklist_regions


class View:
    def view_to_region(self, x, y, clip=False):
        return x, y

    def region_to_view(self, x, y):
        return x, y


blend_path = Path(__file__).resolve().parents[2] / 'blends' / 'Kanvas.blend'
addon.register()
try:
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    load_seconds = time.perf_counter() - started
    trees = [tree for tree in bpy.data.node_groups if tree.bl_idname == 'KanvasNodeTree']
    tree = max(trees, key=lambda item: len(item.kanvas_settings.images))
    settings = tree.kanvas_settings
    images = [item for item in settings.images
              if item.item_type == 'IMAGE' and item.image_data]
    cards = [item for item in settings.images
             if item.item_type == 'TEXT' and item.text_checklist]
    if not cards:
        card = settings.images.add()
        card.item_id = 'benchmark-checklist'
        card.item_type = 'TEXT'
        card.text_checklist = True
        card.location = (0, 0)
    else:
        card = cards[0]
    added = 0
    for image in images[:100]:
        if not any(link.card_id == card.item_id
                   for link in image.checklist_associations):
            image.checklist_associations.add().card_id = card.item_id
            added += 1

    gpu.init()
    offscreen = gpu.types.GPUOffScreen(512, 512)
    try:
        with offscreen.bind():
            gpu.matrix.push_projection()
            try:
                gpu.matrix.load_projection_matrix(Matrix((
                    (2 / 512, 0, 0, -1), (0, 2 / 512, 0, -1),
                    (0, 0, 1, 0), (0, 0, 0, 1),
                )))
                samples = []
                for _ in range(30):
                    start = time.perf_counter()
                    draw_checklist_links(settings)
                    samples.append((time.perf_counter() - start) * 1000)
                generic_median = statistics.median(samples)
                if not card.text_lines:
                    card.text_lines.add().value = 'Benchmark task'
                line = card.text_lines[0]
                if not line.line_id:
                    line.line_id = 'benchmark-task'
                line.show_color_links = True
                for image in images[:100]:
                    sync_checklist_regions(settings, image)
                    image.markup_visible = True
                    paint = next(part for part in image.markup_regions
                                 if part.checklist_card_id == card.item_id
                                 and part.checklist_line_id == line.line_id)
                    if not paint.dabs and not paint.polygons:
                        paint.dabs.add().uv = (0.5, 0.5)
                view_region = SimpleNamespace(view2d=View(), width=512, height=512)
                samples = []
                for _ in range(30):
                    start = time.perf_counter()
                    draw_checklist_links(settings, 1.0, view_region)
                    samples.append((time.perf_counter() - start) * 1000)
            finally:
                gpu.matrix.pop_projection()
    finally:
        offscreen.free()
    print('CHECKLIST BENCH',
          f'load={load_seconds:.2f}s', f'items={len(settings.images)}',
          f'images={len(images)}', f'links_added={added}',
          f'generic_median={generic_median:.3f}ms',
          f'paint_arrows_median={statistics.median(samples):.3f}ms')
finally:
    addon.unregister()
