"""Gradient fills on a real GPU: the shader builds, and drawing a shape into an
offscreen buffer gives the expected colors (linear left to right, radial from the
middle, reflect), then the board is redrawn in the window without errors.

    blender --factory-startup -P scratch/gui_gradient_draw.py
Prints GUIGRADIENT RESULT OK or FAIL. Needs a window (not -b).
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import bpy
import gpu
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

W, H = 200, 100
errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def render(shape, overlays=None):
    """Draw one shape covering canvas x 0..200, y 0..100 into a W x H buffer."""
    from k_tools_kanvas.utils.gpu.gpu_shape import draw_shape_body
    offscreen = gpu.types.GPUOffScreen(W, H)
    try:
        with offscreen.bind():
            framebuffer = gpu.state.active_framebuffer_get()
            framebuffer.clear(color=(0.0, 0.0, 0.0, 0.0))
            with gpu.matrix.push_pop():
                gpu.matrix.load_matrix(Matrix.Identity(4))
                with gpu.matrix.push_pop_projection():
                    gpu.matrix.load_projection_matrix(Matrix((
                        (2.0 / W, 0, 0, -1), (0, 2.0 / H, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1))))
                    if overlays is None:
                        draw_shape_body(shape, 1.0, (-1e6, -1e6, 1e6, 1e6))
                    else:
                        from k_tools_kanvas.utils.gpu.gpu_shape import draw_shape_overlays
                        draw_shape_overlays(overlays, 1.0, (-1e6, -1e6, 1e6, 1e6))
            pixels = framebuffer.read_color(0, 0, W, H, 4, 0, 'FLOAT')
            pixels.dimensions = W * H * 4
            values = list(pixels)
    finally:
        offscreen.free()
    return lambda x, y: tuple(values[(y * W + x) * 4:(y * W + x) * 4 + 4])


def near(color, wanted, tol=0.08):
    return all(abs(a - b) < tol for a, b in zip(color, wanted))


def run():
    addon.register()
    window = bpy.context.window_manager.windows[0]
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI gradients', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    from k_tools_kanvas.utils.gpu.gpu_gradient import get_gradient_shader
    check(get_gradient_shader() is not None, 'gradient shader did not build')
    with bpy.context.temp_override(window=window, area=area, region=region,
                                   space_data=area.spaces.active):
        bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 50.0), size=(200.0, 100.0))
        shape = settings.images[-1]
        shape.shape_show_outline = False
        shape.shape_show_fill = True
        shape.shape_fill_opacity = 1.0
        shape.shape_fill_type = 'LINEAR'
        first, last = shape.shape_gradient_texture.color_ramp.elements
        first.color, first.position = (1, 0, 0, 1), 0.0
        last.color, last.position = (0, 0, 1, 1), 1.0

        pixel = render(shape)
        check(near(pixel(3, 50), (1, 0, 0, 1)), f'linear left {pixel(3, 50)}')
        check(near(pixel(196, 50), (0, 0, 1, 1)), f'linear right {pixel(196, 50)}')
        check(near(pixel(100, 50), (0.5, 0, 0.5, 1)), f'linear middle {pixel(100, 50)}')
        check(near(pixel(100, 5), pixel(100, 95)), 'linear is the same up and down')

        shape.shape_fill_type = 'RADIAL'   # center (0, 0), edge (0.5, 0): radius 100
        pixel = render(shape)
        check(near(pixel(100, 50), (1, 0, 0, 1)), f'radial center {pixel(100, 50)}')
        check(near(pixel(150, 50), (0.5, 0, 0.5, 1)), f'radial halfway {pixel(150, 50)}')
        check(near(pixel(100, 0), pixel(50, 50)), 'radial is round on a stretched shape')

        shape.shape_fill_type = 'LINEAR'
        shape.shape_gradient_end = (0.0, 0.0)      # the ramp ends in the middle
        shape.shape_gradient_spread = 'REFLECT'
        pixel = render(shape)
        check(near(pixel(196, 50), (1, 0, 0, 1)), f'reflect comes back {pixel(196, 50)}')
        shape.shape_gradient_spread = 'PAD'
        pixel = render(shape)
        check(near(pixel(196, 50), (0, 0, 1, 1)), f'pad keeps the end {pixel(196, 50)}')

        # Editing the ramp (what the color ramp widget does) must redraw the board:
        # watched through the message bus; the notification arrives on a later tick.
        import k_tools_kanvas as package
        state['area'] = area
        state['real'] = package._redraw_boards

        def spy(*args):
            state['notified'] = True
            state['real'](*args)
        package._redraw_boards = spy
        package.subscribe_gradient_edits()
        shape.shape_gradient_texture.color_ramp.elements[0].color = (0, 1, 0, 1)
        # Gradient handles: drawn on the Fill tab with the shape selected alone.
        shape.shape_gradient_spread = 'PAD'
        shape.shape_gradient_start, shape.shape_gradient_end = (-0.25, 0.0), (0.25, 0.0)
        for other in settings.images:
            other.is_selected = other == shape
        settings.active_image_index = len(settings.images) - 1
        bpy.context.window_manager.kanvas_tabs.shape = 'FILL'
        pixel = render(shape, overlays=settings)
        bright = lambda c: min(c[:3]) > 0.8 and c[3] > 0.8
        check(bright(pixel(50, 50)), f'start handle {pixel(50, 50)}')
        check(bright(pixel(150, 50)), f'end handle {pixel(150, 50)}')
        check(pixel(100, 50)[3] > 0.5, f'handle line {pixel(100, 50)}')
        check(pixel(100, 80)[3] < 0.1, f'nothing away from the line {pixel(100, 80)}')
        bpy.context.window_manager.kanvas_tabs.shape = 'LINE'
        pixel = render(shape, overlays=settings)
        check(pixel(100, 50)[3] < 0.1, f'no handles off the Fill tab {pixel(100, 50)}')
        output = io.StringIO()
        with redirect_stdout(output):
            bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=3)
        check('Kanvas shape' not in output.getvalue(), output.getvalue())


state = {}


def finish():
    check(state.get('notified'), 'editing the ramp did not ask for a redraw')
    print('GUIGRADIENT RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()


def tick():
    try:
        run()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    bpy.app.timers.register(finish, first_interval=0.5)


bpy.app.timers.register(tick, first_interval=1.0)
