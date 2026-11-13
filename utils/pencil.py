"""Pencil Drawings: strokes kept in one item, in the unit box of a shape.

A Pencil Drawing is a shape item (`shape_kind == 'PENCIL'`), so moving, scaling,
rotating, framing, stacking and anchoring arrows work as for any shape. Its box fits the
strokes. Each stroke stores its points as x, y (unit box, -0.5..0.5, like shape
vertices) and pressure (0..1), packed as float32 in a base64 string: a drawing of a
hundred strokes stays a hundred small strings. Stroke widths are in canvas units before
the drawing's scale.
"""

import base64

import numpy as np

from . import shape_geometry

MIN_PRESSURE = 0.12          # a stroke never thins out to nothing
MIN_BOX = 8.0                # canvas units, a drawing of a dot
CAP_SEGMENTS = 24            # sides of the round ends (fill and fringe use the same)
_cache = {}                  # (item, stroke) -> (signature, batch)


# --- packing -------------------------------------------------------------------------

def encode(points):
    """(n, 3) array of x, y, pressure -> string."""
    return base64.b64encode(np.ascontiguousarray(points, dtype='<f4').tobytes()).decode('ascii')


def decode(text):
    """string -> (n, 3) float32 array; empty for no points."""
    if not text:
        return np.zeros((0, 3), dtype=np.float32)
    return np.frombuffer(base64.b64decode(text), dtype='<f4').reshape(-1, 3).copy()


# --- smoothing -----------------------------------------------------------------------

def smoothed(points, strength):
    """Smooth a captured stroke (n, 3): a moving average that keeps both ends, then one
    round of corner cutting. `strength` 0 leaves the points as they are."""
    if len(points) < 3 or strength <= 0.0:
        return points
    result = points.astype(np.float64)
    radius = int(round(1 + strength * 5))
    passes = 1 + int(strength * 2)
    for _ in range(passes):
        padded = np.concatenate([np.repeat(result[:1], radius, axis=0), result,
                                 np.repeat(result[-1:], radius, axis=0)])
        kernel = np.ones(2 * radius + 1) / (2 * radius + 1)
        result = np.stack([np.convolve(padded[:, axis], kernel, mode='valid')
                           for axis in range(result.shape[1])], axis=1)
        result[0], result[-1] = points[0], points[-1]
    if strength > 0.35 and len(result) > 3:
        # Chaikin: every segment gives two points a quarter and three quarters along it.
        a, b = result[:-1], result[1:]
        cut = np.empty((2 * len(a), result.shape[1]))
        cut[0::2] = a * 0.75 + b * 0.25
        cut[1::2] = a * 0.25 + b * 0.75
        result = np.concatenate([result[:1], cut, result[-1:]])
    return result.astype(np.float32)


def apply_pressure(pressure, use=True, minimum=MIN_PRESSURE, curve=0.0):
    """The pressure to store for a captured one, from the pen settings. Off, the line has a
    constant width. `minimum` is the share of the width left at no pressure; `curve` from
    -1 (hard: the line thickens late) to 1 (soft: it thickens early), 0 as the pen gives it.
    Stored pressure goes through the same floor as always (`MIN_PRESSURE`), so the result
    is what the pen settings ask for, at least that floor."""
    pressure = np.clip(np.asarray(pressure, dtype=np.float64), 0.0, 1.0)
    if not use:
        return np.ones_like(pressure, dtype=np.float32)
    shaped = np.power(pressure, 2.0 ** (-2.0 * float(curve)))
    minimum = float(np.clip(minimum, 0.0, 1.0))
    share = minimum + (1.0 - minimum) * shaped
    return np.clip((share - MIN_PRESSURE) / (1.0 - MIN_PRESSURE), 0.0, 1.0).astype(np.float32)


def thinned(points, minimum):
    """Drop points closer than `minimum` to the last one kept (canvas units on x, y)."""
    if len(points) < 3:
        return points
    keep = [0]
    for index in range(1, len(points) - 1):
        if np.hypot(*(points[index, :2] - points[keep[-1], :2])) >= minimum:
            keep.append(index)
    keep.append(len(points) - 1)
    return points[keep]


# --- the box ---------------------------------------------------------------------------

def local_from_canvas(item, xy):
    """Canvas points (n, 2) -> the drawing's local canvas units (before rotation, scale
    and location)."""
    angle = np.radians(-item.rotation)
    cos, sin = np.cos(angle), np.sin(angle)
    shifted = np.asarray(xy, dtype=np.float64) - np.array(item.location[:2])
    x = shifted[:, 0] * cos - shifted[:, 1] * sin
    y = shifted[:, 0] * sin + shifted[:, 1] * cos
    return np.stack([x, y], axis=1) / max(item.scale_master, 1e-6)


def _strokes_local(item):
    """Every stroke of `item` as (points (n, 3) in local canvas units, color, width)."""
    size = np.array([item.shape_width, item.shape_height])
    out = []
    for stroke in item.shape_strokes:
        points = decode(stroke.data).astype(np.float64)
        points[:, :2] *= size
        out.append((points, tuple(stroke.color), stroke.width))
    return out


def _refit(item, members):
    """Store `members` (every stroke: points (n, 3) in local canvas units, color, width)
    in `item` and refit its box to them, keeping every stroke where it is on the canvas."""
    from ..properties import suspend_frame_geometry_updates
    low = np.min([(points[:, :2] - width * 0.5).min(axis=0) for points, _, width in members], axis=0)
    high = np.max([(points[:, :2] + width * 0.5).max(axis=0) for points, _, width in members], axis=0)
    center = (low + high) * 0.5
    size = np.maximum(high - low, MIN_BOX)
    with suspend_frame_geometry_updates():
        dx, dy = shape_geometry.rotate((center[0] * item.scale_master,
                                        center[1] * item.scale_master), item.rotation)
        item.location = (item.location[0] + dx, item.location[1] + dy)
        item.shape_width, item.shape_height = float(size[0]), float(size[1])
    while len(item.shape_strokes) < len(members):
        item.shape_strokes.add()
    for stroke, (points, stroke_color, stroke_width) in zip(item.shape_strokes, members):
        unit = points.copy()
        unit[:, :2] = (unit[:, :2] - center) / size
        stroke.data = encode(unit)
        stroke.color = stroke_color
        stroke.width = stroke_width
    _forget(item)


def add_stroke(item, canvas_xy, pressure, color, width):
    """Add a stroke given in canvas coordinates to the drawing `item` and refit its box
    (keeping the other strokes where they are on the canvas)."""
    local = local_from_canvas(item, canvas_xy)
    new = np.column_stack([local, np.asarray(pressure, dtype=np.float64)])
    members = [(points, tuple(c), w) for points, c, w in _strokes_local(item)]
    _refit(item, members + [(new, tuple(color), width)])


def canvas_points_of(item, index):
    """The points (n, 2) of one stroke on the canvas."""
    stroke = item.shape_strokes[index]
    points = decode(stroke.data)[:, :2].astype(np.float64) * np.array(
        [item.shape_width, item.shape_height]) * item.scale_master
    angle = np.radians(item.rotation)
    cos, sin = np.cos(angle), np.sin(angle)
    canvas = np.stack([points[:, 0] * cos - points[:, 1] * sin,
                       points[:, 0] * sin + points[:, 1] * cos], axis=1)
    return canvas + np.array(item.location[:2])


def strokes_snapshot(item, indices):
    """What `transform_strokes` starts from: (index, canvas points (n, 2), pressure (n,),
    width) of each stroke in `indices`."""
    return [(index, canvas_points_of(item, index),
             decode(item.shape_strokes[index].data)[:, 2].astype(np.float64),
             float(item.shape_strokes[index].width)) for index in indices
            if 0 <= index < len(item.shape_strokes)]


def snapshot_center(snapshot):
    """Middle of the bounds of the snapshot strokes, in canvas units."""
    everything = np.vstack([points for _, points, _, _ in snapshot])
    return tuple((everything.min(axis=0) + everything.max(axis=0)) * 0.5)


def transform_strokes(item, snapshot, place, width_factor=1.0):
    """Put the snapshot strokes where `place` (canvas points (n, 2) -> (n, 2)) takes them,
    their width times `width_factor`, and refit the box. Always starts from the
    snapshot, so a gesture can be redone on every mouse move."""
    members = [(points, tuple(c), w) for points, c, w in _strokes_local(item)]
    for index, canvas, pressure, width in snapshot:
        if index >= len(members):
            continue
        local = local_from_canvas(item, place(canvas))
        members[index] = (np.column_stack([local, pressure]), members[index][1],
                          max(0.5, width * width_factor))
    _refit(item, members)


def remove_last_stroke(item):
    """Take the newest stroke out; the box keeps its size. False when there is none."""
    count = len(item.shape_strokes)
    if not count:
        return False
    item.shape_strokes.remove(count - 1)
    _forget(item)
    return True


def _forget(item):
    key = item.as_pointer()
    for entry in [entry for entry in _cache if entry[0] == key]:
        del _cache[entry]


# --- picking ---------------------------------------------------------------------------

def pick_stroke(item, canvas_point, tolerance):
    """(index, distance) of the stroke of `item` nearest to a canvas point, if the point is
    within the stroke's reach plus `tolerance` (canvas units); otherwise None."""
    if not len(item.shape_strokes):
        return None
    point = local_from_canvas(item, np.array([canvas_point], dtype=np.float64))[0]
    size = np.array([item.shape_width, item.shape_height])
    reach = tolerance / max(item.scale_master, 1e-6)
    best = None
    for index, stroke in enumerate(item.shape_strokes):
        points = decode(stroke.data)[:, :2].astype(np.float64) * size
        if not len(points):
            continue
        if len(points) == 1:
            distance = float(np.hypot(*(points[0] - point)))
        else:
            a, b = points[:-1], points[1:]
            edge = b - a
            length2 = np.maximum((edge ** 2).sum(axis=1), 1e-12)
            t = np.clip(((point - a) * edge).sum(axis=1) / length2, 0.0, 1.0)
            nearest = a + edge * t[:, None]
            distance = float(np.hypot(*(nearest - point).T).min())
        distance -= stroke.width * 0.5
        if distance <= reach and (best is None or distance < best[1]):
            best = (index, distance)
    return best


def strokes_in_rect(item, low, high):
    """Indices of the strokes of `item` touched by the canvas rectangle low..high (their
    ribbon included: the rectangle grows by half the stroke width)."""
    size = np.array([item.shape_width, item.shape_height])
    angle = np.radians(item.rotation)
    cos, sin = np.cos(angle), np.sin(angle)
    low = np.asarray(low, dtype=np.float64)
    high = np.asarray(high, dtype=np.float64)
    found = []
    for index, stroke in enumerate(item.shape_strokes):
        points = decode(stroke.data)[:, :2].astype(np.float64) * size * item.scale_master
        if not len(points):
            continue
        canvas = np.stack([points[:, 0] * cos - points[:, 1] * sin,
                           points[:, 0] * sin + points[:, 1] * cos], axis=1)
        canvas += np.array(item.location[:2])
        reach = stroke.width * 0.5 * item.scale_master
        lo, hi = low - reach, high + reach
        if np.any(np.all((canvas >= lo) & (canvas <= hi), axis=1)):
            found.append(index)
            continue
        if len(canvas) < 2:
            continue
        # Liang-Barsky on every segment: does it cross the grown rectangle?
        a, b = canvas[:-1], canvas[1:]
        delta = b - a
        t0 = np.zeros(len(a))
        t1 = np.ones(len(a))
        alive = np.ones(len(a), dtype=bool)
        for axis in range(2):
            d = delta[:, axis]
            for p, q in ((-d, a[:, axis] - lo[axis]), (d, hi[axis] - a[:, axis])):
                parallel = np.abs(p) < 1e-12
                alive &= ~(parallel & (q < 0))
                with np.errstate(divide='ignore', invalid='ignore'):
                    r = np.where(parallel, 0.0, q / np.where(parallel, 1.0, p))
                t0 = np.where(~parallel & (p < 0), np.maximum(t0, r), t0)
                t1 = np.where(~parallel & (p > 0), np.minimum(t1, r), t1)
        if np.any(alive & (t0 <= t1)):
            found.append(index)
    return found


def selected_strokes(item):
    return [index for index, stroke in enumerate(item.shape_strokes) if stroke.selected]


def select_strokes(item, indices):
    """Pick exactly the strokes in `indices`."""
    wanted = set(indices)
    for index, stroke in enumerate(item.shape_strokes):
        if stroke.selected != (index in wanted):
            stroke.selected = index in wanted


def toggle_all_strokes(item):
    """Pick every stroke, or none when every stroke is already picked."""
    count = len(item.shape_strokes)
    select_strokes(item, [] if len(selected_strokes(item)) == count else range(count))


def invert_stroke_selection(item):
    chosen = set(selected_strokes(item))
    select_strokes(item, [i for i in range(len(item.shape_strokes)) if i not in chosen])


def clear_stroke_selection(item):
    for stroke in item.shape_strokes:
        if stroke.selected:
            stroke.selected = False


def remove_strokes(item, indices):
    """Delete the strokes at `indices`; the box keeps its size. How many went."""
    gone = sorted(set(i for i in indices if 0 <= i < len(item.shape_strokes)), reverse=True)
    for index in gone:
        item.shape_strokes.remove(index)
    if gone:
        _forget(item)
    return len(gone)


def remove_selected_strokes(item):
    """Delete the picked strokes; the box keeps its size. How many went."""
    return remove_strokes(item, selected_strokes(item))


def strokes_hit_by(item, samples, radius):
    """Indices of the strokes of `item` that a round eraser of `radius` (canvas units)
    touches when its centre is at any of `samples` (n, 2 canvas points). The stroke's own
    width counts."""
    samples = np.asarray(samples, dtype=np.float64).reshape(-1, 2)
    hit = []
    for index, stroke in enumerate(item.shape_strokes):
        points = canvas_points_of(item, index)
        if not len(points):
            continue
        reach = radius + stroke.width * 0.5 * item.scale_master
        if len(points) == 1:
            distance = np.hypot(*(samples - points[0]).T).min()
        else:
            a, b = points[:-1], points[1:]
            edge = b - a
            length2 = np.maximum((edge ** 2).sum(axis=1), 1e-12)
            # (samples, segments): where along each segment the sample is closest.
            t = np.clip(((samples[:, None, :] - a[None]) * edge[None]).sum(axis=2) / length2,
                        0.0, 1.0)
            nearest = a[None] + edge[None] * t[..., None]
            offset = nearest - samples[:, None, :]
            distance = np.sqrt((offset ** 2).sum(axis=2)).min()
        if distance <= reach:
            hit.append(index)
    return hit


# --- erasing ---------------------------------------------------------------------------

def _cut_stroke(points, samples, reach):
    """Pieces (list of (m, 3) arrays, local units) of a stroke once everything within
    `reach` of any of `samples` is taken away. The stroke itself (in a list) when the
    eraser misses it, an empty list when nothing is left. Segments near the eraser are
    subdivided first, so the cut falls where the circle is and not at a far point."""
    xy = points[:, :2]

    def nearest(p):
        return np.sqrt(((p[:, None, :] - samples[None]) ** 2).sum(axis=2)).min(axis=1)

    if len(points) > 1:
        a, b = points[:-1], points[1:]
        edge = b - a
        length2 = np.maximum((edge[:, :2] ** 2).sum(axis=1), 1e-12)
        t = np.clip(((samples[:, None, :] - a[None, :, :2]) * edge[None, :, :2]).sum(axis=2)
                    / length2, 0.0, 1.0)
        closest = a[None, :, :2] + edge[None, :, :2] * t[..., None]
        near = np.sqrt(((closest - samples[:, None, :]) ** 2).sum(axis=2)).min(axis=0)
        step = max(reach * 0.25, 1e-6)
        length = np.sqrt(length2)
        pieces = [points[:1]]
        for index in range(len(a)):
            count = 1
            if near[index] <= reach + step:
                count = int(min(64, max(1, np.ceil(length[index] / step))))
            fractions = np.linspace(0.0, 1.0, count + 1)[1:]
            pieces.append(a[index] + edge[index] * fractions[:, None])
        points = np.vstack(pieces)
        xy = points[:, :2]
    inside = nearest(xy) <= reach
    if not inside.any():
        return [points]
    runs, start = [], None
    for index, gone in enumerate(inside):
        if not gone and start is None:
            start = index
        elif gone and start is not None:
            runs.append(points[start:index])
            start = None
    if start is not None:
        runs.append(points[start:])
    # One point left on its own would be a blob the width of the line: drop it.
    return [run for run in runs if len(run) > 1]


def erase_parts(item, samples, radius):
    """Rub the strokes of `item` out where a round eraser of `radius` (canvas units) passes
    over `samples` (n, 2 canvas points): a stroke is cut into the pieces that stay (each a
    stroke of its own, with the colour, width and pick of the original, in the same place in
    the stack). How many strokes it touched."""
    hit = set(strokes_hit_by(item, samples, radius))
    if not hit:
        return 0
    size = np.array([item.shape_width, item.shape_height])
    scale = max(item.scale_master, 1e-6)
    local = local_from_canvas(item, samples)
    records = []
    for index, stroke in enumerate(item.shape_strokes):
        color, width, picked = tuple(stroke.color), stroke.width, stroke.selected
        if index not in hit:
            records.append((stroke.data, color, width, picked))
            continue
        points = decode(stroke.data).astype(np.float64)
        points[:, :2] *= size
        for piece in _cut_stroke(points, local, radius / scale + width * 0.5):
            unit = piece.copy()
            unit[:, :2] /= size
            records.append((encode(unit), color, width, picked))
    item.shape_strokes.clear()
    for data, color, width, picked in records:
        stroke = item.shape_strokes.add()
        stroke.data, stroke.color, stroke.width, stroke.selected = data, color, width, picked
    _forget(item)
    return len(hit)


# --- drawing ---------------------------------------------------------------------------

def stroke_mesh(points, width):
    """Triangles (positions (m, 2), indices (t, 3)) for a stroke given as (n, 3) x, y,
    pressure in canvas units: a ribbon whose width follows the pressure, with round ends."""
    xy = points[:, :2].astype(np.float64)
    half = width * 0.5 * (MIN_PRESSURE + (1.0 - MIN_PRESSURE) * np.clip(points[:, 2], 0.0, 1.0))
    positions, indices = [], []

    def disc(center, radius, segments=CAP_SEGMENTS):
        base = sum(len(p) for p in positions)     # vertices already laid down
        angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
        ring = center + radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)
        positions.append(np.vstack([center[None, :], ring]))
        fan = np.array([[0, 1 + i, 1 + (i + 1) % segments] for i in range(segments)]) + base
        indices.append(fan)

    if len(xy) == 1:
        disc(xy[0], half[0])
    else:
        tangent = np.gradient(xy, axis=0)
        length = np.hypot(tangent[:, 0], tangent[:, 1])
        length[length < 1e-9] = 1.0
        normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1) / length[:, None]
        left = xy + normal * half[:, None]
        right = xy - normal * half[:, None]
        strip = np.empty((2 * len(xy), 2))
        strip[0::2], strip[1::2] = left, right
        count = len(xy) - 1
        first = np.arange(count) * 2
        quad = np.stack([np.stack([first, first + 1, first + 2], axis=1),
                         np.stack([first + 1, first + 3, first + 2], axis=1)], axis=1)
        positions.append(strip)
        indices.append(quad.reshape(-1, 3))
        disc(xy[0], half[0])
        disc(xy[-1], half[-1])
    return np.vstack(positions).astype(np.float32), np.vstack(indices).astype(np.int32)


def stroke_outline(points, width, segments=CAP_SEGMENTS):
    """Closed clockwise outline (m, 2) of the ribbon `stroke_mesh` fills, with round ends."""
    xy = points[:, :2].astype(np.float64)
    half = width * 0.5 * (MIN_PRESSURE + (1.0 - MIN_PRESSURE) * np.clip(points[:, 2], 0.0, 1.0))
    if len(xy) == 1:
        angles = np.linspace(0.0, -2.0 * np.pi, segments * 2, endpoint=False)
        return xy[0] + half[0] * np.stack([np.cos(angles), np.sin(angles)], axis=1)
    tangent = np.gradient(xy, axis=0)
    length = np.hypot(tangent[:, 0], tangent[:, 1])
    length[length < 1e-9] = 1.0
    normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1) / length[:, None]
    left = xy + normal * half[:, None]
    right = xy - normal * half[:, None]

    def cap(center, radius, start_normal):
        # Half a turn clockwise from the left side to the right side, around the end.
        base = np.arctan2(start_normal[1], start_normal[0])
        angles = base - np.linspace(0.0, np.pi, segments + 1)[1:-1]
        return center + radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)

    end_cap = cap(xy[-1], half[-1], normal[-1])
    start_cap = cap(xy[0], half[0], -normal[0])
    outline = np.vstack([left, end_cap, right[::-1], start_cap])
    # Drop repeated points: the fringe needs every edge to have a direction.
    gaps = np.hypot(*np.diff(np.vstack([outline, outline[:1]]), axis=0).T)
    return outline[gaps > 1e-7]


def _fringe_batch(shader, item, index, stroke, feather):
    """One transparent pixel around the stroke (see `_antialias_fringe`), colour baked in."""
    from gpu_extras.batch import batch_for_shader
    from .gpu.gpu_arrow import _antialias_fringe
    color = (*stroke.color, item.opacity)
    signature = (len(stroke.data), stroke.data[-16:], round(stroke.width, 4),
                 round(item.shape_width, 3), round(item.shape_height, 3),
                 round(feather, 5), tuple(round(c, 4) for c in color))
    key = (item.as_pointer(), index, 'fringe')
    cached = _cache.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    points = decode(stroke.data).astype(np.float64)
    batch = None
    if len(points):
        points[:, :2] *= np.array([item.shape_width, item.shape_height])
        outline = stroke_outline(points, stroke.width)
        if len(outline) >= 3:
            vertices, colors = _antialias_fringe([tuple(p) for p in outline], feather, color)
            if vertices:
                batch = batch_for_shader(shader, 'TRIS', {'pos': vertices, 'color': colors})
    if len(_cache) > 4000:
        _cache.clear()
    _cache[key] = (signature, batch)
    return batch


def _batch(shader, item, index, stroke, grow=0.0):
    """The triangles of one stroke, `grow` wider than it is (for its highlight)."""
    from gpu_extras.batch import batch_for_shader
    signature = (len(stroke.data), stroke.data[-16:], round(stroke.width, 4),
                 round(item.shape_width, 3), round(item.shape_height, 3), round(grow, 4))
    key = (item.as_pointer(), index, bool(grow))
    cached = _cache.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    points = decode(stroke.data).astype(np.float64)
    if not len(points):
        return None
    points[:, :2] *= np.array([item.shape_width, item.shape_height])
    positions, triangles = stroke_mesh(points, stroke.width + grow)
    batch = batch_for_shader(shader, 'TRIS', {'pos': positions}, indices=triangles)
    if len(_cache) > 4000:
        _cache.clear()
    _cache[key] = (signature, batch)
    return batch


HIGHLIGHT = (0.25, 0.6, 1.0, 0.9)


def draw_pencil_body(item, view_bounds, pixel_size=1.0):
    """Draw every stroke of a Pencil Drawing at its place (opacity of the item)."""
    import gpu
    from mathutils import Matrix
    if not len(item.shape_strokes):
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    smooth = gpu.shader.from_builtin('SMOOTH_COLOR')
    try:
        import bpy
        from .kanvas_data import get_settings
        antialias = bool(get_settings(bpy.context).pencil_antialias)
    except Exception:
        antialias = True
    # The fringe is one screen pixel wide, so its geometry follows the zoom.
    feather = round(pixel_size / max(item.scale_master, 1e-6), 4)
    matrix = (Matrix.Translation((item.location[0], item.location[1], 0.0))
              @ Matrix.Rotation(np.radians(item.rotation), 4, 'Z')
              @ Matrix.Scale(item.scale_master, 4))
    gpu.matrix.push()
    gpu.matrix.multiply_matrix(matrix)
    try:
        shader.bind()
        halo = 6.0 * pixel_size / max(item.scale_master, 1e-6)
        for index, stroke in enumerate(item.shape_strokes):
            if stroke.selected:
                outline = _batch(shader, item, index, stroke, grow=halo)
                if outline is not None:
                    shader.uniform_float('color', HIGHLIGHT)
                    outline.draw(shader)
            batch = _batch(shader, item, index, stroke)
            if batch is None:
                continue
            shader.uniform_float('color', (*stroke.color, item.opacity))
            batch.draw(shader)
            if antialias and feather > 0.0:
                fringe = _fringe_batch(smooth, item, index, stroke, feather)
                if fringe is not None:
                    fringe.draw(smooth)
                shader.bind()
    finally:
        gpu.matrix.pop()


# The stroke being drawn, before it is part of a drawing: canvas points and pressures.
live = {'points': None, 'color': (0.0, 0.0, 0.0), 'width': 4.0}


# Where the pointer is over each board while the pencil or the eraser is the tool:
# (window, area) -> (x, y, alt) in the WINDOW region. Set by `kanvas.pencil_cursor` on every
# mouse move (no modal), and by the strokes and the eraser while they are dragging.
hover = {}
CURSOR_COLOR = (0.30, 0.85, 1.0, 1.0)


def hover_key(window, area):
    return (window.as_pointer(), area.as_pointer())


def set_hover(window, area, x, y, alt=False):
    hover[hover_key(window, area)] = (x, y, alt)


def _ring(x, y, radius, segments=40):
    angles = np.linspace(0.0, 2.0 * np.pi, segments + 1)
    points = [(x + radius * np.cos(a), y + radius * np.sin(a)) for a in angles]
    return [p for i in range(segments) for p in (points[i], points[i + 1])]


def _pencil_glyph(x, y):
    """A small pencil, its tip at (x, y), pointing down and to the left."""
    outline = [(0, 0), (3, 8), (12, 17), (17, 12), (8, 3), (0, 0)]
    lines = [p for i in range(len(outline) - 1)
             for p in ((x + outline[i][0], y + outline[i][1]),
                       (x + outline[i + 1][0], y + outline[i + 1][1]))]
    lines += [(x + 3 + 0.0, y + 8), (x + 8, y + 3),              # where the wood ends
              (x + 12, y + 17), (x + 17, y + 12)]                 # the end of the body
    return lines


def draw_pencil_cursor(region, settings):
    """The pencil or eraser mark beside the pointer: the pencil's width as a ring with a
    small pencil, the eraser's reach as a circle. Nothing for any other tool."""
    import bpy
    import gpu
    from gpu_extras.batch import batch_for_shader
    window, area = bpy.context.window, bpy.context.area
    if window is None or area is None or not hover:
        return
    tool = window.workspace.tools.from_space_node()
    name = tool.idname if tool is not None else ''
    if name not in {'kanvas.pencil', 'kanvas.eraser'}:
        return
    entry = hover.get(hover_key(window, area))
    if entry is None:
        return
    x, y, alt = entry
    if not (0 <= x <= region.width and 0 <= y <= region.height):
        return
    erasing = name == 'kanvas.eraser' or alt
    if erasing:
        lines = _ring(x, y, max(2.0, float(settings.pencil_eraser_size)))
        color = (1.0, 1.0, 1.0, 0.95)
    else:
        view = region.view2d
        pixel = abs(view.region_to_view(1, 0)[0] - view.region_to_view(0, 0)[0]) or 1.0
        width = settings.pencil_width / pixel
        lines = _pencil_glyph(x + 3, y + 3)
        if width >= 4.0:
            lines += _ring(x, y, width * 0.5)
        color = (*settings.pencil_color[:3], 1.0)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        gpu.state.line_width_set(3.0)                  # a dark edge, to read on any picture
        shader.uniform_float('color', (0.0, 0.0, 0.0, 0.55))
        batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)
        gpu.state.line_width_set(1.5)
        shader.uniform_float('color', color)
        batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set(old)


def draw_live_stroke():
    """The stroke under the pen, in canvas coordinates."""
    import gpu
    from gpu_extras.batch import batch_for_shader
    points = live['points']
    if points is None or not len(points):
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    positions, triangles = stroke_mesh(points, live['width'])
    batch = batch_for_shader(shader, 'TRIS', {'pos': positions}, indices=triangles)
    shader.bind()
    shader.uniform_float('color', (*live['color'], 1.0))
    old = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    batch.draw(shader)
    gpu.state.blend_set(old)
