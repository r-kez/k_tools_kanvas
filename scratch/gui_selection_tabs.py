"""Draws the Selection panel in a real sidebar with every tab of an image, a shape (with
a gradient) and a text card, and checks that Blender reports no drawing error.

    blender --factory-startup -P scratch/gui_selection_tabs.py
Prints GUITABS RESULT OK or FAIL. Needs a window (not -b).
"""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []
plan = []
state = {'draws': 0}


def setup():
    addon.register()
    window = bpy.context.window_manager.windows[0]
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI tabs', 'KanvasNodeTree')
    space = area.spaces.active
    space.node_tree = tree
    space.show_region_ui = True
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
        bpy.ops.kanvas.create_shape(kind='STAR', location=(0.0, 0.0), size=(100.0, 100.0))
    shape = settings.images[-1]
    shape.shape_fill_type = 'LINEAR'
    image = settings.images.add()
    image.item_type, image.item_id, image.name = 'IMAGE', 'image', 'Photo'
    image.image_data = bpy.data.images.new('photo', 8, 8)
    card = settings.images.add()
    card.item_type, card.item_id, card.name = 'TEXT', 'card', 'Note'
    card.text_checklist = True
    card.text_lines.add().value = 'task'
    ui = next(r for r in area.regions if r.type == 'UI')
    state['ui'] = ui
    for item_id, kind in ((shape.item_id, 'shape'), ('image', 'image'), ('card', 'text')):
        for tab in addon.ui.tabs.TABS[kind] if hasattr(addon, 'ui') else ():
            plan.append((settings, item_id, kind, tab))
    if not plan:
        from k_tools_kanvas.ui.tabs import TABS
        for item_id, kind in ((shape.item_id, 'shape'), ('image', 'image'), ('card', 'text')):
            for tab in TABS[kind]:
                plan.append((settings, item_id, kind, tab))


def move_panels():
    # The sidebar tab cannot be chosen from Python: move the Kanvas panels to the
    # tab that is open instead (unregistered children first, registered parents first).
    category = state['ui'].active_panel_category
    panels = [cls for cls in bpy.types.Panel.__subclasses__()
              if getattr(cls, 'bl_category', '') == 'K-Tools'
              and cls.__module__.startswith('k_tools_kanvas')]
    def depth(cls):
        parent, n = getattr(cls, 'bl_parent_id', ''), 0
        while parent:
            n += 1
            parent = getattr(getattr(bpy.types, parent, None), 'bl_parent_id', '')
        return n
    panels.sort(key=depth)
    for cls in reversed(panels):
        bpy.utils.unregister_class(cls)
    for cls in panels:
        cls.bl_category = category
        bpy.utils.register_class(cls)
    from k_tools_kanvas.ui.selection_panel import KANVAS_PT_SelectionPanel
    real_draw = KANVAS_PT_SelectionPanel.draw

    def counted(self, context):
        state['draws'] += 1
        try:
            real_draw(self, context)
        except Exception as exc:
            errors.append(f'{state.get("now")}: {exc!r}')
            raise
    KANVAS_PT_SelectionPanel.draw = counted


def step():
    if not state.get('moved'):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        move_panels()
        state['moved'] = True
        return 0.2
    if not plan:
        if state['draws'] < 10:
            errors.append(f"the Selection panel drew only {state['draws']} times")
        print('GUITABS RESULT', 'OK' if not errors else 'FAIL')
        for error in errors:
            print('  ', error)
        sys.stdout.flush()
        bpy.ops.wm.quit_blender()
        return None
    settings, item_id, kind, tab = plan.pop(0)
    state['now'] = f'{kind} {tab}'
    for index, item in enumerate(settings.images):
        item.is_selected = item.item_id == item_id
        if item.item_id == item_id:
            settings.active_image_index = index
    setattr(bpy.context.window_manager.kanvas_tabs, kind, tab)
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    import os
    folder = os.environ.get('KANVAS_SHOTS')
    if folder and not state.get('settled'):
        # Let Blender finish moving the panels before the picture is taken.
        state['settled'] = True
        plan.insert(0, (settings, item_id, kind, tab))
        return 0.6
    state['settled'] = False
    if folder:
        # Optional: a screenshot of every tab, to look at the layout.
        bpy.ops.screen.screenshot(filepath=os.path.join(folder, f'{kind}_{tab}.png'))
        ui = state['ui']
        with open(os.path.join(folder, 'sidebar.txt'), 'w') as handle:
            handle.write(f'{ui.x} {ui.y} {ui.width} {ui.height}')
    return 0.05


_original_excepthook = sys.excepthook


def _record(kind, value, trace):
    errors.append(f'{kind.__name__}: {value}')
    _original_excepthook(kind, value, trace)


sys.excepthook = _record
setup()
bpy.app.timers.register(step, first_interval=1.0)
