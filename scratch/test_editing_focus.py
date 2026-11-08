"""Editing focus and Edit Vertices as a mode: the item being edited (an image in Mask or
Color, a shape in Edit Vertices) is left out of the dimming, the dimming covers the
rest of the region, the preference is on by default, and E enters and leaves Edit
Vertices (ellipses included, now that they are curves)."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators.ops_modal import toggle_vertex_edit
from k_tools_kanvas.preferences import KanvasPreferences
from k_tools_kanvas.utils import shape_geometry as sg
from k_tools_kanvas.utils.gpu import gpu_focus
from k_tools_kanvas.utils.gpu.gpu_shape import vertex_edit_shape


def polygon_area(points):
    return abs(sg.signed_area(list(points)))


addon.register()
try:
    assert KanvasPreferences.bl_rna.properties['focus_dim_enabled'].default is True
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Focus', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        image = settings.images.add()
        image.item_type, image.item_id, image.name = 'IMAGE', 'photo', 'Photo'
        image.image_data = bpy.data.images.new('photo', 40, 20)
        image.location = (0.0, 0.0)
        assert gpu_focus.focus_item(settings) is None
        assert gpu_focus.focus_hole(settings, region) is None, 'nothing edited, no dimming'

        # Mask (or Color) editing: the hole is the image, a little larger.
        image.mask_editing = True
        assert gpu_focus.focus_item(settings) == ('IMAGE', image)
        hole = gpu_focus.focus_hole(settings, region)
        assert hole is not None and len(hole) == 4
        view = region.view2d
        corners = [tuple(view.view_to_region(x, y, clip=False))
                   for x, y in ((-20, -10), (20, -10), (20, 10), (-20, 10))]
        assert polygon_area(hole) > polygon_area(corners), 'the hole is a bit larger'
        cx = sum(p[0] for p in hole) / 4
        center = view.view_to_region(0.0, 0.0, clip=False)
        assert abs(cx - center[0]) < 2.0
        triangles = gpu_focus.dim_triangles(region.width, region.height, hole)
        dimmed = sum(polygon_area(triangles[i:i + 3]) for i in range(0, len(triangles), 3))
        expected = region.width * region.height - polygon_area(hole)
        assert abs(dimmed - expected) < 0.01 * region.width * region.height, (dimmed, expected)
        # Zoomed in: the hole's corners lie far outside the region. Inside the region,
        # a point is dimmed exactly when it is outside the hole.
        def covered(triangles, point):
            for i in range(0, len(triangles), 3):
                a, b, c = triangles[i:i + 3]
                d1 = (point[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (point[1] - b[1])
                d2 = (point[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (point[1] - c[1])
                d3 = (point[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (point[1] - a[1])
                if not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0)):
                    return True
            return False

        width, height = 400, 300
        cases = {
            'corner far away': [(-50000.0, -20000.0), (150.0, -30000.0), (200.0, 150.0),
                                (-40000.0, 90000.0)],
            'half out': [(300.0, 100.0), (900.0, 100.0), (900.0, 200.0), (300.0, 200.0)],
            'covers all': [(-1e6, -1e6), (1e6, -1e6), (1e6, 1e6), (-1e6, 1e6)],
            'outside': [(5000.0, 5000.0), (6000.0, 5000.0), (6000.0, 6000.0)],
            'rotated in view': [(200.0, 20.0), (380.0, 150.0), (200.0, 280.0), (20.0, 150.0)],
        }
        for name, polygon in cases.items():
            triangles = gpu_focus.dim_triangles(width, height, polygon)
            wrong = 0
            for x in range(5, width, 13):
                for y in range(5, height, 11):
                    if covered(triangles, (x, y)) == sg.point_in_polygon((x, y), polygon):
                        wrong += 1
            assert wrong == 0, (name, wrong)
        # Desaturate Other Images: off by default; on, only the drawing changes.
        assert KanvasPreferences.bl_rna.properties['focus_desaturate'].default is False
        from types import SimpleNamespace
        other = settings.images.add()
        other.item_type, other.item_id, other.name = 'IMAGE', 'other', 'Other'
        other.image_data = image.image_data
        other.saturation = 0.8
        image = next(item for item in settings.images if item.item_id == 'photo')
        real_get_prefs = gpu_focus.get_prefs
        gpu_focus.get_prefs = lambda: SimpleNamespace(focus_desaturate=False)
        assert gpu_focus.saturation_scale(settings) is None
        gpu_focus.get_prefs = lambda: SimpleNamespace(focus_desaturate=True,
                                                      focus_desaturate_amount=0.75)
        assert gpu_focus.saturation_scale(settings) == ('photo', 0.25)
        image.mask_editing = False
        assert gpu_focus.saturation_scale(settings) is None, 'only while editing'
        image.mask_editing = True
        gpu_focus.get_prefs = real_get_prefs
        other = next(item for item in settings.images if item.item_id == 'other')
        assert abs(other.saturation - 0.8) < 1e-6, 'the stored saturation is never touched'
        image.mask_editing = False
        image.markup_editing = True
        assert gpu_focus.focus_item(settings)[0] == 'IMAGE'
        image.markup_editing = False

        # E: into and out of Edit Vertices, on the one selected shape (an ellipse here).
        assert bpy.ops.kanvas.create_shape(kind='ELLIPSE', location=(200.0, 0.0),
                                           size=(80.0, 80.0)) == {'FINISHED'}
        ellipse = settings.images[-1]
        ellipse_id = ellipse.item_id
        assert toggle_vertex_edit(settings) is not None
        ellipse = next(item for item in settings.images if item.item_id == ellipse_id)
        assert ellipse.shape_edit_vertices and vertex_edit_shape(settings) is not None
        assert gpu_focus.focus_item(settings) == ('SHAPE', ellipse)
        hole = gpu_focus.focus_hole(settings, region)
        assert hole is not None
        assert toggle_vertex_edit(settings) is not None, 'E again leaves'
        ellipse = next(item for item in settings.images if item.item_id == ellipse_id)
        assert not ellipse.shape_edit_vertices and gpu_focus.focus_item(settings) is None
        # Not a single selected shape: E does nothing (the key passes through).
        image.is_selected = True
        assert toggle_vertex_edit(settings) is None
        ellipse.is_selected = False
        assert toggle_vertex_edit(settings) is None, 'an image has no vertices'

    print('EDITING FOCUS PASS')
finally:
    addon.unregister()
