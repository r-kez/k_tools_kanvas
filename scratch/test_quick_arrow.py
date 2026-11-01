"""Headless gestures for hold-to-draw arrows and paint-mode navigation."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_arrow import KANVAS_OT_QuickArrow
from k_tools_kanvas.operators.ops_mask import KANVAS_OT_PaintImageMask
from k_tools_kanvas.utils.arrow_geometry import (
    checklist_anchor_points, image_point_from_uv,
)
from k_tools_kanvas.utils.kanvas_data import get_settings


class QuickHarness:
    invoke = KANVAS_OT_QuickArrow.invoke
    modal = KANVAS_OT_QuickArrow.modal
    _current_arrow = KANVAS_OT_QuickArrow._current_arrow
    _cancel_current = KANVAS_OT_QuickArrow._cancel_current
    _finish = KANVAS_OT_QuickArrow._finish


class PaintHarness:
    modal = KANVAS_OT_PaintImageMask.modal
    _sam_ready = lambda self, item: False   # Auto Select is not set up in this test
    report = lambda self, *args, **kwargs: None
    _clear_line = KANVAS_OT_PaintImageMask._clear_line
    _in_canvas = KANVAS_OT_PaintImageMask._in_canvas
    _window_region = KANVAS_OT_PaintImageMask._window_region
    _zoom_from_drag = KANVAS_OT_PaintImageMask._zoom_from_drag

    def _commit_stroke(self, item):
        pass

    def _item(self):
        return self.item

    def _mouse_uv(self, event, item):
        return None

    def _pan_by(self, context, dx, dy):
        self.pan_calls.append((dx, dy))

    def _zoom_view(self, context, direction):
        self.zoom_calls.append(direction)


class View:
    def region_to_view(self, x, y):
        return x - 500.0, y - 500.0


class Area:
    regions = [SimpleNamespace(type='WINDOW', x=0, y=0, width=1000,
                               height=1000, view2d=View())]

    def tag_redraw(self):
        pass


def event(kind, x=0, y=0, value='PRESS', ctrl=False, alt=False, is_repeat=False,
          prev_x=None, prev_y=None, shift=False):
    return SimpleNamespace(type=kind, value=value, mouse_x=x + 500,
                           mouse_y=y + 500, ctrl=ctrl, alt=alt, shift=shift,
                           is_repeat=is_repeat,
                           mouse_prev_x=(x if prev_x is None else prev_x) + 500,
                           mouse_prev_y=(y if prev_y is None else prev_y) + 500)


addon.register()
try:
    settings = get_settings(bpy.context)
    settings.images.clear()
    settings.arrows.clear()
    card = settings.images.add()
    card.item_id = 'quick-card'
    card.item_type = 'TEXT'
    card.location = (-150, 50)
    card.text_checklist = True
    task = card.text_lines.add()
    task.line_id = 'quick-task'
    task.value = 'Review image'
    image = settings.images.add()
    image.item_id = 'quick-image'
    image.item_type = 'IMAGE'
    image.image_data = bpy.data.images.new('Quick arrow target', 100, 80)
    image.location = (150, 50)
    area = Area()
    context = SimpleNamespace(
        scene=SimpleNamespace(kanvas_settings=settings), area=area,
        window_manager=SimpleNamespace(modal_handler_add=lambda operator: None),
    )

    start = checklist_anchor_points(card)[1][2]
    end = image_point_from_uv(image, (0.0, 0.5))
    quick = QuickHarness()
    assert quick.invoke(context, event('A')) == {'RUNNING_MODAL'}
    assert settings.arrow_quick_active and settings.arrow_dragging
    assert 'PASS_THROUGH' in quick.modal(context, event('MOUSEMOVE', *start))
    assert settings.arrow_hover_item_id == card.item_id
    quick.modal(context, event('LEFTMOUSE', *start))
    assert len(settings.arrows) == 0
    quick.modal(context, event('MOUSEMOVE', *end))
    assert len(settings.arrows) == 1
    assert len(image.checklist_associations) == 0
    quick.modal(context, event('LEFTMOUSE', *end, value='RELEASE'))
    arrow = settings.arrows[0]
    assert arrow.start_item_id == card.item_id
    assert arrow.end_item_id == image.item_id
    assert len(image.checklist_associations) == 1
    assert image.checklist_associations[0].card_id == card.item_id
    assert len(image.markup_regions) == 1
    assert quick.modal(context, event('A', value='RELEASE')) == {'FINISHED'}
    assert not settings.arrow_quick_active and not settings.arrow_dragging

    free = QuickHarness()
    free.invoke(context, event('A'))
    assert 'PASS_THROUGH' in free.modal(context, event('MIDDLEMOUSE'))
    assert 'PASS_THROUGH' in free.modal(context, event('MOUSEMOVE'))
    assert 'PASS_THROUGH' in free.modal(context, event('MIDDLEMOUSE', value='RELEASE'))
    free.modal(context, event('LEFTMOUSE', -300, -200))
    free.modal(context, event('MOUSEMOVE', -150, -200))
    free.modal(context, event('LEFTMOUSE', -150, -200, 'RELEASE'))
    assert len(settings.arrows) == 2
    assert not settings.arrows[1].start_item_id
    assert not settings.arrows[1].end_item_id
    free.modal(context, event('A', value='RELEASE'))

    no_drag = QuickHarness()
    no_drag.invoke(context, event('A'))
    no_drag.modal(context, event('LEFTMOUSE', -300, -200))
    no_drag.modal(context, event('LEFTMOUSE', -300, -200, 'RELEASE'))
    assert len(settings.arrows) == 2
    no_drag.modal(context, event('A', value='RELEASE'))

    release_during_drag = QuickHarness()
    release_during_drag.invoke(context, event('A'))
    release_during_drag.modal(context, event('LEFTMOUSE', -300, -200))
    release_during_drag.modal(context, event('MOUSEMOVE', -240, -200))
    release_during_drag.modal(context, event('A', value='RELEASE'))
    assert settings.arrow_quick_active
    assert release_during_drag.modal(context, event('LEFTMOUSE', -200, -200, 'RELEASE')) == {'FINISHED'}
    assert len(settings.arrows) == 3

    cancel = QuickHarness()
    cancel.invoke(context, event('A'))
    cancel.modal(context, event('LEFTMOUSE', -300, -200))
    cancel.modal(context, event('MOUSEMOVE', -250, -200))
    assert len(settings.arrows) == 4
    cancel.modal(context, event('ESC'))
    assert len(settings.arrows) == 3

    paint = PaintHarness()
    paint.item = image
    paint._area = area
    paint._cursor_uv = None
    paint._last_uv = None
    paint._painting = False
    paint._nav_mode = None
    paint._nav_mouse = None
    paint._zoom_drag_pixels = 0.0
    paint._held_alt_keys = set()
    paint._alt_held = False
    paint._line_press_uv = None
    paint._line_start_uv = None
    paint._line_preview_uv = None
    paint._line_press_mouse = None
    paint._line_dragging = False
    paint.pan_calls = []
    paint.zoom_calls = []
    old_brush = image.mask_brush_size
    paint._painting = True
    assert 'PASS_THROUGH' not in paint.modal(context, event('MIDDLEMOUSE'))
    assert not paint._painting
    assert 'PASS_THROUGH' not in paint.modal(context, event('MOUSEMOVE', 20, 10))
    assert paint.pan_calls[-1] == (20, 10)
    assert 'PASS_THROUGH' not in paint.modal(context, event('MIDDLEMOUSE', value='RELEASE'))
    assert 'PASS_THROUGH' not in paint.modal(context, event('WHEELUPMOUSE'))
    assert 'PASS_THROUGH' not in paint.modal(context, event('WHEELINMOUSE'))
    assert 'PASS_THROUGH' not in paint.modal(context, event('WHEELOUTMOUSE'))
    assert paint.zoom_calls == [1, 1, -1]
    assert image.mask_brush_size == old_brush
    assert 'PASS_THROUGH' not in paint.modal(context, event('WHEELINMOUSE', ctrl=True))
    assert image.mask_brush_size > old_brush
    assert 'PASS_THROUGH' not in paint.modal(context, event('TRACKPADPAN', 10, 20, prev_x=4, prev_y=12))
    assert paint.pan_calls[-1] == (6, 8)
    assert 'PASS_THROUGH' not in paint.modal(context, event('MOUSEMOVE'))
    assert 'PASS_THROUGH' not in paint.modal(context, event('INBETWEEN_MOUSEMOVE'))
    assert 'PASS_THROUGH' in paint.modal(context, event('RIGHTMOUSE', alt=True))
    assert 'PASS_THROUGH' not in paint.modal(context, event('LEFT_ALT'))
    assert paint._alt_held and not image.mask_erase
    assert 'PASS_THROUGH' not in paint.modal(context, event('LEFT_ALT', is_repeat=True))
    assert paint._alt_held and not image.mask_erase
    assert 'PASS_THROUGH' not in paint.modal(context, event('LEFT_ALT', value='RELEASE'))
    assert not paint._alt_held and not image.mask_erase
    paint.modal(context, event('RIGHT_ALT'))
    assert paint._alt_held and not image.mask_erase
    assert 'PASS_THROUGH' not in paint.modal(context, event('A'))
    print('QUICK_ARROW_AND_MASK_NAVIGATION_OK')
finally:
    addon.unregister()
