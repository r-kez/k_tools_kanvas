"""Check checklist ordering keeps each task's state and arrow identity."""

import sys
from pathlib import Path

import bpy
import gpu

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.gpu.gpu_text import text_edit_button_bounds, draw_text_edit_button
from k_tools_kanvas.utils.gpu.gpu_image import get_icon_texture


addon.register()
try:
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Checklist order test', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(region for region in area.regions if region.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_text(location=(0, 0), checklist=True) == {'FINISHED'}
        card = settings.images[settings.active_image_index]
        card.text_lines[0].value = 'zebra'
        card.text_lines[0].done = True
        for label in ('apple', 'Banana'):
            assert bpy.ops.kanvas.add_text_line() == {'FINISHED'}
            card.text_lines[-1].value = label
        original_ids = {line.value: line.line_id for line in card.text_lines}
        arrow = settings.arrows.add()
        arrow.start_line_id = original_ids['zebra']

        assert bpy.ops.kanvas.move_checklist_task(index=2, direction=-1) == {'FINISHED'}
        assert [line.value for line in card.text_lines] == ['zebra', 'Banana', 'apple']
        assert bpy.ops.kanvas.sort_checklist(mode='ALPHA_ASC') == {'FINISHED'}
        assert [line.value for line in card.text_lines] == ['apple', 'Banana', 'zebra']
        assert bpy.ops.kanvas.sort_checklist(mode='OPEN_FIRST') == {'CANCELLED'}
        assert [line.value for line in card.text_lines] == ['apple', 'Banana', 'zebra']
        assert bpy.ops.kanvas.sort_checklist(mode='DONE_FIRST') == {'FINISHED'}
        assert [line.value for line in card.text_lines] == ['zebra', 'apple', 'Banana']
        assert bpy.ops.kanvas.sort_checklist(mode='ALPHA_DESC') == {'FINISHED'}
        assert [line.value for line in card.text_lines] == ['zebra', 'Banana', 'apple']
        assert all(line.line_id == original_ids[line.value] for line in card.text_lines)
        assert card.text_lines[0].done and arrow.start_line_id == card.text_lines[0].line_id

        class View:
            def __init__(self, scale):
                self.scale = scale

            def view_to_region(self, x, y, clip=False):
                return x * self.scale, y * self.scale

        class Region:
            def __init__(self, scale):
                self.view2d = View(scale)

        full = text_edit_button_bounds(card, Region(1))
        close = text_edit_button_bounds(card, Region(8))
        far = text_edit_button_bounds(card, Region(0.25))
        assert full and close and far
        assert full[2] - full[0] == 18
        assert close[2] - close[0] == 144
        assert far[2] - far[0] == 4.5
        assert text_edit_button_bounds(card, Region(0.1)) is None
        card.text_font_size = 72
        large_header_button = text_edit_button_bounds(card, Region(1))
        assert large_header_button[2] - large_header_button[0] == 72
        if hasattr(gpu, 'init'):
            gpu.init()
            offscreen = gpu.types.GPUOffScreen(512, 512)
            try:
                with offscreen.bind():
                    gpu.state.viewport_set(0, 0, 512, 512)
                    draw_text_edit_button(card, Region(1))
                    assert get_icon_texture('pencil') is not None
            finally:
                offscreen.free()
        print('CHECKLIST_ORDER_OK')
finally:
    addon.unregister()
