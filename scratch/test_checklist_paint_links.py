"""Per-task eye and colored arrow to painted image regions."""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy
import gpu
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_checklist import sync_checklist_regions
from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv
from k_tools_kanvas.utils.gpu.gpu_checklist import (
    _paint_target, _task_arrow_geometry, draw_checklist_links,
)
from k_tools_kanvas.utils.gpu.gpu_text import (
    _scroll_layout, draw_text_label, hit_test_checklist,
    hit_test_checklist_eye,
)


class View:
    def view_to_region(self, x, y, clip=False):
        return x, y

    def region_to_view(self, x, y):
        return x, y


view_region = SimpleNamespace(view2d=View(), width=800, height=600)
addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Checklist paint link test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    settings = tree.kanvas_settings
    card = settings.images.add()
    card.item_type = 'TEXT'
    card.item_id = 'paint-card'
    card.text_checklist = True
    card.location = (200, 200)
    line = card.text_lines.add()
    line.line_id = 'paint-task'
    line.value = 'Mark this area'
    line.color = (0.2, 0.8, 0.3)
    image = settings.images.add()
    image.item_type = 'IMAGE'
    image.item_id = 'paint-image'
    image.image_data = bpy.data.images.new('Paint link pixels', 128, 128)
    image.location = (470, 200)
    image.checklist_associations.add().card_id = card.item_id
    sync_checklist_regions(settings, image)
    image.markup_visible = True
    paint = image.markup_regions[0]
    paint.dabs.add().uv = (0.1, 0.5)
    paint.dabs.add().uv = (0.9, 0.5)

    layout = _scroll_layout(card, view_region)
    bx = layout['bounds'][0] + layout['padding']
    y = layout['top'] - layout['font_size'] * 0.5
    assert hit_test_checklist(card, view_region,
                              (bx + layout['font_size'] * 0.4, y)) == 0
    assert hit_test_checklist_eye(card, view_region,
                                  (bx + layout['font_size'] * 1.1, y)) == 0
    assert hit_test_checklist(card, view_region,
                              (bx + layout['font_size'] * 1.1, y)) is None

    cards = {card.item_id: card}
    vertices, colors, pairs = _task_arrow_geometry(settings, cards, view_region, 1.0)
    assert not vertices and not pairs
    line.show_color_links = True
    vertices, colors, pairs = _task_arrow_geometry(settings, cards, view_region, 1.0)
    assert len(vertices) == len(colors) == 54
    assert pairs == {(card.item_id, image.item_id)}
    assert all(abs(actual - expected) < 1e-5 for actual, expected in
               zip(colors[0][:3], line.color))
    left = image_point_from_uv(image, (0.1, 0.5))
    assert all(abs(actual - expected) < 1e-4 for actual, expected in
               zip(_paint_target(paint, image, (360, 200)), left))

    gpu.init()
    offscreen = gpu.types.GPUOffScreen(800, 600)
    try:
        with offscreen.bind():
            gpu.matrix.push_projection()
            try:
                gpu.matrix.load_projection_matrix(Matrix((
                    (2 / 800, 0, 0, -1), (0, 2 / 600, 0, -1),
                    (0, 0, 1, 0), (0, 0, 0, 1),
                )))
                draw_checklist_links(settings, 1.0, view_region)
                draw_text_label(card, view_region)
            finally:
                gpu.matrix.pop_projection()
    finally:
        offscreen.free()

    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        blend = str(Path(folder) / 'paint_links.blend')
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        bpy.ops.wm.open_mainfile(filepath=blend)
        loaded = bpy.data.node_groups['Checklist paint link test'].kanvas_settings
        assert loaded.images[0].text_lines[0].show_color_links
        assert loaded.images[1].markup_regions[0].checklist_line_id == 'paint-task'
    print('CHECKLIST PAINT LINKS PASS')
finally:
    addon.unregister()
