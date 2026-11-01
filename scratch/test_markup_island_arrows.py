"""Checklist arrows: nearest island only, or one arrow per island."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu import gpu_checklist as gc


class View:
    def view_to_region(self, x, y, clip=False):
        return x + 600, y + 400

    def region_to_view(self, x, y):
        return x - 600, y - 400


addon.register()
try:
    tree = bpy.data.node_groups.new('Arrows', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    card = settings.images.add()
    card.item_type = 'TEXT'
    card.item_id = 'card'
    card.text_checklist = True
    card.location = (-400, 100)
    card.text_width = 300
    card.text_height = 200
    card.text_font_size = 18
    task = card.text_lines.add()
    task.value = 'Roof'
    task.line_id = 'line'
    task.show_color_links = True
    task.color = (1.0, 0.3, 0.2)

    image = bpy.data.images.new('img', 128, 128)
    item = settings.images.add()
    item.item_type = 'IMAGE'
    item.item_id = 'img'
    item.image_data = image
    item.location = (300, 0)
    item.markup_visible = True
    link = item.checklist_associations.add()
    link.card_id = 'card'
    paint = item.markup_regions.add()
    paint.region_id = 'r'
    paint.checklist_card_id = 'card'
    paint.checklist_line_id = 'line'
    paint.opacity = 1.0
    for low, high in ((0.1, 0.35), (0.65, 0.9)):   # two separate islands
        polygon = paint.polygons.add()
        polygon.sequence = len(paint.polygons)
        for uv in ((low, low), (high, low), (high, high), (low, high)):
            polygon.vertices.add().uv = uv
    paint.next_sequence = 3

    region = SimpleNamespace(view2d=View(), width=1600, height=900)
    cards = {'card': card}

    def arrow_vertices():
        vertices, _, pairs = gc._task_arrow_geometry(settings, cards, region, 1.0)
        return len(vertices), pairs

    assert not item.markup_arrows_all_islands, 'nearest island is the default'
    nearest, pairs = arrow_vertices()
    assert nearest > 0 and ('card', 'img') in pairs
    item.markup_arrows_all_islands = True
    every, _ = arrow_vertices()
    assert every == nearest * 2, (nearest, every)
    item.markup_arrows_all_islands = False
    assert arrow_vertices()[0] == nearest
    print('ISLAND ARROWS OK', nearest, every)
finally:
    addon.unregister()
