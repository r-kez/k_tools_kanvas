"""Test mask-level color eyedropper and checklist link persistence."""

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_markup import region_index_at_uv, _region_masks
from k_tools_kanvas.utils.gpu.gpu_checklist import _task_arrow_geometry, draw_checklist_links
from k_tools_kanvas.operators.ops_checklist import sync_checklist_regions

addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Eyedropper test tree', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    settings = tree.kanvas_settings

    # 1. Test Task 1: Check that checklist link between card and image is NOT suppressed by task arrows
    card = settings.images.add()
    card.item_type = 'TEXT'
    card.item_id = 'test-card'
    card.text_checklist = True
    card.location = (100, 100)
    line1 = card.text_lines.add()
    line1.line_id = 'task-1'
    line1.value = 'Item 1'
    line1.show_color_links = True
    line1.color = (0.9, 0.2, 0.2)

    image = settings.images.add()
    image.item_type = 'IMAGE'
    image.item_id = 'test-image'
    image.image_data = bpy.data.images.new('TestImg', 64, 64)
    image.location = (400, 100)
    image.checklist_associations.add().card_id = card.item_id
    sync_checklist_regions(settings, image)
    image.markup_visible = True

    # Add a dab to the paint region for task-1
    paint1 = image.markup_regions[0]
    dab = paint1.dabs.add()
    dab.uv = (0.5, 0.5)
    dab.radius_uv = (0.1, 0.1)
    dab.uv_axis_x = (0.1, 0.0)
    dab.uv_axis_y = (0.0, 0.1)

    class MockView:
        def view_to_region(self, x, y, clip=False):
            return x, y
        def region_to_view(self, x, y):
            return x, y

    mock_region = SimpleNamespace(view2d=MockView(), width=800, height=600)
    cards = {card.item_id: card}
    vertices, colors, task_pairs = _task_arrow_geometry(settings, cards, mock_region, 1.0)
    assert task_pairs == {(card.item_id, image.item_id)}, f"Expected task_pairs, got {task_pairs}"

    # Verify Task 1: in gpu_checklist, suppressed_pairs should NOT include task_pairs
    from k_tools_kanvas.utils.checklist_links import attached_checklist_pairs
    from k_tools_kanvas.utils.gpu.gpu_checklist import _paint_target
    from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv
    arrow_pairs = attached_checklist_pairs(settings)
    assert (card.item_id, image.item_id) not in arrow_pairs

    # Verify that erased regions do NOT attract arrows:
    # Dab 1 is on nose (0.5, 0.5)
    # Add dab 2 on cheek (0.9, 0.5) which is closer to the card
    dab_cheek = paint1.dabs.add()
    dab_cheek.uv = (0.9, 0.5)
    dab_cheek.radius_uv = (0.05, 0.05)
    dab_cheek.uv_axis_x = (0.05, 0.0)
    dab_cheek.uv_axis_y = (0.0, 0.05)
    dab_cheek.sequence = 1
    image.markup_revision += 1

    target_before_erase = _paint_target(paint1, image, (600, 100))
    # Before erasing cheek, target is closest to cheek
    cheek_pt = image_point_from_uv(image, (0.9, 0.5))
    assert math.dist(target_before_erase, cheek_pt) < 1e-3, "Before erase, should point to cheek"

    # Now add an erase dab covering the cheek
    dab_erase = paint1.dabs.add()
    dab_erase.uv = (0.9, 0.5)
    dab_erase.radius_uv = (0.08, 0.08)
    dab_erase.uv_axis_x = (0.08, 0.0)
    dab_erase.uv_axis_y = (0.0, 0.08)
    dab_erase.erase = True
    dab_erase.sequence = 2
    image.markup_revision += 1

    target_after_erase = _paint_target(paint1, image, (600, 100))
    nose_pt = image_point_from_uv(image, (0.5, 0.5))
    # After erasing cheek, arrow MUST point to nose, NOT the erased cheek!
    assert math.dist(target_after_erase, nose_pt) < 1e-3, f"After erase, should point to nose, got {target_after_erase}"

    # Now erase the nose as well
    dab_erase_nose = paint1.dabs.add()
    dab_erase_nose.uv = (0.5, 0.5)
    dab_erase_nose.radius_uv = (0.15, 0.15)
    dab_erase_nose.uv_axis_x = (0.15, 0.0)
    dab_erase_nose.uv_axis_y = (0.0, 0.15)
    dab_erase_nose.erase = True
    dab_erase_nose.sequence = 3
    image.markup_revision += 1

    target_all_erased = _paint_target(paint1, image, (600, 100))
    assert target_all_erased is None, "When region is completely erased, target should be None"

    # Restore nose dab for remaining tests
    dab_restore = paint1.dabs.add()
    dab_restore.uv = (0.5, 0.5)
    dab_restore.radius_uv = (0.1, 0.1)
    dab_restore.uv_axis_x = (0.1, 0.0)
    dab_restore.uv_axis_y = (0.0, 0.1)
    dab_restore.sequence = 4
    image.markup_revision += 1

    # 2. Test Task 2: Mask-level Eyedropper (region_index_at_uv)
    # Add a second region
    paint2 = image.markup_regions.add()
    paint2.region_id = 'region-2'
    paint2.name = 'Item 2'
    paint2.color = (0.2, 0.8, 0.3)
    paint2.visible = True
    paint2.opacity = 0.5
    dab2 = paint2.dabs.add()
    dab2.uv = (0.8, 0.8)
    dab2.radius_uv = (0.08, 0.08)
    dab2.uv_axis_x = (0.08, 0.0)
    dab2.uv_axis_y = (0.0, 0.08)
    image.markup_revision += 1

    # Add a third region overlapping paint1 at (0.5, 0.5)
    paint3 = image.markup_regions.add()
    paint3.region_id = 'region-3'
    paint3.name = 'Item 3 (Top)'
    paint3.color = (0.1, 0.2, 0.9)
    paint3.visible = True
    paint3.opacity = 0.8
    dab3 = paint3.dabs.add()
    dab3.uv = (0.5, 0.5)
    dab3.radius_uv = (0.08, 0.08)
    dab3.uv_axis_x = (0.08, 0.0)
    dab3.uv_axis_y = (0.0, 0.08)
    image.markup_revision += 1

    # Test sampling at (0.8, 0.8) -> should hit paint2 (index 1)
    hit_idx = region_index_at_uv(image, (0.8, 0.8))
    assert hit_idx == 1, f"Expected index 1, got {hit_idx}"
    assert image.markup_regions[hit_idx].name == 'Item 2'

    # Test sampling at (0.5, 0.5) -> should hit paint3 (index 2, top-most layer)
    hit_top = region_index_at_uv(image, (0.5, 0.5))
    assert hit_top == 2, f"Expected index 2 (top-most), got {hit_top}"
    assert image.markup_regions[hit_top].name == 'Item 3 (Top)'

    # Test sampling when top-most is hidden -> should fall through to paint1 (index 0)
    paint3.visible = False
    image.markup_revision += 1
    hit_under = region_index_at_uv(image, (0.5, 0.5))
    assert hit_under == 0, f"Expected index 0 (underneath), got {hit_under}"

    # Test sampling on unpainted area (0.1, 0.1) -> should return None
    hit_none = region_index_at_uv(image, (0.1, 0.1))
    assert hit_none is None, f"Expected None on unpainted pixel, got {hit_none}"

    # Test sampling outside bounds -> should return None
    assert region_index_at_uv(image, (-0.2, 0.5)) is None
    assert region_index_at_uv(image, (1.5, 0.5)) is None
    assert region_index_at_uv(image, None) is None

    # Test that no new region is created
    initial_count = len(image.markup_regions)
    image.markup_active_index = hit_idx
    assert len(image.markup_regions) == initial_count, "No new color region should be added!"
    assert image.markup_active_index == 1

    # 3. Test Modal Operator: holding 'S', hovering, and clicking on a mask
    from k_tools_kanvas.operators.ops_markup import KANVAS_OT_EditColorMarkup, _MarkupEditProxy

    class Painter:
        modal = KANVAS_OT_EditColorMarkup.modal
        _switch_region = KANVAS_OT_EditColorMarkup._switch_region
        _commit_stroke = lambda self, itm: None
        _clear_line = lambda self: None
        _polygon_cancel = lambda self: None
        _rectangle_cancel = lambda self: None
        _palette_hit = lambda self, itm, ev: None
        _mouse_uv = lambda self, ev, itm: getattr(ev, 'uv', None)
        report = lambda self, type_set, msg: None

        def __init__(self, raw_item, area):
            self.raw_item = raw_item
            self._tree = tree
            self._item_id = raw_item.item_id
            self._area = area
            self._sample_held = False
            self._sample_hover_index = None
            self._sample_mouse = None
            self._last_region_index = 0

        def _item(self):
            return _MarkupEditProxy(self.raw_item)

        def _raw_item(self):
            return self.raw_item

    class MockContext:
        def __init__(self, area):
            self.area = area

    mock_context = MockContext(area)
    painter = Painter(image, area)
    image.markup_active_index = 0  # Start on index 0

    # Simulate pressing 'S'
    press_s = SimpleNamespace(type='S', value='PRESS', ctrl=False, alt=False,
                              mouse_x=100, mouse_y=100)
    painter.modal(mock_context, press_s)
    assert painter._sample_held is True, "Holding 'S' should activate _sample_held"

    # Simulate mouse move over (0.8, 0.8) which is paint2 (Item 2)
    # Mock _mouse_uv to return (0.8, 0.8)
    painter._mouse_uv = lambda event, itm: (0.8, 0.8)
    move_event = SimpleNamespace(type='MOUSEMOVE', value='NOTHING', ctrl=False, alt=False,
                                 mouse_x=200, mouse_y=200)
    painter.modal(mock_context, move_event)
    assert painter._sample_hover_index == 1, f"Expected hovered index 1, got {painter._sample_hover_index}"

    # Simulate left click on the hovered mask
    click_event = SimpleNamespace(type='LEFTMOUSE', value='PRESS', ctrl=False, alt=False,
                                  mouse_x=200, mouse_y=200)
    painter.modal(mock_context, click_event)
    assert image.markup_active_index == 1, f"Active index should switch to 1, got {image.markup_active_index}"
    assert len(image.markup_regions) == initial_count, "Should not add new regions on click!"

    # Simulate releasing 'S'
    release_s = SimpleNamespace(type='S', value='RELEASE', ctrl=False, alt=False,
                                mouse_x=200, mouse_y=200)
    painter.modal(mock_context, release_s)
    assert painter._sample_held is False, "Releasing 'S' should deactivate _sample_held"

    print("ALL EYEDROPPER & CHECKLIST LINK TESTS PASSED SUCCESSFULLY!")

finally:
    addon.unregister()
