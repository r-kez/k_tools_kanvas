"""Drawing a mark with the mouse, on a real window with simulated mouse events: the Draw Mark
tool arms the next drag, a press-drag-release on the image draws a line or a rectangle in
image coordinates, Shift holds a line to the image axes, a click without a drag draws
nothing, Escape cancels a drag and removes the mark, and Escape while armed disarms the
tool. A mark made for the scale opens the dialog after the release.

    blender --factory-startup --enable-event-simulate -P scratch/gui_measure_draw.py
Prints GUIDRAW RESULT OK, SKIPPED (no event simulation) or FAIL. Needs a window (not -b).

Events are sent one per timer tick: an operator started from inside another (a press
that starts the drag) reads the window's current mouse position, which a burst of
queued events would already have moved to the last one.
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


def photo():
    return next(i for i in state['tree'].kanvas_settings.images if i.item_id == 'car')


def settings():
    return state['tree'].kanvas_settings


def override():
    return bpy.context.temp_override(window=state['window'], area=state['kanvas'],
                                     region=state['region'], space_data=state['space'])


def window_xy(uv):
    """Window coordinates of an image point, for simulated events."""
    from k_tools_kanvas.utils.arrow_geometry import image_point_from_uv
    point = image_point_from_uv(photo(), uv)
    region = state['region']
    x, y = region.view2d.view_to_region(point[0], point[1], clip=False)
    return int(region.x + x), int(region.y + y)


def send(kind, value, uv=None, shift=False, xy=None):
    x, y = xy if xy is not None else window_xy(uv)
    state['window'].event_simulate(type=kind, value=value, x=x, y=y, shift=shift)


class DefaultPrefs:
    """Run from a folder, the add-on is not installed and has no preferences, but the
    canvas operators need them: stand in with the default of every preference."""

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


def setup():
    addon.register()
    from k_tools_kanvas.utils.gpu import gpu_common
    prefs = DefaultPrefs()
    gpu_common._lookup_prefs = lambda: prefs
    window = bpy.context.window_manager.windows[0]
    if not hasattr(window, 'event_simulate'):
        print('GUIDRAW RESULT SKIPPED (start Blender with --enable-event-simulate)')
        bpy.ops.wm.quit_blender()
        return False
    areas = sorted(window.screen.areas, key=lambda a: a.width * a.height, reverse=True)
    kanvas = areas[0]
    kanvas.type = 'NODE_EDITOR'
    kanvas.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI draw', 'KanvasNodeTree')
    space = kanvas.spaces.active
    space.node_tree = tree
    region = next(r for r in kanvas.regions if r.type == 'WINDOW')
    state.update(window=window, kanvas=kanvas, tree=tree, space=space, region=region)
    image = bpy.data.images.new('car', 400, 200, alpha=True)
    item = tree.kanvas_settings.images.add()
    item.item_type, item.item_id, item.name = 'IMAGE', 'car', 'Car'
    item.image_data = image
    item.is_selected = True
    tree.kanvas_settings.active_image_index = 0
    with override():
        bpy.ops.kanvas.focus_selection()
    return True


def arm(kind, purpose='MARK'):
    with override():
        bpy.ops.kanvas.measure_tool('INVOKE_DEFAULT', kind=kind, purpose=purpose)


def drag(kind, purpose, start, end, middle=None, shift=False, release=True):
    """The actions of one drawn mark: arm the tool, press, move, release."""
    actions = [lambda: arm(kind, purpose),
               lambda: send('MOUSEMOVE', 'NOTHING', start),
               lambda: send('LEFTMOUSE', 'PRESS', start)]
    if middle is not None:
        actions.append(lambda: send('MOUSEMOVE', 'NOTHING', middle))
    actions.append(lambda: send('MOUSEMOVE', 'NOTHING', end, shift=shift))
    if release:
        actions.append(lambda: send('LEFTMOUSE', 'RELEASE', end, shift=shift))
    return actions


def corner():
    return (state['region'].x + 6, state['region'].y + 6)


def settle():
    """Nothing to send: a pause for the editor to catch up."""


def check_line():
    marks = photo().measures
    check(len(marks) == 1, f'a line was drawn ({len(marks)} marks)')
    if marks:
        mark = marks[0]
        check(mark.kind == 'LINE' and abs(mark.p0[0] - 0.2) < 0.02 and abs(mark.p0[1] - 0.3) < 0.02
              and abs(mark.p1[0] - 0.8) < 0.02 and abs(mark.p1[1] - 0.6) < 0.02,
              f'line from {tuple(mark.p0)} to {tuple(mark.p1)}')
        check(mark.name == 'Line 1' and not photo().measure_scale_id, 'a plain mark')


def check_rect():
    marks = photo().measures
    check(len(marks) == 2 and marks[1].kind == 'RECT', f'a rectangle was drawn ({len(marks)})')
    if len(marks) == 2:
        check(abs(marks[1].p0[0] - 0.1) < 0.02 and abs(marks[1].p1[0] - 0.3) < 0.02
              and abs(marks[1].p1[1] - 0.4) < 0.02,
              f'rectangle {tuple(marks[1].p0)} {tuple(marks[1].p1)}')


def check_shift():
    marks = photo().measures
    check(len(marks) == 3, f'a straight line ({len(marks)})')
    if len(marks) == 3:
        check(abs(marks[2].p1[1] - marks[2].p0[1]) < 1e-4,
              f'held horizontal {tuple(marks[2].p0)} {tuple(marks[2].p1)}')


def check_click():
    check(len(photo().measures) == 3, f'a click draws nothing ({len(photo().measures)})')


def check_escape_drag():
    check(len(photo().measures) == 3, f'Escape cancels the drag ({len(photo().measures)})')


def check_disarmed():
    from k_tools_kanvas.operators.ops_modal import _shape_armed_areas
    key = (state['window'].as_pointer(), state['kanvas'].as_pointer())
    check(key not in _shape_armed_areas, 'Escape disarms the tool')
    check(len(photo().measures) == 3, 'nothing was drawn')


def check_scale_mark():
    marks = photo().measures
    check(len(marks) == 4 and marks[3].name == 'Scale', f'the scale mark was drawn ({len(marks)})')


def check_dialog_dismissed():
    check(len(photo().measures) == 4 and not photo().measure_scale_id,
          'the mark stays when the dialog is dismissed')


def build_actions():
    # The splash screen closes with the first click and swallows it: spend one on a corner
    # of the canvas (empty, so it changes nothing).
    actions = [lambda: send('MOUSEMOVE', 'NOTHING', xy=corner()), settle,
               lambda: send('LEFTMOUSE', 'PRESS', xy=corner()),
               lambda: send('LEFTMOUSE', 'RELEASE', xy=corner()), settle, settle]
    actions += drag('LINE', 'MARK', (0.2, 0.3), (0.8, 0.6), middle=(0.5, 0.45))
    actions += [settle, check_line]
    actions += drag('RECT', 'MARK', (0.1, 0.1), (0.3, 0.4))
    actions += [settle, check_rect]
    actions += drag('LINE', 'MARK', (0.2, 0.8), (0.7, 0.83), shift=True)
    actions += [settle, check_shift]
    # A click without a drag draws nothing.
    actions += [lambda: arm('LINE'), lambda: send('MOUSEMOVE', 'NOTHING', (0.5, 0.5)),
                lambda: send('LEFTMOUSE', 'PRESS', (0.5, 0.5)),
                lambda: send('LEFTMOUSE', 'RELEASE', (0.5, 0.5)), settle, check_click]
    # Escape during the drag removes the mark.
    actions += drag('LINE', 'MARK', (0.4, 0.2), (0.6, 0.4), release=False)
    actions += [lambda: send('ESC', 'PRESS', (0.6, 0.4)), settle, check_escape_drag]
    # Escape while armed disarms the tool.
    actions += [lambda: arm('LINE'), lambda: send('MOUSEMOVE', 'NOTHING', (0.5, 0.5)),
                lambda: send('ESC', 'PRESS', (0.5, 0.5)), settle, check_disarmed]
    # A mark for the scale: after the release the dialog asks for the real size.
    actions += drag('LINE', 'SCALE', (0.2, 0.9), (0.6, 0.9))
    actions += [settle, check_scale_mark,
                lambda: send('ESC', 'PRESS', xy=(state['region'].x + 5, state['region'].y + 5)),
                settle, check_dialog_dismissed]
    return actions


ACTIONS = []


def tick():
    try:
        if 'ready' not in state:
            state['ready'] = setup()
            if not state['ready']:
                return None
            ACTIONS.extend(build_actions())
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
    print('GUIDRAW RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
