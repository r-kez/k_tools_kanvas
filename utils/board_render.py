"""Render the board, or part of it, to a picture: the same drawing as the canvas, done
in an offscreen buffer instead of the editor.

The canvas draws through `draw_board` (view space) and `draw_board_labels` (region
pixels). Here both are called with a stand-in region whose `view2d` maps one tile of
the wanted rectangle, with the interface left out (`export=True`) and the selection
cleared for the moment, so no outline or handle shows. Large pictures are rendered in
tiles of at most TILE pixels and joined, so the GPU never needs a buffer larger than
that. The colors come out as the canvas shows them; the picture is written as PNG
with plain zlib, without going through a Blender image (a 16k picture would need
gigabytes as floats).
"""

import math
import struct
import zlib

TILE = 4096
MAX_SIDE = 16384


class _View2D:
    """The two mappings the drawing code uses, for one tile."""

    def __init__(self, left, bottom, pixel_size):
        self.left, self.bottom, self.pixel_size = left, bottom, pixel_size

    def view_to_region(self, x, y, clip=True):
        return ((x - self.left) / self.pixel_size, (y - self.bottom) / self.pixel_size)

    def region_to_view(self, x, y):
        return (self.left + x * self.pixel_size, self.bottom + y * self.pixel_size)


class _Region:
    def __init__(self, width, height, view2d):
        self.width, self.height, self.view2d = width, height, view2d
        self.x = self.y = 0
        self.type = 'WINDOW'


# --- What to render --------------------------------------------------------------------

def _pad(box, amount):
    return box[0] - amount, box[1] - amount, box[2] + amount, box[3] + amount


def item_rect(settings, items):
    """Canvas rectangle around items (frames include what they hold). A shape's line
    reaches past its outline, so its width is added."""
    from .item_geometry import item_bounds
    boxes = []
    for item in items:
        box = item_bounds(item)
        if not box:
            continue
        if item.item_type == 'SHAPE' and item.shape_show_outline:
            box = _pad(box, item.shape_line_width)
        boxes.append(box)
    return union(*boxes)


def arrow_rect(settings, arrows):
    """Canvas rectangle around arrows, curve, line width and heads included."""
    from .arrow_geometry import curve_points
    boxes = []
    for arrow in arrows:
        points = [p for p in curve_points(settings, arrow) if p is not None]
        if not points:
            continue
        box = (min(p[0] for p in points), min(p[1] for p in points),
               max(p[0] for p in points), max(p[1] for p in points))
        boxes.append(_pad(box, arrow.thickness * 5.0 + 8.0))   # the head is wider than the line
    return union(*boxes)


def union(*rects):
    rects = [r for r in rects if r]
    if not rects:
        return None
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects))


def selection_contents(settings):
    """(items, arrows) a picture of the selection shows: the selected items, with
    everything inside a selected frame or group (not the frame around a selected
    item), and the arrows that are selected or whose attached ends all land on those
    items. Hidden items stay hidden."""
    from .gpu import frame_descendants
    kept = {}
    for item in settings.images:
        if not item.is_selected or not item.show_in_editor:
            continue
        kept[item.item_id] = item
        if item.item_type == 'FRAME':
            for child in frame_descendants(settings, item.frame_node_name):
                if child.show_in_editor:
                    kept[child.item_id] = child
    arrows = []
    for arrow in settings.arrows:
        ends = [item_id for item_id in (arrow.start_item_id, arrow.end_item_id) if item_id]
        if arrow.is_selected or (ends and all(item_id in kept for item_id in ends)):
            arrows.append(arrow)
    return list(kept.values()), arrows


def board_rect(settings, scope, only_selected=True):
    """Canvas rectangle of 'SELECTION' (what `selection_contents` keeps, or with
    `only_selected` off, the selected items and arrows) or 'ALL' (every visible item
    and arrow). None when there is nothing."""
    visible = [item for item in settings.images if item.show_in_editor]
    if scope == 'SELECTION' and only_selected:
        items, arrows = selection_contents(settings)
    elif scope == 'SELECTION':
        items = [item for item in visible if item.is_selected]
        arrows = [arrow for arrow in settings.arrows if arrow.is_selected]
    else:
        items, arrows = visible, list(settings.arrows)
    return union(item_rect(settings, items), arrow_rect(settings, arrows))


def output_size(rect, scale, margin):
    """Pixel size of the picture of `rect` at `scale` pixels per canvas unit, with a
    margin in pixels on every side."""
    width = (rect[2] - rect[0]) * scale + 2 * margin
    height = (rect[3] - rect[1]) * scale + 2 * margin
    return max(1, int(math.ceil(width))), max(1, int(math.ceil(height)))


def tiles(width, height, tile=TILE):
    """(x, y, w, h) pieces covering a width x height picture, from the bottom left."""
    return [(x, y, min(tile, width - x), min(tile, height - y))
            for y in range(0, height, tile) for x in range(0, width, tile)]


# --- Rendering -------------------------------------------------------------------------

def _render_tile(settings, space, frame_number, left, bottom, pixel_size, width, height,
                 background):
    """RGBA bytes (premultiplied, bottom row first) of one tile."""
    import gpu
    from mathutils import Matrix
    from . import gpu as kanvas_gpu
    from .gpu.gpu_common import begin_draw_pass, end_draw_pass
    region = _Region(width, height, _View2D(left, bottom, pixel_size))
    view_bounds = (left, bottom, left + width * pixel_size, bottom + height * pixel_size)
    offscreen = gpu.types.GPUOffScreen(width, height, format='RGBA8')
    try:
        with offscreen.bind():
            framebuffer = gpu.state.active_framebuffer_get()
            framebuffer.clear(color=background)
            begin_draw_pass()
            try:
                with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                    gpu.matrix.load_matrix(Matrix.Identity(4))
                    w, h = width * pixel_size, height * pixel_size
                    gpu.matrix.load_projection_matrix(Matrix((
                        (2.0 / w, 0, 0, -1 - 2.0 * left / w),
                        (0, 2.0 / h, 0, -1 - 2.0 * bottom / h),
                        (0, 0, 1, 0), (0, 0, 0, 1))))
                    kanvas_gpu.draw_board(settings, view_bounds, pixel_size, region,
                                          space=space, frame_number=frame_number, export=True)
                with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                    gpu.matrix.load_matrix(Matrix.Identity(4))
                    gpu.matrix.load_projection_matrix(Matrix((
                        (2.0 / width, 0, 0, -1), (0, 2.0 / height, 0, -1),
                        (0, 0, 1, 0), (0, 0, 0, 1))))
                    kanvas_gpu.draw_board_labels(settings, region, export=True)
            finally:
                end_draw_pass()
            buffer = framebuffer.read_color(0, 0, width, height, 4, 0, 'UBYTE')
            buffer.dimensions = width * height * 4
            return bytes(buffer)
    finally:
        offscreen.free()


def render(settings, rect, scale, margin=0, background=(0.0, 0.0, 0.0, 0.0), space=None,
           frame_number=0, only=None):
    """The picture of `rect` as a NumPy array (height, width, 4) of uint8, straight
    alpha, top row first, ready for PNG. `only` is (items, arrows) to draw alone (see
    `selection_contents`); the other items are hidden while drawing and come back."""
    import numpy as np
    from ..properties import suspend_selection_updates
    width, height = output_size(rect, scale, margin)
    if max(width, height) > MAX_SIDE:
        raise ValueError(f'{width} x {height} px is larger than {MAX_SIDE} px on a side')
    pixel_size = 1.0 / scale
    left = rect[0] - margin * pixel_size
    bottom = rect[1] - margin * pixel_size
    picture = np.zeros((height, width, 4), dtype=np.uint8)
    # No outline or handle in the picture: clear the selection for the moment.
    selected = [item.is_selected for item in settings.images]
    arrows = [arrow.is_selected for arrow in settings.arrows]
    shown = [item.show_in_editor for item in settings.images]
    from .gpu import gpu_arrow
    from ..properties import suspend_visibility_updates
    try:
        if only is not None:
            keep = {item.item_id for item in only[0]}
            with suspend_visibility_updates():
                for item in settings.images:
                    if item.show_in_editor and item.item_id not in keep:
                        item.show_in_editor = False
            gpu_arrow.ARROW_FILTER = {arrow.as_pointer() for arrow in only[1]}
        with suspend_selection_updates():
            for item in settings.images:
                if item.is_selected:
                    item.is_selected = False
            for arrow in settings.arrows:
                if arrow.is_selected:
                    arrow.is_selected = False
        for x, y, w, h in tiles(width, height):
            data = _render_tile(settings, space, frame_number, left + x * pixel_size,
                                bottom + y * pixel_size, pixel_size, w, h, background)
            tile = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4)
            picture[y:y + h, x:x + w] = tile
    finally:
        gpu_arrow.ARROW_FILTER = None
        with suspend_visibility_updates():
            for item, state in zip(settings.images, shown):
                if item.show_in_editor != state:
                    item.show_in_editor = state
        with suspend_selection_updates():
            for item, state in zip(settings.images, selected):
                if item.is_selected != state:
                    item.is_selected = state
            for arrow, state in zip(settings.arrows, arrows):
                if arrow.is_selected != state:
                    arrow.is_selected = state
    return unpremultiply(picture[::-1])


def unpremultiply(picture):
    """Drawing over a clear buffer leaves colors multiplied by their alpha; PNG wants
    them straight."""
    import numpy as np
    alpha = picture[..., 3:4].astype(np.float32)
    color = picture[..., :3].astype(np.float32)
    safe = np.where(alpha > 0, alpha, 1.0)
    straight = np.where(alpha > 0, np.clip(color * 255.0 / safe, 0, 255), 0)
    result = picture.copy()
    result[..., :3] = (straight + 0.5).astype(np.uint8)
    return result


def write_png(path, picture):
    """Write a (height, width, 4) uint8 array (top row first) as an RGBA PNG."""
    import numpy as np
    height, width = picture.shape[:2]
    rows = np.concatenate([np.zeros((height, 1), dtype=np.uint8),
                           picture.reshape(height, width * 4)], axis=1)

    def chunk(kind, data):
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    with open(path, 'wb') as handle:
        handle.write(b'\x89PNG\r\n\x1a\n')
        handle.write(chunk(b'IHDR', header))
        handle.write(chunk(b'IDAT', zlib.compress(rows.tobytes(), 6)))
        handle.write(chunk(b'IEND', b''))
