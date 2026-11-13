"""Pencil Drawings stuck to an image: they follow its move, rotation and scale, can be
placed by hand, let go, and survive the image being deleted."""

import math
import sys
from pathlib import Path

import numpy as np
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import pencil, pencil_anchor

addon.register()
tree = bpy.data.node_groups.new('Anchor test', 'KanvasNodeTree')
settings = tree.kanvas_settings

picture = bpy.data.images.new('pic', 200, 100)
image = settings.images.add()
image.item_id, image.item_type, image.name = 'img', 'IMAGE', 'Picture'
image.image_data = picture
image.location = (1000.0, 500.0)

drawing = settings.images.add()
drawing.item_id, drawing.item_type, drawing.shape_kind = 'dr', 'SHAPE', 'PENCIL'
drawing.location = (1050.0, 520.0)
pencil.add_stroke(drawing, np.array([[1000.0, 500.0], [1100.0, 540.0]]), [1.0, 1.0],
                  (1, 0, 0), 6.0)


def stroke_points():
    return pencil.canvas_points_of(drawing, 0)


# hit test: the image covers its own rectangle, nothing outside it
assert pencil_anchor.image_under_point(settings, (1000.0, 500.0)).item_id == 'img'
assert pencil_anchor.image_under_point(settings, (1000.0, 600.0)) is None     # 100 high, centred at 500
assert pencil_anchor.image_under_point(settings, (1000.0, 549.0)).item_id == 'img'
assert pencil_anchor.image_under_point(settings, (5000.0, 5000.0)) is None

# loose by default: the image moves, the drawing stays
before = stroke_points().copy()
image.location = (1100.0, 500.0)
pencil_anchor.sync(settings)
assert np.allclose(stroke_points(), before, atol=1e-2)

# stuck: it follows a move
image.location = (1000.0, 500.0)
pencil_anchor.attach(drawing, image)
before = stroke_points().copy()
image.location = (1300.0, 400.0)
pencil_anchor.sync(settings)
assert np.allclose(stroke_points(), before + np.array([300.0, -100.0]), atol=1e-2), stroke_points()

# a rotation around the image's middle carries the strokes with it
start = stroke_points().copy()
middle = np.array(image.location[:2])
image.rotation = 90.0
pencil_anchor.sync(settings)
turned = stroke_points()
rotated = middle + (start - middle) @ np.array([[0.0, 1.0], [-1.0, 0.0]])   # +90 degrees
assert np.allclose(turned, rotated, atol=1e-2), (turned, rotated)
assert abs(drawing.rotation - 90.0) < 1e-3

# a scale about the middle too
start = stroke_points().copy()
image.scale_master = 2.0
pencil_anchor.sync(settings)
assert np.allclose(stroke_points(), middle + (start - middle) * 2.0, atol=1e-1)
assert abs(drawing.scale_master - 2.0) < 1e-4

# going back restores exactly
image.scale_master = 1.0
image.rotation = 0.0
image.location = (1000.0, 500.0)
pencil_anchor.sync(settings)
assert np.allclose(stroke_points(), np.array([[1000.0, 500.0], [1100.0, 540.0]]), atol=1e-1)

# syncing again changes nothing
before = stroke_points().copy()
pencil_anchor.sync(settings)
pencil_anchor.sync(settings)
assert np.allclose(stroke_points(), before, atol=1e-4)

# placing the drawing by hand keeps it stuck, from where it was put
drawing.location = (drawing.location[0] + 60.0, drawing.location[1])
pencil_anchor.sync(settings)
placed = stroke_points().copy()
assert drawing.anchor_item_id == 'img'
image.location = (1000.0, 700.0)
pencil_anchor.sync(settings)
assert np.allclose(stroke_points(), placed + np.array([0.0, 200.0]), atol=1e-2)

# a stroke added later (the box refits) does not break the tie
pencil.add_stroke(drawing, np.array([[1200.0, 800.0], [1250.0, 820.0]]), [1.0, 1.0],
                  (0, 0, 1), 6.0)
pencil_anchor.sync(settings)
second = pencil.canvas_points_of(drawing, 1).copy()
image.location = (1100.0, 700.0)
pencil_anchor.sync(settings)
assert np.allclose(pencil.canvas_points_of(drawing, 1), second + np.array([100.0, 0.0]), atol=1e-2)

# moving both together (a joint move) keeps the picture as it is
both = stroke_points().copy()
image.location = (image.location[0] + 50.0, image.location[1] + 50.0)
drawing.location = (drawing.location[0] + 50.0, drawing.location[1] + 50.0)
pencil_anchor.sync(settings)
assert np.allclose(stroke_points(), both + np.array([50.0, 50.0]), atol=1e-2)

# drawings_of lists the shown ones; hidden ones stay out
assert [d.item_id for d in pencil_anchor.drawings_of(settings, image)] == ['dr']
drawing.show_in_editor = False
assert pencil_anchor.drawings_of(settings, image) == []
drawing.show_in_editor = True

# detached: the image moves, the drawing stays
pencil_anchor.detach(drawing)
kept = stroke_points().copy()
image.location = (0.0, 0.0)
pencil_anchor.sync(settings)
assert np.allclose(stroke_points(), kept, atol=1e-2)

# the image deleted: the tie is dropped and nothing breaks
image.location = (1000.0, 500.0)
pencil_anchor.attach(drawing, image)
settings.images.remove(next(i for i, item in enumerate(settings.images) if item.item_id == 'img'))
pencil_anchor.sync(settings)
drawing = next(item for item in settings.images if item.item_id == 'dr')
assert drawing.anchor_item_id == ''

addon.unregister()
print('test_pencil_anchor: OK')
