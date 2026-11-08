"""Draws shapes with holes, open paths, curves and Edit Vertices in a real window and
checks that the GPU code runs without errors and reuses its batches.

    blender --factory-startup -P scratch/gui_shape_draw.py
Prints GUIDRAW RESULT OK or FAIL. Needs a window (not -b).
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import shape_geometry as sg

state = {'step': 0, 'errors': []}


def setup():
    addon.register()
    window = bpy.context.window_manager.windows[0]
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI shapes', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    from k_tools_kanvas.operators.ops_shape import (PolygonSession, combine_shapes,
                                                    set_vertex_type)
    with bpy.context.temp_override(window=window, area=area, region=region,
                                   space_data=area.spaces.active):
        for kind, location, size in (('RECTANGLE', (0, 0), (300, 300)),
                                     ('ELLIPSE', (0, 0), (150, 150)),
                                     ('STAR', (400, 0), (200, 200))):
            bpy.ops.kanvas.create_shape(kind=kind, location=location, size=size)
        ring = combine_shapes(bpy.context, settings, list(settings.images)[:2],
                              settings.images[0])
        star = next(item for item in settings.images if item.shape_kind == 'STAR')
        set_vertex_type(star, [0, 2, 4], 'AUTO')
        star.shape_line_style = 'DASHED'
        star.shape_line_cap = 'SQUARE'
        star.shape_line_join = 'MITER'
        star.shape_line_align = 'OUTSIDE'
        star.shape_line_width = 8.0
        bpy.ops.kanvas.create_shape(kind='TRIANGLE', location=(150, 120), size=(120, 90))
        triangle = settings.images[-1]
        triangle.shape_corner_radius = 15.0
        triangle.shape_line_join = 'BEVEL'
        triangle.shape_line_align = 'INSIDE'
        picture = settings.images.add()
        picture.item_type, picture.item_id, picture.name = 'IMAGE', 'gui_picture', 'Picture'
        picture.image_data = bpy.data.images.new('gui picture', 64, 64, alpha=True)
        picture.location = (-60.0, 60.0)
        picture.z_index = 0
        pen = PolygonSession('PEN')
        pen.add_point(bpy.context, settings, (-140.0, -60.0))
        pen.add_point(bpy.context, settings, (-60.0, -100.0))
        pen.drag_handle(settings, (-20.0, -40.0))
        pen.add_point(bpy.context, settings, (100.0, -110.0))
        pen.finish(bpy.context, settings)
        settings.images[settings.active_image_index].shape_line_cap = 'FLAT'
        ring = next(item for item in settings.images
                    if len(sg.item_contour_ranges(item)) > 1)
        for item in settings.images:
            item.is_selected = item.item_id == ring.item_id
        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_id == ring.item_id)
        ring.shape_edit_vertices = True
        ring.shape_vertices[0].select = True
        bpy.ops.kanvas.focus_selection() if bpy.ops.kanvas.focus_selection.poll() else None
    # The add-on loaded by this script has no preferences: turn the editing focus on.
    from types import SimpleNamespace
    from k_tools_kanvas.utils.gpu import gpu_focus
    gpu_focus.get_prefs = lambda: SimpleNamespace(focus_dim_enabled=True, focus_dim_amount=0.5,
                                                  focus_desaturate=True,
                                                  focus_desaturate_amount=1.0)
    state['area'] = area
    state['settings'] = settings


def tick():
    captured = io.StringIO()
    try:
        if state['step'] == 0:
            setup()
        state['area'].tag_redraw()
        with redirect_stdout(captured):
            bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=3)
    except Exception as exc:   # noqa: BLE001 - report anything
        state['errors'].append(repr(exc))
    output = captured.getvalue()
    sys.stdout.write(output)
    state['errors'].extend(line for line in output.splitlines()
                           if line.startswith(('Kanvas shape', 'Kanvas editing focus',
                                               'Kanvas vertex edit'))
                           or 'Traceback' in line)
    state['step'] += 1
    if state['step'] < 4:
        return 0.2
    from k_tools_kanvas.utils.gpu import gpu_shape
    region = next(r for r in state['area'].regions if r.type == 'WINDOW')
    view = region.view2d
    bounds = (*view.region_to_view(0, 0), *view.region_to_view(region.width, region.height))
    shapes = [item for item in state['settings'].images
              if item.item_type == 'SHAPE' and gpu_shape._visible(item, bounds)]
    print('GUIDRAW visible shapes:', [item.name for item in shapes], flush=True)
    if not shapes:
        state['errors'].append('no shape in view')
    cached = sum(1 for item in shapes if item.as_pointer() in gpu_shape._batch_cache)
    if cached != len(shapes):
        state['errors'].append(f'batches cached for {cached} of {len(shapes)} shapes')
    else:
        before = {item.as_pointer(): gpu_shape._batch_cache[item.as_pointer()][1] for item in shapes}
        state['area'].tag_redraw()
        bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
        reused = all(gpu_shape._batch_cache[key][1] is batches for key, batches in before.items())
        if not reused:
            state['errors'].append('batches rebuilt for unchanged shapes')
    print('GUIDRAW RESULT', 'OK' if not state['errors'] else 'FAIL ' + str(state['errors']),
          flush=True)
    addon.unregister()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
