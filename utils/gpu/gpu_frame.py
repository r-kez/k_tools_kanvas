"""Rendering and hit testing for Kanvas-owned frames."""
import gpu
from gpu_extras.batch import batch_for_shader
from .gpu_theme import (draw_glass_surface, draw_rounded_border,
                        draw_rounded_fill, glass_enabled, selection_color,
                        studio_enabled)

# Header height is fixed in 2D canvas view units (so it zooms with the canvas and never covers images)
FRAME_HEADER_HEIGHT = 36.0
HANDLE_PIXELS = 14


def frame_header_height(frame):
    """Keep the header tall enough for the frame's chosen label size."""
    return max(FRAME_HEADER_HEIGHT, frame.frame_font_size * 2.4)


def hit_test_frame(frame, position, view_pixel_size, allow_resize=True):
    """Return the draggable part under a view-space point."""
    x, y = position
    left, top = frame.location
    right = left + frame.frame_width
    bottom = top - frame.frame_height
    if not (left <= x <= right and bottom <= y <= top):
        return None
    handle = HANDLE_PIXELS * view_pixel_size
    if allow_resize and x >= right - handle and y <= bottom + handle:
        return 'RESIZE'
    if y >= top - frame_header_height(frame):
        return 'MOVE'
    return 'BODY'


def draw_kanvas_frame(frame, view_pixel_size, region=None, highlight=False,
                      allow_resize=True):
    if not frame.show_in_editor:
        return
    left, top = frame.location
    right = left + frame.frame_width
    bottom = top - frame.frame_height
    header_bottom = max(bottom, top - frame_header_height(frame))
    c = frame.frame_color

    if studio_enabled():
        _draw_studio_frame(frame, view_pixel_size, left, bottom, right, top,
                           header_bottom, highlight, allow_resize)
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')

    def rectangle(x0, y0, x1, y1, color):
        batch = batch_for_shader(shader, 'TRIS', {'pos': [
            (x0, y0), (x1, y0), (x1, y1),
            (x0, y0), (x1, y1), (x0, y1)]})
        shader.bind()
        shader.uniform_float('color', color)
        batch.draw(shader)

    # Frame body (behind images)
    rectangle(left, bottom, right, header_bottom, (*c, frame.frame_opacity))
    # Frame header bar (fixed canvas height, richer alpha)
    header_alpha = min(1.0, frame.frame_opacity + 0.35)
    rectangle(left, header_bottom, right, top, (*c, header_alpha))

    # Border outline and header divider
    border = ((1.0, 0.85, 0.15, 1.0) if highlight else
              (0.95, 0.74, 0.25, 1.0) if frame.is_selected else (*c, 0.9))
    outline = batch_for_shader(shader, 'LINES', {'pos': [
        (left, top), (right, top),
        (right, top), (right, bottom),
        (right, bottom), (left, bottom),
        (left, bottom), (left, top),
        (left, header_bottom), (right, header_bottom),
    ]})
    shader.uniform_float('color', border)
    outline.draw(shader)

    if allow_resize:
        handle = HANDLE_PIXELS * view_pixel_size
        grip = batch_for_shader(shader, 'LINES', {'pos': [
            (right - handle, bottom + handle * 0.35), (right - handle * 0.35, bottom + handle),
            (right - handle * 0.65, bottom + handle * 0.25), (right - handle * 0.25, bottom + handle * 0.65)]})
        grip.draw(shader)
    gpu.state.blend_set('NONE')


def _draw_studio_frame(frame, pixel_size, left, bottom, right, top,
                       header_bottom, highlight, allow_resize):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        bounds = (left, bottom, right, top)
        radius = min(12.0, (right - left) * 0.1, (top - bottom) * 0.1)
        c = frame.frame_color
        accent = selection_color()
        glass = glass_enabled()
        if glass:
            draw_glass_surface(shader, bounds, radius, c,
                               frame.frame_opacity, pixel_size)
        else:
            draw_rounded_fill(shader, bounds, radius, (*c, frame.frame_opacity),
                              pixel_size, antialias=True)
        # Keep the header visually distinct while the item's chosen color remains visible.
        header_inset = max(2.0, radius * 0.28)
        if header_bottom + header_inset < top - header_inset:
            draw_rounded_fill(shader,
                              (left + header_inset, header_bottom + header_inset,
                               right - header_inset, top - header_inset),
                              max(1.0, radius - header_inset),
                              (*c, min(0.5, 0.14 + frame.frame_opacity * 0.34)),
                              pixel_size)
        border = ((1.0, 0.85, 0.15, 1.0) if highlight else
                  (*accent[:3], 1.0) if frame.is_selected else
                  (0.75, 0.88, 1.0, 0.4) if glass else (*c, 0.76))
        draw_rounded_border(shader, bounds, radius, max(1.0, 1.5 * pixel_size),
                            border, pixel_size, antialias=True)
        line = batch_for_shader(shader, 'LINES', {'pos': [
            (left + radius, header_bottom), (right - radius, header_bottom),
        ]})
        shader.uniform_float('color', (*accent[:3], 0.68) if frame.is_selected
                             else (*c, 0.56))
        line.draw(shader)
        if allow_resize:
            handle = HANDLE_PIXELS * pixel_size
            grip = batch_for_shader(shader, 'LINES', {'pos': [
                (right - handle, bottom + handle * 0.35),
                (right - handle * 0.35, bottom + handle),
                (right - handle * 0.65, bottom + handle * 0.25),
                (right - handle * 0.25, bottom + handle * 0.65),
            ]})
            shader.uniform_float('color', border)
            grip.draw(shader)
    finally:
        gpu.state.blend_set(old_blend)

