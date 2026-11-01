"""Headless regression for image-instance mask storage and UV rasterization."""

import os
import sys
import uuid
import math

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import k_tools_kanvas
from k_tools_kanvas.utils.gpu.gpu_mask import rasterize_mask
from k_tools_kanvas.utils.arrow_geometry import image_uv_at, image_point_from_uv
from k_tools_kanvas.operators.ops_mask import round_brush_geometry
from k_tools_kanvas.operators import ops_mask


k_tools_kanvas.register()
tree = bpy.data.node_groups.new('Mask regression', 'KanvasNodeTree')
item = tree.kanvas_settings.images.add()
item.item_id = 'mask-regression-instance'
item.item_type = 'IMAGE'
item.image_data = bpy.data.images.new('Mask source', width=100, height=100)
item.mask_enabled = True
dab = item.mask_dabs.add()
dab.uv = (0.5, 0.5)
dab.radius_uv = (0.2, 0.2)
assert rasterize_mask(item.mask_dabs, 100, 100)[50, 50] == 1
assert rasterize_mask(item.mask_dabs, 100, 100)[10, 10] == 0
erase = item.mask_dabs.add()
erase.uv = (0.5, 0.5)
erase.radius_uv = (0.05, 0.05)
erase.erase = True
pixels = rasterize_mask(item.mask_dabs, 100, 100)
first_pass = rasterize_mask(item.mask_dabs[:1], 100, 100)
incremental = rasterize_mask(item.mask_dabs, 100, 100, first_pass, start=1)
assert (incremental == pixels).all()
assert pixels[50, 50] == 0
assert pixels[50, 60] == 1
item.location = (120.0, -45.0)
item.scale_xy = (1.5, 0.8)
item.rotation = 27.0
item.shear_xy = (0.15, -0.08)
item.flip_h = True
item.flip_v = True
for uv in ((0.1, 0.2), (0.5, 0.5), (0.9, 0.8)):
    point = image_point_from_uv(item, uv)
    recovered = image_uv_at(item, point)
    assert all(abs(a - b) < 1e-5 for a, b in zip(uv, recovered))

item.mask_brush_size = 15.0
radius, axis_x, axis_y = round_brush_geometry(item)
center = image_point_from_uv(item, (0.5, 0.5))
for axis in (axis_x, axis_y):
    endpoint = image_point_from_uv(item, (0.5 + axis[0], 0.5 + axis[1]))
    assert abs(math.dist(center, endpoint) - radius) < 1e-4
round_dab = item.mask_dabs.add()
round_dab.uv = (0.5, 0.5)
round_dab.uv_axis_x = axis_x
round_dab.uv_axis_y = axis_y
round_pixels = rasterize_mask(item.mask_dabs[2:], 100, 100)
for angle in (0, math.pi / 2, math.pi, math.pi * 1.5):
    for distance, expected in ((0.7, 1), (1.3, 0)):
        u = 0.5 + distance * (math.cos(angle) * axis_x[0] + math.sin(angle) * axis_y[0])
        v = 0.5 + distance * (math.cos(angle) * axis_x[1] + math.sin(angle) * axis_y[1])
        assert round_pixels[int(v * 100), int(u * 100)] == expected
tiny_dab = item.mask_dabs.add()
tiny_dab.uv = (0.5, 0.5)
tiny_dab.uv_axis_x = (1 / 8000, 0)
tiny_dab.uv_axis_y = (0, 1 / 8000)
assert rasterize_mask(item.mask_dabs[3:], 512, 512).sum() > 0
item.mask_dabs.remove(3)

second = tree.kanvas_settings.images.add()
second.item_id = 'other-image-instance'
second.item_type = 'IMAGE'
second.image_data = item.image_data
assert len(second.mask_dabs) == 0
assert not second.mask_enabled

filename = os.path.join(os.path.dirname(__file__), f'kanvas_image_mask_{uuid.uuid4().hex}.blend')
bpy.ops.wm.save_as_mainfile(filepath=filename)
bpy.ops.wm.open_mainfile(filepath=filename)
loaded_items = bpy.data.node_groups['Mask regression'].kanvas_settings.images
loaded = loaded_items[0]
assert loaded.mask_enabled
assert len(loaded.mask_dabs) == 3
assert tuple(round(x, 2) for x in loaded.mask_dabs[0].uv) == (0.5, 0.5)
assert loaded.mask_dabs[1].erase
assert tuple(loaded.mask_dabs[2].uv_axis_x) != (0.0, 0.0)
assert len(loaded_items[1].mask_dabs) == 0

class RemovedPainter:
    def _draw_cursor(self):
        raise ReferenceError('StructRNA of type KANVAS_OT_PaintImageMask has been removed')

loaded.mask_editing = True
state = {'painter': RemovedPainter(), 'tree': bpy.data.node_groups['Mask regression'],
         'item_id': loaded.item_id, 'handler': None}
ops_mask._active_painters.append(state)
ops_mask._draw_painter(state)
assert state not in ops_mask._active_painters
assert state['painter'] is None
assert not loaded.mask_editing
os.remove(filename)
print('MASK_REGRESSION_OK')
