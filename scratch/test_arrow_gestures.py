"""Exercise arrow placement, endpoint dragging, and cancellation."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.preferences import KanvasPreferences
from k_tools_kanvas.operators.ops_arrow import (
    KANVAS_OT_CreateArrow, KANVAS_OT_DragArrow,
)
from k_tools_kanvas.utils.arrow_geometry import (
    checklist_anchor_points, curve_midpoint, hit_arrow,
    image_point_from_uv, text_anchor_points,
)
from k_tools_kanvas.utils.checklist_links import attached_checklist_pairs
from k_tools_kanvas.operators.ops_checklist import associate_arrow_endpoints


class CreateHarness:
    invoke = KANVAS_OT_CreateArrow.invoke
    modal = KANVAS_OT_CreateArrow.modal
    cancel = KANVAS_OT_CreateArrow.cancel


class DragHarness:
    invoke = KANVAS_OT_DragArrow.invoke
    modal = KANVAS_OT_DragArrow.modal
    _finish = KANVAS_OT_DragArrow._finish


class View:
    def region_to_view(self, x, y):
        return x - 500.0, y - 500.0


class Area:
    regions = [SimpleNamespace(type='WINDOW', x=0, y=0, width=1000,
                               height=1000, view2d=View())]

    def tag_redraw(self):
        pass


def event(kind, x, y, value='PRESS'):
    return SimpleNamespace(type=kind, value=value, mouse_x=x + 500,
                           mouse_y=y + 500)


addon.register()
try:
    assert tuple(KanvasPreferences.bl_rna.properties[
        'color_arrow_curve_handle'].default_array) == (1.0, 1.0, 1.0, 1.0)
    assert tuple(KanvasPreferences.bl_rna.properties[
        'color_arrow_endpoint_handles'].default_array) == (1.0, 1.0, 1.0, 1.0)
    settings = get_settings(bpy.context)
    image = settings.images.add()
    image.item_id = 'image'
    image.item_type = 'IMAGE'
    image.image_data = bpy.data.images.new('Arrow gesture image', 100, 80)
    image.location = (100, 50)
    card = settings.images.add()
    card.item_id = 'card'
    card.item_type = 'TEXT'
    card.location = (-150, 50)

    context = SimpleNamespace(
        scene=SimpleNamespace(kanvas_settings=settings),
        area=Area(),
        window_manager=SimpleNamespace(modal_handler_add=lambda operator: None),
    )
    start = text_anchor_points(card)[1][1]
    end = image_point_from_uv(image, (0.7, 0.4))
    create = CreateHarness()
    assert create.invoke(context, event('NONE', 0, 0)) == {'RUNNING_MODAL'}
    assert create.modal(context, event('LEFTMOUSE', *start)) == {'RUNNING_MODAL'}
    assert create.modal(context, event('MOUSEMOVE', *end)) == {'RUNNING_MODAL'}
    assert create.modal(context, event('LEFTMOUSE', *end)) == {'FINISHED'}
    arrow = settings.arrows[0]
    arrow.label = 'Reference flow'
    assert arrow.label == 'Reference flow'
    assert arrow.start_item_id == card.item_id
    assert arrow.end_item_id == image.item_id
    assert not settings.arrow_dragging

    drag = DragHarness()
    drag.arrow_index = 0
    drag.part = 'end'
    assert drag.invoke(context, event('LEFTMOUSE', *end)) == {'RUNNING_MODAL'}
    assert drag.modal(context, event('MOUSEMOVE', 250, 250)) == {'RUNNING_MODAL'}
    assert drag.modal(context, event('LEFTMOUSE', 250, 250, 'RELEASE')) == {'FINISHED'}
    assert not arrow.end_item_id
    assert tuple(arrow.end) == (250, 250)

    middle = curve_midpoint(settings, arrow)
    assert hit_arrow(settings, middle, 1.0) == (0, 'curve')
    bend = DragHarness()
    bend.arrow_index = 0
    bend.part = 'curve'
    assert bend.invoke(context, event('LEFTMOUSE', *middle)) == {'RUNNING_MODAL'}
    assert bend.modal(context, event('MOUSEMOVE', middle[0], middle[1] + 60)) == {'RUNNING_MODAL'}
    assert tuple(arrow.curve_offset) == (0, 60)
    assert bend.modal(context, event('LEFTMOUSE', middle[0], middle[1] + 60,
                                     'RELEASE')) == {'FINISHED'}
    assert curve_midpoint(settings, arrow)[1] == middle[1] + 60

    middle = curve_midpoint(settings, arrow)
    cancelled_bend = DragHarness()
    cancelled_bend.arrow_index = 0
    cancelled_bend.part = 'curve'
    assert cancelled_bend.invoke(context, event('LEFTMOUSE', *middle)) == {'RUNNING_MODAL'}
    cancelled_bend.modal(context, event('MOUSEMOVE', middle[0] + 40, middle[1]))
    assert cancelled_bend.modal(context, event('ESC', *middle)) == {'CANCELLED'}
    assert tuple(arrow.curve_offset) == (0, 60)

    cancelled = CreateHarness()
    cancelled.invoke(context, event('NONE', 0, 0))
    assert cancelled.modal(context, event('ESC', 0, 0)) == {'CANCELLED'}
    assert len(settings.arrows) == 1

    # Completing a dragged endpoint creates a checklist link once.
    card.text_checklist = True
    task = card.text_lines.add()
    task.line_id = 'arrow-task'
    task.value = 'Review'
    assert not image.checklist_associations
    reattach = DragHarness()
    reattach.arrow_index = 0
    reattach.part = 'end'
    target = image_point_from_uv(image, (0.7, 0.4))
    assert reattach.invoke(context, event('LEFTMOUSE', 250, 250)) == {'RUNNING_MODAL'}
    assert reattach.modal(context, event('MOUSEMOVE', *target)) == {'RUNNING_MODAL'}
    assert not image.checklist_associations
    assert reattach.modal(context, event('LEFTMOUSE', *target, 'RELEASE')) == {'FINISHED'}
    assert len(image.checklist_associations) == 1
    assert image.checklist_associations[0].card_id == card.item_id
    assert len(image.markup_regions) == 1
    assert attached_checklist_pairs(settings) == {(card.item_id, image.item_id)}

    reverse_image = settings.images.add()
    reverse_image.item_id = 'reverse-image'
    reverse_image.item_type = 'IMAGE'
    reverse_image.image_data = bpy.data.images.new('Reverse arrow image', 100, 80)
    reverse_image.location = (250, -150)
    reverse_start = image_point_from_uv(reverse_image, (0.0, 0.5))
    reverse_end = checklist_anchor_points(card)[1][2]
    reverse = CreateHarness()
    assert reverse.invoke(context, event('NONE', 0, 0)) == {'RUNNING_MODAL'}
    assert reverse.modal(context, event('LEFTMOUSE', *reverse_start)) == {'RUNNING_MODAL'}
    assert reverse.modal(context, event('MOUSEMOVE', *reverse_end)) == {'RUNNING_MODAL'}
    assert not reverse_image.checklist_associations
    assert reverse.modal(context, event('LEFTMOUSE', *reverse_end)) == {'FINISHED'}
    assert len(reverse_image.checklist_associations) == 1
    assert len(reverse_image.markup_regions) == 1
    assert attached_checklist_pairs(settings) == {
        (card.item_id, image.item_id), (card.item_id, reverse_image.item_id)}
    assert not associate_arrow_endpoints(settings, settings.arrows[-1])
    assert len(reverse_image.markup_regions) == 1
    settings.arrows.remove(len(settings.arrows) - 1)
    assert len(reverse_image.checklist_associations) == 1
    assert attached_checklist_pairs(settings) == {(card.item_id, image.item_id)}
    print('ARROW GESTURES PASS')
finally:
    addon.unregister()
