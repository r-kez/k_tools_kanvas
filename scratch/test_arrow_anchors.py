"""Smoke test arrow placement and content-relative attachment in Blender."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas import ui
from k_tools_kanvas.utils.arrow_geometry import (
    anchor_candidate, endpoint, hit_arrow,
    image_anchor_points, image_point_from_uv, image_uv_at,
    set_endpoint, text_anchor_points,
)


def close_point(actual, expected):
    assert all(math.isclose(a, b, abs_tol=1e-4)
               for a, b in zip(actual, expected)), (actual, expected)


class Layout:
    def __init__(self):
        self.properties = []

    def row(self, **kwargs):
        return self

    def column(self, **kwargs):
        return self

    def box(self):
        return self

    def label(self, **kwargs):
        pass

    def separator(self):
        pass

    def template_list(self, *args, **kwargs):
        pass

    def prop(self, owner, name, **kwargs):
        self.properties.append(name)

    def operator(self, *args, **kwargs):
        return SimpleNamespace()


addon.register()
try:
    scene = bpy.context.scene
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    area.spaces.active.node_tree = bpy.data.node_groups.new('Arrows', 'KanvasNodeTree')
    settings = area.spaces.active.edit_tree.kanvas_settings
    image = settings.images.add()
    image.item_id = 'test-image'
    image.item_type = 'IMAGE'
    image.image_data = bpy.data.images.new('Arrow image', 100, 80)
    image.location = (100, 50)
    note = settings.images.add()
    note.item_id = 'test-card'
    note.item_type = 'TEXT'
    note.location = (-150, 50)

    with bpy.context.temp_override(area=area, space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_arrow('EXEC_DEFAULT') == {'FINISHED'}
    assert len(settings.arrows) == 1
    arrow = settings.arrows[0]
    layout = Layout()
    ui.KANVAS_PT_ItemsPanel.draw(SimpleNamespace(layout=layout),
                                 SimpleNamespace(scene=scene,
                                                 space_data=area.spaces.active,
                                                 tool_settings=scene.tool_settings))
    assert 'color' in layout.properties and 'thickness' in layout.properties
    card_uv, card_point = text_anchor_points(note)[1]
    set_endpoint(arrow, 'start', card_point,
                 (note.item_id, card_uv, card_point))
    image_point = image_point_from_uv(image, (0.72, 0.35))
    candidate = anchor_candidate(settings, image_point, 1.0)
    assert candidate and candidate[0] == image.item_id
    set_endpoint(arrow, 'end', candidate[2], candidate)
    close_point(endpoint(settings, arrow, 'end'), image_point)
    assert hit_arrow(settings, image_point, 1.0) == (0, 'end')

    image.location = (260, -40)
    image.scale_master = 1.6
    image.scale_xy = (1.2, 0.8)
    image.shear_xy = (0.1, -0.05)
    image.rotation = 37
    close_point(endpoint(settings, arrow, 'end'),
                image_point_from_uv(image, candidate[1]))
    close_point(image_uv_at(image, endpoint(settings, arrow, 'end')),
                candidate[1])
    image.flip_h = True
    image.flip_v = True
    close_point(endpoint(settings, arrow, 'end'),
                image_point_from_uv(image, candidate[1]))
    anchors = image_anchor_points(image)
    assert len(anchors) == 8
    center = tuple(image.location)
    for uv, anchor in anchors:
        direction = (anchor[0] - center[0], anchor[1] - center[1])
        distance = math.hypot(*direction)
        outside = (anchor[0] + direction[0] * 10.0 / distance,
                   anchor[1] + direction[1] * 10.0 / distance)
        snapped = anchor_candidate(settings, outside, 1.0)
        assert snapped and snapped[0] == image.item_id
        close_point(snapped[1], uv)
        close_point(snapped[2], anchor)

    note.location = (-250, -70)
    note.text_scale = 1.4
    close_point(endpoint(settings, arrow, 'start'),
                text_anchor_points(note)[1][1])
    frozen = endpoint(settings, arrow, 'end')
    with bpy.context.temp_override(area=area, space_data=area.spaces.active):
        assert bpy.ops.kanvas.remove_image('EXEC_DEFAULT', index=0) == {'FINISHED'}
    assert not arrow.end_item_id
    close_point(endpoint(settings, arrow, 'end'), frozen)
    print('ARROW ANCHORS PASS')
finally:
    addon.unregister()
