"""A cropped image with the mouse (simulated events): a click on the part the crop hides
does not select the image and a drag there does not move it; a click inside the crop selects
it and a drag moves it by the drag; the scale handles are at the corners of the crop, and
dragging one scales the image; a drag inside the crop still works after resetting the
bounds, and then a click in the old hidden part does select.

    blender --factory-startup --enable-event-simulate -P scratch/gui_crop_click.py
Prints GUICLICK RESULT OK, SKIPPED (no event simulation) or FAIL. Needs a window (not -b).
One event per timer tick, and one click spent on the splash screen: see
gui_measure_draw.py.
"""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []
state = {}


def check(condition, message):
    if not condition:
        errors.append(message)


class DefaultPrefs:
    """Stand in for the add-on preferences when run from a folder (see gui_measure_draw)."""

    def __init__(self):
        from k_tools_kanvas.preferences import KanvasPreferences
        self._props = {p.identifier: p for p in KanvasPreferences.bl_rna.properties}

    def __getattr__(self, name):
        prop = self.__dict__.get('_props', {}).get(name)
        if prop is None:
            raise AttributeError(name)
        if prop.type in {'FLOAT', 'INT', 'BOOLEAN'} and prop.array_length > 0:
            return tuple(prop.default_array)
        return prop.default


def photo():
    return next(i for i in state['tree'].kanvas_settings.images if i.item_id == 'photo')


def override():
    return bpy.context.temp_override(window=state['window'], area=state['kanvas'],
                                     region=state['region'], space_data=state['space'])


def window_xy(uv):
    from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv
    point = image_point_from_uv(photo(), uv)
    x, y = state['region'].view2d.view_to_region(point[0], point[1], clip=False)
    return int(state['region'].x + x), int(state['region'].y + y)


def send(kind, value, uv=None, xy=None, offset=(0, 0)):
    x, y = xy if xy is not None else window_xy(uv)
    state['window'].event_simulate(type=kind, value=value, x=x + offset[0], y=y + offset[1])


def setup():
    addon.register()
    from k_tools_kanvas.utils import item_crop
    from k_tools_kanvas.utils.gpu import gpu_common
    window = bpy.context.window_manager.windows[0]
    if not hasattr(window, 'event_simulate'):
        print('GUICLICK RESULT SKIPPED (start Blender with --enable-event-simulate)')
        bpy.ops.wm.quit_blender()
        return False
    prefs = DefaultPrefs()
    gpu_common._lookup_prefs = lambda: prefs
    areas = sorted(window.screen.areas, key=lambda a: a.width * a.height, reverse=True)
    kanvas = areas[0]
    kanvas.type = 'NODE_EDITOR'
    kanvas.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI click', 'KanvasNodeTree')
    space = kanvas.spaces.active
    space.node_tree = tree
    region = next(r for r in kanvas.regions if r.type == 'WINDOW')
    state.update(window=window, kanvas=kanvas, tree=tree, space=space, region=region)
    item = tree.kanvas_settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'photo', 'Photo'
    item.image_data = bpy.data.images.new('photo', 400, 200, alpha=True)
    item.is_selected = True
    tree.kanvas_settings.active_image_index = 0
    item_crop.set_crop(photo(), (0.05, 0.1, 0.45, 0.9))      # the left part of the image
    with override():
        bpy.ops.kanvas.focus_selection()
    return True


def deselect():
    photo().is_selected = False


def click(uv):
    return [lambda: send('MOUSEMOVE', 'NOTHING', uv), lambda: send('LEFTMOUSE', 'PRESS', uv),
            lambda: send('LEFTMOUSE', 'RELEASE', uv)]


def drag(uv, delta):
    """Press on an image point and drag by `delta` pixels. The start is worked out once:
    the image moves under the mouse, so its point would run away from later events."""
    base = {}

    def start():
        base['xy'] = window_xy(uv)
        send('MOUSEMOVE', 'NOTHING', xy=base['xy'])

    def at(kind, value, fraction):
        offset = (int(delta[0] * fraction), int(delta[1] * fraction))
        send(kind, value, xy=base['xy'], offset=offset)
    return [start, lambda: at('LEFTMOUSE', 'PRESS', 0.0), lambda: at('MOUSEMOVE', 'NOTHING', 0.5),
            lambda: at('MOUSEMOVE', 'NOTHING', 1.0), lambda: at('LEFTMOUSE', 'RELEASE', 1.0)]


def settle():
    """A pause for the editor to catch up."""


def build():
    corner = (state['region'].x + 6, state['region'].y + 6)
    inside, hidden = (0.25, 0.5), (0.8, 0.5)
    actions = [lambda: send('MOUSEMOVE', 'NOTHING', xy=corner), settle,
               lambda: send('LEFTMOUSE', 'PRESS', xy=corner),
               lambda: send('LEFTMOUSE', 'RELEASE', xy=corner), settle, settle, deselect, settle]
    # A click on the part the crop hides selects nothing.
    actions += click(hidden) + [settle, lambda: check(not photo().is_selected,
                                                        'a click on the hidden part selects nothing')]
    # A click inside the crop selects the image.
    actions += click(inside) + [settle, lambda: check(photo().is_selected, 'a click inside selects it')]
    # A drag on the hidden part moves nothing (it draws a selection box).
    actions += [lambda: state.update(location=tuple(photo().location)), deselect, settle]
    actions += drag(hidden, (60, 30)) + [settle, lambda: check(
        tuple(photo().location) == state['location'], 'a drag on the hidden part does not move it')]
    # A drag inside the crop moves the image by the drag.
    actions += click(inside) + [settle]
    actions += [lambda: state.update(location=tuple(photo().location), zoom=_pixel_size())]
    actions += drag(inside, (60, 30)) + [settle, check_moved]
    # The scale handle at the top right corner of the crop scales the image.
    actions += [lambda: state.update(scale=photo().scale_master)]
    actions += drag((0.45, 0.9), (50, 40)) + [settle, check_scaled]
    # After Reset Bounds a click on what was hidden selects.
    actions += [reset, settle, deselect, settle]
    actions += click(hidden) + [settle, lambda: check(photo().is_selected,
                                                        'after Reset Bounds the whole image is clickable')]
    return actions


def reset():
    with override():
        bpy.ops.kanvas.reset_bounds()


def _pixel_size():
    view = state['region'].view2d
    return abs(view.region_to_view(1, 0)[0] - view.region_to_view(0, 0)[0])


def check_moved():
    start = state['location']
    now = tuple(photo().location)
    expected = (60 * state['zoom'], 30 * state['zoom'])
    check(abs((now[0] - start[0]) - expected[0]) < 3 * state['zoom']
          and abs((now[1] - start[1]) - expected[1]) < 3 * state['zoom'],
          f'a drag inside moved it by the drag {now} from {start} (wanted about {expected})')


def check_scaled():
    check(photo().scale_master > state['scale'] * 1.02,
          f'the handle at the crop corner scales it {state["scale"]} -> {photo().scale_master}')


ACTIONS = []


def tick():
    try:
        if 'ready' not in state:
            state['ready'] = setup()
            if not state['ready']:
                return None
            ACTIONS.extend(build())
            return 0.8
        if ACTIONS:
            ACTIONS.pop(0)()
            for area in bpy.context.window_manager.windows[0].screen.areas:
                area.tag_redraw()
            return 0.35
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    print('GUICLICK RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
