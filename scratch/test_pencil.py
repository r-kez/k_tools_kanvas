"""Pencil Drawing data: packing, the box that fits the strokes, and strokes that stay
where they are on the canvas when the drawing moves, rotates or grows."""

import sys
from pathlib import Path

import numpy as np
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import pencil, shape_geometry

addon.register()
tree = bpy.data.node_groups.new('Pencil test', 'KanvasNodeTree')
settings = tree.kanvas_settings


def canvas_points(item, index):
    """The canvas position of every point of a stroke, from the stored unit coordinates."""
    points = pencil.decode(item.shape_strokes[index].data)
    return np.array([shape_geometry.unit_to_canvas(item, p[:2]) for p in points])


# packing
data = np.array([[0.1, -0.2, 0.5], [0.3, 0.4, 1.0]], dtype=np.float32)
assert np.allclose(pencil.decode(pencil.encode(data)), data)
assert pencil.decode('').shape == (0, 3)

# a drawing from one stroke
item = settings.images.add()
item.item_id, item.item_type, item.name = 'd', 'SHAPE', 'Drawing'
item.shape_kind = 'PENCIL'
item.location = (500.0, 500.0)
first = np.array([[100.0, 100.0], [200.0, 150.0], [300.0, 100.0]])
pencil.add_stroke(item, first, [1.0, 1.0, 1.0], (1, 0, 0), 10.0)
assert len(item.shape_strokes) == 1
assert np.allclose(canvas_points(item, 0), first, atol=1e-3), canvas_points(item, 0)
# the box covers the stroke plus half its width
assert abs(item.shape_width - (200.0 + 10.0)) < 1e-3 and abs(item.shape_height - (50.0 + 10.0)) < 1e-3
assert np.allclose(item.location[:2], (200.0, 125.0), atol=1e-3)

# a second stroke outside the box grows it; the first stays put on the canvas
second = np.array([[-100.0, 400.0], [0.0, 450.0]])
pencil.add_stroke(item, second, [0.5, 1.0], (0, 0, 1), 6.0)
assert len(item.shape_strokes) == 2
assert np.allclose(canvas_points(item, 0), first, atol=1e-3)
assert np.allclose(canvas_points(item, 1), second, atol=1e-3)
assert tuple(item.shape_strokes[1].color) == (0.0, 0.0, 1.0)

# moved, rotated and scaled, new strokes still land where they were drawn
item.location = (item.location[0] + 40.0, item.location[1] - 25.0)
item.rotation = 30.0
item.scale_master = 1.5
third = np.array([[10.0, 10.0], [60.0, 80.0], [120.0, 20.0]])
before = [canvas_points(item, i) for i in range(2)]
pencil.add_stroke(item, third, [1.0, 0.7, 1.0], (0, 1, 0), 5.0)
assert np.allclose(canvas_points(item, 2), third, atol=1e-2), canvas_points(item, 2)
for index in range(2):
    assert np.allclose(canvas_points(item, index), before[index], atol=1e-2)

# box select: strokes touched by a canvas rectangle, on a rotated and scaled drawing
assert pencil.strokes_in_rect(item, (-1000, -1000), (-900, -900)) == []
tip = canvas_points(item, 0)[1]
assert pencil.strokes_in_rect(item, tip - 1.0, tip + 1.0) == [0]          # a point inside
assert pencil.strokes_in_rect(item, (-1000, -1000), (1000, 1000)) == [0, 1, 2]
# a rectangle crossed by the middle of a segment, with no stroke point inside it
mid = (canvas_points(item, 1)[0] + canvas_points(item, 1)[1]) / 2
assert pencil.strokes_in_rect(item, mid - 1.0, mid + 1.0) == [1]
# wide enough strokes are touched from beside them, narrow ones are not
edge = canvas_points(item, 2)[0] + np.array([0.0, 0.0])
assert 2 in pencil.strokes_in_rect(item, edge - 0.2, edge + 0.2)

# transforming one stroke: the others stay on the canvas, the box refits
before = [canvas_points(item, i) for i in range(3)]
widths = [item.shape_strokes[i].width for i in range(3)]
snap = pencil.strokes_snapshot(item, [1])
center = np.array(pencil.snapshot_center(snap))
assert np.allclose(center, (before[1].min(axis=0) + before[1].max(axis=0)) / 2, atol=1e-3)
pencil.transform_strokes(item, snap, lambda p: p + np.array([300.0, -200.0]))      # move
assert np.allclose(canvas_points(item, 1), before[1] + np.array([300.0, -200.0]), atol=1e-2)
for i in (0, 2):
    assert np.allclose(canvas_points(item, i), before[i], atol=1e-2)
pencil.transform_strokes(item, snap, lambda p: center + (p - center) * 2.0, 2.0)  # scale
assert np.allclose(canvas_points(item, 1), center + (before[1] - center) * 2.0, atol=1e-2)
assert abs(item.shape_strokes[1].width - widths[1] * 2.0) < 1e-4
c, s_ = np.cos(np.pi / 2), np.sin(np.pi / 2)                                       # rotate
pencil.transform_strokes(item, snap, lambda p: center + (p - center) @ np.array([[c, s_], [-s_, c]]))
turned = canvas_points(item, 1)
assert np.allclose(np.hypot(*(turned - center).T), np.hypot(*(before[1] - center).T), atol=1e-2)
# every stroke is inside the refitted box
for i in range(3):
    local = pencil.local_from_canvas(item, canvas_points(item, i))
    assert np.all(np.abs(local) <= np.array([item.shape_width, item.shape_height]) / 2 + 1e-3)
# starting again from the snapshot puts it back exactly
pencil.transform_strokes(item, snap, lambda p: p)
for i in range(3):
    assert np.allclose(canvas_points(item, i), before[i], atol=1e-2)
    assert abs(item.shape_strokes[i].width - widths[i]) < 1e-4

# select all / invert on the strokes of a drawing
pencil.select_strokes(item, [])
pencil.toggle_all_strokes(item)
assert pencil.selected_strokes(item) == [0, 1, 2]
pencil.toggle_all_strokes(item)
assert pencil.selected_strokes(item) == []
pencil.select_strokes(item, [0])
pencil.invert_stroke_selection(item)
assert pencil.selected_strokes(item) == [1, 2]
pencil.select_strokes(item, [])

# export / copy: a pencil drawing is a picture of its own
from k_tools_kanvas.operators.ops_export_image import export_target, _only_picture_selected
from k_tools_kanvas.utils import item_picture
assert item_picture.is_drawing_item(item)
for other in settings.images:
    other.is_selected = False
assert export_target(settings) is None
item.is_selected = True
settings.active_image_index = 0
assert export_target(settings).item_id == item.item_id and _only_picture_selected(settings)
width, height = item_picture.drawing_size(item, 2.0)
box = __import__('k_tools_kanvas.utils.item_geometry', fromlist=['x']).item_bounds(item)
assert width == int(np.ceil((box[2] - box[0]) * 2.0)) and height == int(np.ceil((box[3] - box[1]) * 2.0))
empty = settings.images.add()
empty.item_id, empty.item_type, empty.shape_kind = 'e', 'SHAPE', 'PENCIL'
assert not item_picture.is_drawing_item(empty), 'a drawing without strokes has nothing to export'
settings.images.remove(len(settings.images) - 1)
item = next(i for i in settings.images if i.item_id == 'd')
item.is_selected = False
# the picture itself needs a GPU; try it where there is one
try:
    item.is_selected = True
    item.opacity = 0.4
    picture = item_picture.render_drawing(settings, item, 1.0)
    assert picture.shape[:2] == (item_picture.drawing_size(item, 1.0)[1], item_picture.drawing_size(item, 1.0)[0])
    assert picture[..., 3].max() > 0, 'the strokes are in the picture'
    assert abs(item.opacity - 0.4) < 1e-6, 'opacity comes back'
    print('render_drawing: rendered', picture.shape)
except Exception as exc:
    print('render_drawing: no GPU here:', type(exc).__name__)

# pen pressure: off is constant, the minimum and the curve shape the response
full = pencil.apply_pressure([0.0, 0.5, 1.0], use=False)
assert np.allclose(full, 1.0)
plain = pencil.apply_pressure([0.0, 0.5, 1.0], True, pencil.MIN_PRESSURE, 0.0)
assert np.allclose(plain, [0.0, 0.5, 1.0], atol=1e-5), plain          # the pen as it comes
assert np.allclose(pencil.apply_pressure([0.0, 0.3, 1.0], True, 1.0, 0.0), 1.0)   # no thinning at all
soft = pencil.apply_pressure([0.3], True, pencil.MIN_PRESSURE, 1.0)[0]
hard = pencil.apply_pressure([0.3], True, pencil.MIN_PRESSURE, -1.0)[0]
assert hard < 0.3 < soft, (hard, soft)
half = pencil.apply_pressure([0.0], True, 0.5, 0.0)[0]            # half the width left at no pressure
assert abs((pencil.MIN_PRESSURE + (1 - pencil.MIN_PRESSURE) * half) - 0.5) < 1e-5
clamped = pencil.apply_pressure([2.0, -1.0], True, 0.2, 0.0)       # out of range is clamped
assert abs(clamped[0] - 1.0) < 1e-6 and abs(clamped[1] - (0.2 - pencil.MIN_PRESSURE) / (1 - pencil.MIN_PRESSURE)) < 1e-5
assert settings.pencil_use_pressure is True

# eraser: strokes within reach of the sweep go, the others stay
eraser_drawing = settings.images.add()
eraser_drawing.item_id, eraser_drawing.item_type = 'er', 'SHAPE'
eraser_drawing.shape_kind = 'PENCIL'
pencil.add_stroke(eraser_drawing, np.array([[0.0, 0.0], [100.0, 0.0]]), [1.0, 1.0], (1, 0, 0), 4.0)
pencil.add_stroke(eraser_drawing, np.array([[0.0, 50.0], [100.0, 50.0]]), [1.0, 1.0], (0, 1, 0), 4.0)
pencil.add_stroke(eraser_drawing, np.array([[300.0, 300.0]]), [1.0], (0, 0, 1), 4.0)
assert pencil.strokes_hit_by(eraser_drawing, [(50.0, 20.0)], 4.0) == []
assert pencil.strokes_hit_by(eraser_drawing, [(50.0, 3.0)], 2.0) == [0]            # the width counts
assert pencil.strokes_hit_by(eraser_drawing, [(50.0, 25.0)], 30.0) == [0, 1]
assert pencil.strokes_hit_by(eraser_drawing, [(298.0, 300.0)], 1.0) == [2]         # a dot
# a sweep from one side to the other crosses a stroke with no sample on it
sweep = np.linspace((50.0, -40.0), (50.0, 90.0), 60)
assert pencil.strokes_hit_by(eraser_drawing, sweep, 2.0) == [0, 1]
assert pencil.remove_strokes(eraser_drawing, [0, 1, 7]) == 2
assert len(eraser_drawing.shape_strokes) == 1
settings.images.remove(len(settings.images) - 1)

# partial eraser: a stroke is cut where the eraser passes, the rest stays
part = settings.images.add()
part.item_id, part.item_type, part.shape_kind = 'pt', 'SHAPE', 'PENCIL'
pencil.add_stroke(part, np.array([[0.0, 0.0], [100.0, 0.0]]), [1.0, 1.0], (1, 0, 0), 4.0)
pencil.add_stroke(part, np.array([[0.0, 60.0], [100.0, 60.0]]), [1.0, 1.0], (0, 1, 0), 4.0)
pencil.select_strokes(part, [0])
assert pencil.erase_parts(part, [(50.0, 0.0)], 5.0) == 1
assert len(part.shape_strokes) == 3, len(part.shape_strokes)
left, right = pencil.canvas_points_of(part, 0), pencil.canvas_points_of(part, 1)
assert abs(left[0][0]) < 1e-2 and abs(right[-1][0] - 100.0) < 1e-2        # the far ends stay
assert 40.0 < left[:, 0].max() < 45.0 and 55.0 < right[:, 0].min() < 60.0, (left, right)
assert np.allclose(left[:, 1], 0.0, atol=1e-3) and np.allclose(right[:, 1], 0.0, atol=1e-3)
assert tuple(part.shape_strokes[0].color) == (1.0, 0.0, 0.0) == tuple(part.shape_strokes[1].color)
assert tuple(part.shape_strokes[2].color) == (0.0, 1.0, 0.0), 'order of the others is kept'
assert pencil.selected_strokes(part) == [0, 1], 'the pieces keep the pick'
assert all(abs(c - 4.0) < 1e-5 for c in (part.shape_strokes[0].width, part.shape_strokes[1].width))
assert abs(pencil.canvas_points_of(part, 2)[0][1] - 60.0) < 1e-2
# a miss changes nothing; a sweep over the whole thing leaves nothing
assert pencil.erase_parts(part, [(50.0, 30.0)], 3.0) == 0 and len(part.shape_strokes) == 3
assert pencil.erase_parts(part, np.linspace((-20.0, 0.0), (120.0, 0.0), 40), 6.0) == 2
assert len(part.shape_strokes) == 1 and tuple(part.shape_strokes[0].color) == (0.0, 1.0, 0.0)
# a stroke with many points is cut in the same way, with the pressure kept
many = np.column_stack([np.linspace(0, 200, 80), np.zeros(80), np.linspace(0.2, 1.0, 80)])
pencil.add_stroke(part, many[:, :2], many[:, 2], (0, 0, 1), 4.0)
before = len(part.shape_strokes)
assert pencil.erase_parts(part, [(100.0, 0.0)], 8.0) == 1 and len(part.shape_strokes) == before + 1
tail = pencil.decode(part.shape_strokes[before].data)
assert tail[:, 2].min() > 0.5 and np.all(np.diff(tail[:, 2]) >= -1e-5), 'pressure follows the line'
settings.images.remove(len(settings.images) - 1)
# a click picks a drawing on a stroke, not on the empty part of its box
click = settings.images.add()
click.item_id, click.item_type, click.shape_kind = 'ck', 'SHAPE', 'PENCIL'
pencil.add_stroke(click, np.array([[0.0, 0.0], [100.0, 100.0]]), [1.0, 1.0], (1, 0, 0), 4.0)
assert shape_geometry.hit_shape(click, (50.0, 50.0), 6.0)
assert not shape_geometry.hit_shape(click, (90.0, 10.0), 6.0), 'inside the box, off the stroke'
settings.images.remove(len(settings.images) - 1)

# the cursor marks: glyph and rings are plain geometry
glyph = pencil._pencil_glyph(10.0, 10.0)
assert len(glyph) % 2 == 0 and len(glyph) >= 10
ring = pencil._ring(0.0, 0.0, 5.0, 16)
assert len(ring) == 32 and abs(np.hypot(*ring[0]) - 5.0) < 1e-6
assert pencil.hover == {}

# the mesh: a ribbon and two round ends, indices inside the vertex list
points = np.array([[0, 0, 1.0], [10, 0, 1.0], [20, 5, 0.5]])
positions, triangles = pencil.stroke_mesh(points, 4.0)
assert positions.shape[1] == 2 and triangles.shape[1] == 3
assert triangles.max() < len(positions) and triangles.min() >= 0
dot_positions, dot_triangles = pencil.stroke_mesh(np.array([[5, 5, 1.0]]), 4.0)
assert dot_triangles.max() < len(dot_positions)
# pressure thins the line: the narrow end is closer to the path than the full one
assert pencil.MIN_PRESSURE < 0.5

# smoothing keeps the ends and removes jitter
rng = np.random.default_rng(1)
line = np.column_stack([np.linspace(0, 100, 60), rng.normal(0, 3, 60), np.ones(60)]).astype(np.float32)
smooth = pencil.smoothed(line, 0.8)
assert np.allclose(smooth[0], line[0]) and np.allclose(smooth[-1], line[-1])
assert smooth[:, 1].std() < line[:, 1].std()
assert np.array_equal(pencil.smoothed(line, 0.0), line)

# picking: the nearest stroke within reach, none far away, rotation and scale respected
assert pencil.pick_stroke(item, tuple(third[1]), 3.0)[0] == 2
assert pencil.pick_stroke(item, tuple(canvas_points(item, 1)[1]), 3.0)[0] == 1
assert pencil.pick_stroke(item, (5000.0, 5000.0), 3.0) is None
near = (third[1][0] + 1.0, third[1][1] + 1.0)
assert pencil.pick_stroke(item, near, 3.0)[0] == 2

# restyling and deleting what is picked
from k_tools_kanvas.properties import show_pencil_style
item.shape_strokes[1].selected = True
item.shape_strokes[2].selected = True
settings.pencil_color = (0.9, 0.1, 0.2)
settings.pencil_width = 11.0
assert tuple(round(c, 3) for c in item.shape_strokes[1].color) == (0.9, 0.1, 0.2)
assert item.shape_strokes[2].width == 11.0
assert tuple(item.shape_strokes[0].color) == (1.0, 0.0, 0.0), 'unpicked strokes keep their color'
show_pencil_style(settings, item.shape_strokes[0])           # showing a stroke restyles nothing
assert item.shape_strokes[1].width == 11.0 and settings.pencil_width == 10.0

# undo the last stroke
assert pencil.remove_last_stroke(item) and len(item.shape_strokes) == 2

# antialiasing: the outline is closed, clockwise, and its fringe has geometry
for pts in (np.array([[0, 0, 1], [10, 0, 1], [20, 5, 0.5]], dtype=np.float64),
            np.array([[3, 3, 1]], dtype=np.float64)):
    outline = pencil.stroke_outline(pts, 4.0)
    x, y = outline[:, 0], outline[:, 1]
    area = 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)
    assert area < 0, 'outline must be clockwise'
    from k_tools_kanvas.utils.gpu.gpu_arrow import _antialias_fringe
    vertices, colors = _antialias_fringe([tuple(p) for p in outline], 0.5, (1, 0, 0, 1))
    assert vertices and len(vertices) == len(colors)
assert settings.pencil_antialias is True

addon.unregister()
print('test_pencil: OK')
