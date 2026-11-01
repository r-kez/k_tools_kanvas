"""Checklist eye only when linked, hidden Kanvas datablocks, Move-mode pan operator."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import hidden_datablocks
from k_tools_kanvas.utils.gpu import gpu_text

addon.register()
try:
    # ---- the eye appears only once the checklist is linked to an image -------
    class View:
        def view_to_region(self, x, y, clip=False):
            return x + 600, y + 400
        def region_to_view(self, x, y):
            return x - 600, y - 400

    tree = bpy.data.node_groups.new('Usability', 'KanvasNodeTree')
    settings = tree.kanvas_settings
    card = settings.images.add()
    card.item_type, card.item_id, card.text_checklist = 'TEXT', 'card', True
    card.location, card.text_width, card.text_height, card.text_font_size = (-400, 100), 300, 200, 18
    task = card.text_lines.add()
    task.value, task.line_id = 'Roof', 'line'
    region = SimpleNamespace(view2d=View(), width=1600, height=900)
    layout = gpu_text._scroll_layout(card, region)
    x = layout['bounds'][0] + layout['padding'] + layout['font_size'] * 1.1
    y = layout['top'] + layout['scroll_screen'] - layout['font_size'] * 0.5
    assert gpu_text.hit_test_checklist_eye(card, region, (x, y)) is None, 'unlinked: no eye'

    image = bpy.data.images.new('Kanvas_photo.png', 16, 16)
    item = settings.images.add()
    item.item_type, item.item_id, item.image_data = 'IMAGE', 'img', image
    item.checklist_associations.add().card_id = 'card'
    assert gpu_text.hit_test_checklist_eye(card, region, (x, y)) == 0, 'linked: eye is clickable'
    item.checklist_associations.remove(0)
    assert gpu_text.hit_test_checklist_eye(card, region, (x, y)) is None, 'unlinked again'
    print('EYE ONLY WHEN LINKED OK')

    # ---- Kanvas images are hidden from Blender's lists, and restorable -------------
    assert hidden_datablocks.sweep() >= 1
    assert image.name == '.Kanvas_photo.png', image.name
    assert hidden_datablocks.sweep() == 0, 'second sweep must be a no-op'
    other = bpy.data.images.new('My own picture', 8, 8)
    hidden_datablocks.sweep()
    assert other.name == 'My own picture', 'images outside Kanvas are untouched'
    from k_tools_kanvas.utils.gpu.gpu_markup import markup_texture_for_item
    generated = bpy.data.images.new('Kanvas Mask abcd1234', 8, 8)
    hidden_datablocks.sweep()
    assert generated.name == '.Kanvas Mask abcd1234'
    visible = [i.name for i in bpy.data.images if not i.name.startswith('.')]
    assert 'My own picture' in visible and not any('Kanvas' in n for n in visible), visible
    hidden_datablocks.enabled = lambda: False                # the preference switched off
    assert hidden_datablocks.sweep() >= 2
    assert image.name == 'Kanvas_photo.png' and generated.name == 'Kanvas Mask abcd1234'
    print('HIDDEN DATABLOCKS OK')

    # ---- Move-mode pan is a registered, short-lived operator ---------------------------
    assert hasattr(bpy.ops.kanvas, 'hand_pan') and hasattr(bpy.ops.kanvas, 'hand_cursor')
    assert 'kanvas.hand_pan' not in __import__('k_tools_kanvas.keymap', fromlist=['x'])._MANAGED_OPERATORS
    print('MOVE PAN OPERATOR OK')
finally:
    addon.unregister()
