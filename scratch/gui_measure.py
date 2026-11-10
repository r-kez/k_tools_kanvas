"""Marks and scale on a real GPU and window: the Draw Mark tool arms the next drag and
Escape disarms it; the Set Scale dialog operator gives the image a scale; the canvas shows
the scale mark in amber and the other marks in cyan, each with its size in a label; the
unit follows the board; Send to 3D View with Real Scale makes the Empty as big as the
image is in real life (units of the scene included), and follows a new scale and a new
mask; copies of the image carry their marks.

    blender --factory-startup -P scratch/gui_measure.py
Prints GUIMEASURE RESULT OK or FAIL. Needs a window (not -b).
"""

import os
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []
state = {}


def check(condition, message):
    if not condition:
        errors.append(message)


def settings():
    return state['tree'].kanvas_settings


def photo():
    return next(i for i in settings().images if i.item_id == 'car')


def override():
    return bpy.context.temp_override(window=state['window'], area=state['kanvas'],
                                     region=state['region'], space_data=state['space'])


def setup():
    import numpy as np
    addon.register()
    window = bpy.context.window_manager.windows[0]
    areas = sorted(window.screen.areas, key=lambda a: a.width * a.height, reverse=True)
    view3d = next(a for a in areas if a.type == 'VIEW_3D')
    kanvas = next(a for a in areas if a != view3d and a.width * a.height > 40000)
    kanvas.type = 'NODE_EDITOR'
    kanvas.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI measure', 'KanvasNodeTree')
    space = kanvas.spaces.active
    space.node_tree = tree
    region = next(r for r in kanvas.regions if r.type == 'WINDOW')
    state.update(window=window, kanvas=kanvas, view3d=view3d, tree=tree, space=space,
                 region=region)
    # A dark image, so the amber and cyan marks and the white labels stand out.
    image = bpy.data.images.new('car', 400, 200, alpha=True)
    pixels = np.zeros((200, 400, 4), dtype=np.float32)
    pixels[:] = (0.12, 0.12, 0.12, 1.0)
    image.pixels.foreach_set(pixels.ravel())
    item = settings().images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'car', 'Car'
    item.image_data = image
    item.is_selected = True
    settings().active_image_index = 0
    from k_tools_kanvas.utils import measure as mm
    # The wheel: a rectangle 40 px wide and 50 px high, 66 cm high. Another mark: a line.
    wheel = mm.add_mark(item, 'RECT', (0.1, 0.25), (0.2, 0.5), 'Wheel')
    check(mm.set_scale(photo(), wheel.measure_id, 66.0, 'CM', 'HEIGHT') or False, 'wheel scale')
    state['wheel_id'] = photo().measures[0].measure_id
    line = mm.add_mark(photo(), 'LINE', (0.3, 0.5), (0.9, 0.5), 'Wheelbase')
    state['line_id'] = line.measure_id
    check(len(photo().measures) == 2 and photo().measure_active_index == 1, 'two marks')
    with override():
        bpy.ops.kanvas.focus_selection()
    scene = bpy.context.scene
    for obj in list(scene.objects):
        obj.hide_viewport = True


def step_tool_and_dialog():
    from k_tools_kanvas.operators.ops_modal import _shape_armed_areas
    from k_tools_kanvas.operators import ops_measure
    from k_tools_kanvas.utils import measure as mm
    window, kanvas = state['window'], state['kanvas']
    key = (window.as_pointer(), kanvas.as_pointer())
    # The tool arms the next drag and starts nothing.
    with override():
        result = bpy.ops.kanvas.measure_tool('INVOKE_DEFAULT', kind='LINE', purpose='SCALE')
    armed = _shape_armed_areas.get(key)
    check(result == {'CANCELLED'} and armed == 'MEASURE:SCALE:LINE:car', f'armed {result} {armed}')
    _shape_armed_areas.pop(key, None)
    # Shift holds a line to the image axes, a rectangle to a square.
    item = photo()
    end = ops_measure._constrained(item, (0.1, 0.1), (0.6, 0.12), 'LINE')
    check(abs(end[1] - 0.1) < 1e-6 and abs(end[0] - 0.6) < 0.01, f'horizontal line {end}')
    end = ops_measure._constrained(item, (0.1, 0.1), (0.3, 0.8), 'RECT')
    check(abs((end[0] - 0.1) * 400) - abs((end[1] - 0.1) * 200) < 1e-3, f'square {end}')
    # The dialog operator sets a scale from the line: 258 cm for its 240 px.
    with override():
        result = bpy.ops.kanvas.set_measure_scale('EXEC_DEFAULT', item_id='car',
                                                  measure_id=state['line_id'], value=2.4,
                                                  unit='M', side='LENGTH')
    check(result == {'FINISHED'} and photo().measure_scale_id == state['line_id'],
          f'scale from the line {result}')
    check(abs(mm.meters_per_pixel(photo()) - 0.01) < 1e-6, f'0.01 m a pixel {mm.meters_per_pixel(photo())}')
    # Back to the wheel as the scale: 66 cm for its 50 px.
    with override():
        result = bpy.ops.kanvas.set_measure_scale('EXEC_DEFAULT', item_id='car',
                                                  measure_id=state['wheel_id'], value=66.0,
                                                  unit='CM', side='HEIGHT')
    check(result == {'FINISHED'} and photo().measure_scale_id == state['wheel_id'], 'wheel scale again')
    mpp = mm.meters_per_pixel(photo())
    check(abs(mpp - 0.0132) < 1e-6, f'0.0132 m a pixel {mpp}')
    check(mm.mark_text(photo(), photo().measures[1], 'CM') == '316.8 cm',
          mm.mark_text(photo(), photo().measures[1], 'CM'))
    check(mm.mark_text(photo(), photo().measures[0], 'CM') == '52.8 × 66 cm',
          mm.mark_text(photo(), photo().measures[0], 'CM'))
    # The board reads in the unit of the first scale; changing it re-reads every mark.
    settings().measure_unit = 'IN'
    check(mm.mark_text(photo(), photo().measures[0], settings().measure_unit) == '20.79 × 25.98 in',
          mm.mark_text(photo(), photo().measures[0], settings().measure_unit))
    settings().measure_unit = 'CM'
    for item in settings().images:
        item.is_selected = False       # no selection outline: it is cyan like the marks


def canvas_shot(name):
    import numpy as np
    window, kanvas = state['window'], state['kanvas']
    path = os.path.join(tempfile.gettempdir(), f'kanvas_measure_{name}.png')
    with bpy.context.temp_override(window=window, area=kanvas):
        bpy.ops.screen.screenshot_area(filepath=path)
    shot = bpy.data.images.load(path, check_existing=False)
    width, height = shot.size
    pixels = np.array(shot.pixels[:], dtype=np.float32).reshape(height, width, 4)
    bpy.data.images.remove(shot)
    region = state['region']
    x0, y0 = region.x - kanvas.x, region.y - kanvas.y
    return pixels[y0:y0 + region.height, x0:x0 + region.width]


def count(pixels, test):
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    return int(test(r, g, b).sum())


def amber(r, g, b):
    return (r > 0.9) & (g > 0.55) & (g < 0.85) & (b < 0.35)


def cyan(r, g, b):
    return (r < 0.4) & (g > 0.75) & (b > 0.9)


def white(r, g, b):
    return (r > 0.9) & (g > 0.9) & (b > 0.9)


def near(point, radius=70):
    """Boolean mask helper: region pixels within radius of a canvas point."""
    import numpy as np
    region = state['region']
    x, y = region.view2d.view_to_region(point[0], point[1], clip=False)
    ys, xs = np.mgrid[0:region.height, 0:region.width]
    return (abs(xs - x) < radius) & (abs(ys - y) < radius)


def step_canvas():
    from k_tools_kanvas.utils import measure as mm
    pixels = canvas_shot('marks')
    wheel = photo().measures[0]
    line = photo().measures[1]
    wheel_at = near(mm.mark_label_point(photo(), wheel))
    line_at = near(mm.mark_label_point(photo(), line))
    a = count(pixels, lambda r, g, b: amber(r, g, b) & wheel_at)
    c = count(pixels, lambda r, g, b: cyan(r, g, b) & line_at)
    check(a > 40, f'the scale mark is amber ({a} pixels)')
    check(c > 40, f'the other mark is cyan ({c} pixels)')
    # A label: white text over a dark pill at the middle of each mark.
    w = count(pixels, lambda r, g, b: white(r, g, b) & wheel_at)
    check(w > 8, f'a label with the size on the wheel ({w} white pixels)')
    # Hiding the marks takes everything off.
    photo().measure_visible = False
    state['wheel_label'] = w


def step_hidden():
    from k_tools_kanvas.utils import measure as mm
    pixels = canvas_shot('hidden')
    wheel_at = near(mm.mark_label_point(photo(), photo().measures[0]))
    a = count(pixels, lambda r, g, b: amber(r, g, b) & wheel_at)
    check(a == 0, f'no marks when hidden ({a})')
    photo().measure_visible = True
    # --- Send to 3D View with Real Scale ---------------------------------------------------
    photo().is_selected = True
    settings().active_image_index = 0
    scene = bpy.context.scene
    scene.cursor.location = (0.0, 0.0, 0.0)
    with override():
        result = bpy.ops.kanvas.add_3d_reference('EXEC_DEFAULT', size=9.0)
    check(result == {'FINISHED'}, f'sent {result}')
    entry = scene.kanvas_references[0]
    obj = entry.object
    # 400 px wide, 0.0132 m a pixel: 5.28 m.
    check(entry.real_scale and abs(obj.empty_display_size - 5.28) < 1e-4,
          f'real size {entry.real_scale} {obj.empty_display_size}')
    # A new scale for the same mark: the Size follows from the timer.
    photo().measures[0].known_value = 33.0
    state['entry'] = entry


def step_follows_scale():
    entry = state['entry']
    check(abs(entry.object.empty_display_size - 2.64) < 1e-4,
          f'a new scale resizes the reference {entry.object.empty_display_size}')
    # Unit scale of the scene: a Blender unit is a centimeter.
    bpy.context.scene.unit_settings.scale_length = 0.01
    entry.real_scale = False
    entry.real_scale = True
    check(abs(entry.object.empty_display_size - 264.0) < 0.05,
          f'in units of the scene {entry.object.empty_display_size}')
    bpy.context.scene.unit_settings.scale_length = 1.0
    entry.real_scale = False
    entry.real_scale = True
    # A mask on the left half: the picture is half as wide, so half the real size.
    item = photo()
    polygon = item.mask_polygons.add()
    for uv in ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    photo().mask_enabled = True
    photo().mask_revision += 1


def step_follows_mask():
    entry = state['entry']
    check(abs(entry.object.empty_display_size - 1.32) < 1e-3,
          f'a mask resizes the reference {entry.object.empty_display_size}')
    # Real Scale off: the Size is the user's again.
    entry.real_scale = False
    entry.object.empty_display_size = 3.0
    photo().measures[0].known_value = 66.0
    state['photo_count'] = len(settings().images)


def step_uncalibrated_and_copy():
    from k_tools_kanvas.utils import measure as mm
    entry = bpy.context.scene.kanvas_references[0]
    check(abs(entry.object.empty_display_size - 3.0) < 1e-6, 'Real Scale off keeps the Size')
    # An image without a scale has no Real Scale: it uses Size.
    item = settings().images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'plain', 'Plain'
    item.image_data = bpy.data.images.new('plain', 100, 100)
    for other in settings().images:
        other.is_selected = other.item_id == 'plain'
    settings().active_image_index = next(i for i, x in enumerate(settings().images)
                                         if x.item_id == 'plain')
    with override():
        result = bpy.ops.kanvas.add_3d_reference('EXEC_DEFAULT', size=7.0)
    plain = bpy.context.scene.kanvas_references[-1]
    check(result == {'FINISHED'} and not plain.real_scale
          and abs(plain.object.empty_display_size - 7.0) < 1e-6,
          f'no scale, no real size {plain.real_scale} {plain.object.empty_display_size}')
    # Copies carry marks and scale.
    for other in settings().images:
        other.is_selected = other.item_id == 'car'
    settings().active_image_index = next(i for i, x in enumerate(settings().images)
                                         if x.item_id == 'car')
    with override():
        result = bpy.ops.kanvas.duplicate_image()
    copies = [i for i in settings().images if i.item_id not in {'car', 'plain'}]
    check(result == {'FINISHED'} and len(copies) == 1, f'duplicated {result} {len(copies)}')
    if copies:
        copy = copies[0]
        check(len(copy.measures) == 2 and copy.measure_scale_id == state['wheel_id']
              and abs(mm.meters_per_pixel(copy) - 0.0132) < 1e-6,
              f'the copy has the marks and the scale {len(copy.measures)} {copy.measure_scale_id}')
    # Removing the scale mark takes the scale with it.
    for other in settings().images:
        other.is_selected = other.item_id == 'car'
    settings().active_image_index = next(i for i, x in enumerate(settings().images)
                                         if x.item_id == 'car')
    photo().measure_active_index = 0
    with override():
        result = bpy.ops.kanvas.remove_measure()
    check(result == {'FINISHED'} and not photo().measure_scale_id and len(photo().measures) == 1
          and not mm.is_calibrated(photo()), f'removing the scale mark {result}')


STEPS = [setup, step_tool_and_dialog, step_canvas, step_hidden, step_follows_scale,
         step_follows_mask, step_uncalibrated_and_copy]


def tick():
    try:
        STEPS.pop(0)()
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        if STEPS:
            return 0.8
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    print('GUIMEASURE RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
