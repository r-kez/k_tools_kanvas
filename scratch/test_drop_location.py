"""Dropped files land under the pointer: images and SVG files (one or several) are
added where they are dropped, not in the middle of the view; the SVG drop handler
exists only for Kanvas trees; the axis lines span the whole view."""
import math
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_image import KANVAS_OT_AddImage, drop_location, view_center
from k_tools_kanvas.operators.ops_shape import KANVAS_FH_SVG, KANVAS_OT_ImportShapesSVG
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.gpu.gpu_grid import axis_segments


def close(a, b, tol=0.5):
    return math.dist(a, b) < tol


# Axis lines: from edge to edge of the view, and absent when the origin line is off screen.
horizontal, vertical = axis_segments((-5000.0, -20.0, 7000.0, 30.0))
assert horizontal == ((-5000.0, 0.0), (7000.0, 0.0)) and vertical == ((0.0, -20.0), (0.0, 30.0))
assert axis_segments((10.0, 10.0, 20.0, 20.0)) == (None, None)

addon.register()
try:
    assert hasattr(bpy.types, 'KANVAS_FH_SVG') and KANVAS_FH_SVG.bl_file_extensions == '.svg'
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    region = next(r for r in area.regions if r.type == 'WINDOW')
    space = area.spaces.active
    folder = tempfile.mkdtemp()
    with bpy.context.temp_override(area=area, region=region, space_data=space):
        assert not KANVAS_FH_SVG.poll_drop(bpy.context), 'only in a Kanvas tree'
        area.ui_type = 'KanvasNodeTree'
        tree = bpy.data.node_groups.new('Drop', 'KanvasNodeTree')
        space.node_tree = tree
        settings = tree.kanvas_settings
        assert KANVAS_FH_SVG.poll_drop(bpy.context)
        context = bpy.context
        assert region.width > 40 and region.height > 40, (region.width, region.height)

        # The pointer, well away from the middle of the view.
        pointer = SimpleNamespace(mouse_region_x=15, mouse_region_y=20)
        target = drop_location(context, pointer)
        assert target is not None and not close(target, view_center(context), 1.0)
        assert close(target, tuple(region.view2d.region_to_view(15, 20)), 1e-6)
        outside = SimpleNamespace(mouse_region_x=-5, mouse_region_y=20)
        assert drop_location(context, outside) is None

        # An image lands centered on the pointer.
        image = bpy.data.images.new('Dropped', 32, 32)
        path = os.path.join(folder, 'dropped.png')
        image.filepath_raw = path
        image.file_format = 'PNG'
        image.save()
        bpy.data.images.remove(image)
        reports = []
        stand_in = SimpleNamespace(files=[], filepath=path, directory='',
                                   report=lambda kind, message: reports.append(message))
        stand_in.execute = lambda ctx: KANVAS_OT_AddImage.execute(stand_in, ctx)
        assert KANVAS_OT_AddImage.invoke(stand_in, context, pointer) == {'FINISHED'}, reports
        dropped = next(item for item in settings.images if item.item_type == 'IMAGE')
        assert close(tuple(dropped.location), target), (tuple(dropped.location), target)

        # An SVG lands centered on the pointer; several files line up from there.
        svg = ('<svg xmlns="http://www.w3.org/2000/svg"><rect id="box" x="0" y="0" '
               'width="100" height="50" fill="red"/></svg>')
        names = []
        for number in range(2):
            name = f'drop{number}.svg'
            open(os.path.join(folder, name), 'w', encoding='utf-8').write(svg)
            names.append(name)

        def svg_stand_in(**fields):
            stand = SimpleNamespace(fit_size=False, size=400.0, group=True,
                                    report=lambda kind, message: reports.append(message),
                                    **fields)
            stand.execute = lambda ctx: KANVAS_OT_ImportShapesSVG.execute(stand, ctx)
            stand._paths = lambda: KANVAS_OT_ImportShapesSVG._paths(stand)
            return stand

        one = svg_stand_in(filepath=os.path.join(folder, names[0]), files=[], directory='')
        assert KANVAS_OT_ImportShapesSVG.invoke(one, context, pointer) == {'FINISHED'}, reports
        box = next(item for item in settings.images if item.item_type == 'SHAPE')
        assert close(tuple(box.location), target), (tuple(box.location), target)
        for item in list(settings.images):
            item.is_selected = False
        before = {item.item_id for item in settings.images}
        several = svg_stand_in(filepath='', directory=folder,
                               files=[SimpleNamespace(name=name) for name in names])
        assert KANVAS_OT_ImportShapesSVG.invoke(several, context, pointer) == {'FINISHED'}
        new = sorted((item for item in settings.images
                      if item.item_type == 'SHAPE' and item.item_id not in before),
                     key=lambda item: item.location[0])
        assert len(new) == 2 and close(tuple(new[0].location), target)
        gap = sg.bounds(new[1])[0] - sg.bounds(new[0])[2]
        assert abs(gap - 40.0) < 0.5 and abs(new[1].location[1] - target[1]) < 0.5, gap
        assert all(item.is_selected for item in new)

    print('DROP LOCATION PASS')
finally:
    addon.unregister()
