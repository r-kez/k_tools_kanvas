"""Drawing with the pencil on a real window with simulated mouse events: the first stroke
makes a Pencil Drawing, the next ones join it, Esc/E leave it, a stroke after that makes
a second drawing, and E on the first draws on it again.

    blender --factory-startup --enable-event-simulate -P scratch/gui_pencil.py
Prints GUIPENCIL RESULT OK, SKIPPED or FAIL. Needs a window (not -b). One event per
timer tick (see gui_measure_draw.py).
"""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

state = {'step': 0, 'queue': []}
errors = []
report = []


class DefaultPrefs:
    def __init__(self):
        from k_tools_kanvas.preferences import KanvasPreferences
        self._props = {p.identifier: p for p in KanvasPreferences.bl_rna.properties}

    def __getattr__(self, name):
        prop = self._props.get(name) if '_props' in self.__dict__ else None
        if prop is None:
            raise AttributeError(name)
        if prop.type in {'FLOAT', 'INT', 'BOOLEAN'} and prop.array_length > 0:
            return tuple(prop.default_array)
        return prop.default


def check(condition, message):
    if not condition:
        errors.append(message)


def settings():
    return state['tree'].kanvas_settings


def drawings():
    return [i for i in settings().images if i.item_type == 'SHAPE' and i.shape_kind == 'PENCIL']


def send(kind, value, x, y, ctrl=False):
    state['window'].event_simulate(type=kind, value=value, x=x, y=y, ctrl=ctrl)


def stroke_events(points):
    """Press at the first point, move through the rest, release at the last."""
    x0, y0 = points[0]
    events = [('MOUSEMOVE', 'NOTHING', x0, y0), ('LEFTMOUSE', 'PRESS', x0, y0)]
    events += [('MOUSEMOVE', 'NOTHING', x, y) for x, y in points[1:]]
    x1, y1 = points[-1]
    events.append(('LEFTMOUSE', 'RELEASE', x1, y1))
    return events


def tool_id():
    tool = state['window'].workspace.tools.from_space_node()
    return None if tool is None else tool.idname


def run_in_area(fn):
    with bpy.context.temp_override(window=state['window'], area=state['area'],
                                   region=state['region']):
        fn()


def tick():
    window = bpy.context.window_manager.windows[0]
    if state['step'] == 0:
        addon.register()
        from k_tools_kanvas.utils.gpu import gpu_common
        prefs = DefaultPrefs()
        gpu_common._lookup_prefs = lambda: prefs
        if not hasattr(window, 'event_simulate'):
            print('GUIPENCIL RESULT SKIPPED (start Blender with --enable-event-simulate)')
            bpy.ops.wm.quit_blender()
            return None
        area = max(window.screen.areas, key=lambda a: a.width * a.height)
        area.type = 'NODE_EDITOR'
        area.ui_type = 'KanvasNodeTree'
        tree = bpy.data.node_groups.new('GUI pencil', 'KanvasNodeTree')
        area.spaces.active.node_tree = tree
        state.update(window=window, area=area, tree=tree,
                     region=next(r for r in area.regions if r.type == 'WINDOW'))
        state['step'] = 1
        return 0.5

    if state['queue']:
        kind, value, x, y, *modifiers = state['queue'].pop(0)
        send(kind, value, x, y, *modifiers)
        return 0.15

    region = state['region']
    cx, cy = region.x + region.width // 2, region.y + region.height // 2
    step = state['step']
    state['step'] += 1

    def wave(dx, dy, count=14):
        return [(cx + dx + i * 12, cy + dy + int(30 * (1 if i % 2 else -1) * 0.3) + i * 3)
                for i in range(count)]

    if step == 1:                                        # splash click, then the tool
        state['queue'] = [('LEFTMOUSE', 'PRESS', region.x + 3, region.y + 3),
                          ('LEFTMOUSE', 'RELEASE', region.x + 3, region.y + 3)]
        return 0.5
    if step == 2:
        run_in_area(lambda: bpy.ops.wm.tool_set_by_id(name='kanvas.pencil',
                                                      space_type='NODE_EDITOR'))
        check(tool_id() == 'kanvas.pencil', f'tool is {tool_id()}')
        state['queue'] = stroke_events(wave(-120, 0))
        return 0.6
    if step == 3:
        check(len(drawings()) == 1, f'one stroke made {len(drawings())} drawings')
        if drawings():
            check(len(drawings()[0].shape_strokes) == 1, 'first drawing has one stroke')
            report.append(('after 1', len(drawings()), len(drawings()[0].shape_strokes),
                           tuple(round(v) for v in (drawings()[0].shape_width,
                                                    drawings()[0].shape_height))))
        state['queue'] = stroke_events(wave(-120, 60))
        return 0.6
    if step == 4:
        check(len(drawings()) == 1, f'second stroke made {len(drawings())} drawings')
        if drawings():
            check(len(drawings()[0].shape_strokes) == 2, 'second stroke joined the drawing')
        # leave: Esc
        state['queue'] = [('ESC', 'PRESS', cx, cy), ('ESC', 'RELEASE', cx, cy)]
        return 0.6
    if step == 5:
        check(not any(d.pencil_editing for d in drawings()), 'Esc left the drawing')
        check(tool_id() == 'kanvas.edit', f'Esc went back to Edit, tool is {tool_id()}')
        run_in_area(lambda: bpy.ops.wm.tool_set_by_id(name='kanvas.pencil',
                                                      space_type='NODE_EDITOR'))
        state['queue'] = stroke_events(wave(100, -80))
        return 0.6
    if step == 6:
        check(len(drawings()) == 2, f'a stroke after leaving made {len(drawings())} drawings')
        report.append(('after leave', len(drawings()),
                       [len(d.shape_strokes) for d in drawings()]))
        report.append(('items', len(settings().images)))
        # Ctrl+click on the second stroke of the first drawing (it is not being drawn on)
        from k_tools_kanvas.utils import shape_geometry, pencil
        first = drawings()[0]
        state['first'] = first.item_id
        points = pencil.decode(first.shape_strokes[1].data)
        mid = points[len(points) // 2]
        canvas = shape_geometry.unit_to_canvas(first, mid[:2])
        sx, sy = region.view2d.view_to_region(canvas[0], canvas[1], clip=False)
        state['target'] = (region.x + int(sx), region.y + int(sy))
        run_in_area(lambda: bpy.ops.wm.tool_set_by_id(name='kanvas.pencil',
                                                      space_type='NODE_EDITOR'))
        x, y = state['target']
        state['queue'] = [('MOUSEMOVE', 'NOTHING', x, y, True),
                          ('LEFTMOUSE', 'PRESS', x, y, True),
                          ('LEFTMOUSE', 'RELEASE', x, y, True)]
        return 0.6
    if step == 7:
        first = next(i for i in settings().images if i.item_id == state['first'])
        picked = [i for i, st in enumerate(first.shape_strokes) if st.selected]
        report.append(('picked', picked))
        check(picked == [1], f'Ctrl+click picked {picked}')
        check(first.is_selected and first.pencil_editing, 'picking selected the drawing')
        check(len(drawings()) == 2, 'picking made no drawing')
        check(len(first.shape_strokes) == 2, 'picking drew nothing')
        settings().pencil_color = (1.0, 0.0, 0.0)
        check(tuple(first.shape_strokes[1].color) == (1.0, 0.0, 0.0), 'color reached the pick')
        check(tuple(first.shape_strokes[0].color) != (1.0, 0.0, 0.0), 'other stroke kept its color')
        x, y = state['target']
        state['queue'] = [('X', 'PRESS', x, y), ('X', 'RELEASE', x, y)]
        return 0.6
    if step == 8:
        first = next(i for i in settings().images if i.item_id == state['first'])
        report.append(('strokes after X', len(first.shape_strokes)))
        check(len(first.shape_strokes) == 1, f'X left {len(first.shape_strokes)} strokes')
        check(first.name in settings().images, 'the drawing itself stayed')
        return 0.3

    for entry in report:
        print('GUIPENCIL', entry)
    for message in errors:
        print('GUIPENCIL ERROR', message)
    print('GUIPENCIL RESULT', 'FAIL' if errors else 'OK')
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
