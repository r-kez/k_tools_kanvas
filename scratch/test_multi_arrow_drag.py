"""Move and cancel two selected arrows as one gesture."""

from pathlib import Path
from types import SimpleNamespace
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_arrow import KANVAS_OT_DragArrow
from k_tools_kanvas.properties import suspend_selection_updates
from k_tools_kanvas.utils.kanvas_data import get_settings


class DragHarness:
    invoke = KANVAS_OT_DragArrow.invoke
    modal = KANVAS_OT_DragArrow.modal
    _finish = KANVAS_OT_DragArrow._finish


class View:
    def region_to_view(self, x, y):
        return x - 500, y - 500


class Area:
    regions = [SimpleNamespace(type='WINDOW', x=0, y=0, width=1000,
                               height=1000, view2d=View())]

    def tag_redraw(self):
        pass


def event(kind, x, y, value='PRESS'):
    return SimpleNamespace(type=kind, value=value, mouse_x=x + 500, mouse_y=y + 500)


addon.register()
try:
    settings = get_settings(bpy.context)
    for y in (0, 100):
        arrow = settings.arrows.add()
        arrow.start = (0, y)
        arrow.end = (80, y)
        arrow.is_selected = True
    context = SimpleNamespace(
        scene=SimpleNamespace(kanvas_settings=settings),
        area=Area(),
        window_manager=SimpleNamespace(modal_handler_add=lambda operator: None),
    )
    with suspend_selection_updates():
        settings.active_arrow_index = 0

    drag = DragHarness()
    drag.arrow_index = 0
    drag.part = 'body'
    assert drag.invoke(context, event('LEFTMOUSE', 40, 0)) == {'RUNNING_MODAL'}
    assert drag.modal(context, event('MOUSEMOVE', 60, 20)) == {'RUNNING_MODAL'}
    assert [tuple(arrow.start) for arrow in settings.arrows] == [(20, 20), (20, 120)]
    assert drag.modal(context, event('ESC', 60, 20)) == {'CANCELLED'}
    assert [tuple(arrow.start) for arrow in settings.arrows] == [(0, 0), (0, 100)]

    drag = DragHarness()
    drag.arrow_index = 0
    drag.part = 'body'
    assert drag.invoke(context, event('LEFTMOUSE', 40, 0)) == {'RUNNING_MODAL'}
    assert drag.modal(context, event('MOUSEMOVE', 60, 20)) == {'RUNNING_MODAL'}
    assert drag.modal(context, event('LEFTMOUSE', 60, 20, 'RELEASE')) == {'FINISHED'}
    assert [tuple(arrow.start) for arrow in settings.arrows] == [(20, 20), (20, 120)]

    image = settings.images.add()
    image.item_id = 'mixed-image'
    image.item_type = 'IMAGE'
    image.image_data = bpy.data.images.new('Mixed move', 20, 20)
    image.location = (300, 300)
    image.is_selected = True
    settings.arrows[0].start_item_id = image.item_id
    settings.arrows[0].start_uv = (0.5, 0.5)
    drag = DragHarness()
    drag.arrow_index = 0
    drag.part = 'body'
    assert drag.invoke(context, event('LEFTMOUSE', 60, 20)) == {'RUNNING_MODAL'}
    assert drag.modal(context, event('MOUSEMOVE', 80, 40)) == {'RUNNING_MODAL'}
    assert tuple(image.location) == (320, 320)
    assert settings.arrows[0].start_item_id == image.item_id
    assert tuple(settings.arrows[1].start) == (40, 140)
    assert drag.modal(context, event('ESC', 80, 40)) == {'CANCELLED'}
    assert tuple(image.location) == (300, 300)
    assert settings.arrows[0].start_item_id == image.item_id
    assert tuple(settings.arrows[1].start) == (20, 120)
    drag = DragHarness()
    drag.arrow_index = 0
    drag.part = 'body'
    assert drag.invoke(context, event('LEFTMOUSE', 60, 20)) == {'RUNNING_MODAL'}
    assert drag.modal(context, event('MOUSEMOVE', 80, 40)) == {'RUNNING_MODAL'}
    assert drag.modal(context, event('LEFTMOUSE', 80, 40, 'RELEASE')) == {'FINISHED'}
    assert tuple(image.location) == (320, 320)
    assert settings.arrows[0].start_item_id == image.item_id
    assert tuple(settings.arrows[1].start) == (40, 140)
    print('MULTI ARROW DRAG PASS')
finally:
    addon.unregister()
