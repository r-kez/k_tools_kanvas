"""Gradient fills: the ramp maths, seeding the color ramp, drawing data, the operators,
copies (duplicate, Copy/Paste Style, a copied tree), older saved stops, refitting the
box, and the shader (built when a GPU is there)."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import shape_gradient as sg


def close(a, b, tol=1e-4):
    return all(abs(x - y) < tol for x, y in zip(a, b))


# --- Pure maths ----------------------------------------------------------------------
stops = [(1, 0, 0, 1, 0.0), (0, 0, 1, 0, 1.0)]
assert close(sg.sample(stops, 0.5), (0.5, 0, 0.5, 0.5))
assert close(sg.sample(stops, -1), (1, 0, 0, 1)) and close(sg.sample(stops, 2), (0, 0, 1, 0))
three = [(0, 0, 0, 1, 0.0), (1, 1, 1, 1, 0.25), (0, 0, 0, 1, 1.0)]
assert close(sg.sample(three, 0.25), (1, 1, 1, 1)) and close(sg.sample(three, 0.625), (0.5, 0.5, 0.5, 1))
assert len(sg.ramp(stops)) == sg.RAMP_SIZE * 4
assert close(sg.average_color([1, 0, 0, 1, 0, 0, 1, 0]), (0.5, 0, 0.5, 0.5))
assert abs(sg.gradient_t('LINEAR', (0, 0), (10, 0), (5, 99)) - 0.5) < 1e-9
assert abs(sg.gradient_t('RADIAL', (0, 0), (10, 0), (0, 5)) - 0.5) < 1e-9
assert sg.spread_t(1.25, 'PAD') == 1.0 and abs(sg.spread_t(1.25, 'REPEAT') - 0.25) < 1e-9
assert abs(sg.spread_t(1.25, 'REFLECT') - 0.75) < 1e-9
assert abs(sg.spread_t(-0.25, 'REFLECT') - 0.25) < 1e-9

addon.register()
try:
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('Gradient', 'KanvasNodeTree')
    area.spaces.active.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings

    def by_id(item_id):
        return next(item for item in settings.images if item.item_id == item_id)

    with bpy.context.temp_override(area=area, region=region, space_data=area.spaces.active):
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(100.0, 50.0),
                                           size=(200.0, 100.0)) == {'FINISHED'}
        shape_id = settings.images[-1].item_id
        shape = by_id(shape_id)
        settings.active_image_index = len(settings.images) - 1
        shape.is_selected = True
        assert shape.shape_fill_type == 'SOLID' and shape.shape_gradient_texture is None
        assert not bpy.ops.kanvas.gradient_rotate.poll(), 'a solid fill has no gradient'

        # --- Seeding: a hidden texture holds the color ramp -----------------------------
        shape.shape_fill_color = (0.2, 0.4, 0.6)
        shape.shape_fill_type = 'LINEAR'
        texture = shape.shape_gradient_texture
        assert texture is not None and texture.name.startswith('.'), 'hidden from lists'
        assert texture.users == 1
        records = sg.stop_records(shape)
        assert len(records) == 2 and close(records[0][:4], (0.2, 0.4, 0.6, 1.0))
        assert records[1][3] == 0.0, 'the fill color fades to clear'
        start, end = sg.canvas_points(shape)
        assert close(start, (0.0, 50.0)) and close(end, (200.0, 50.0)), (start, end)
        shape.shape_fill_type = 'RADIAL'
        assert close(tuple(shape.shape_gradient_start), (0, 0)), 'radial starts in the middle'
        assert close(tuple(shape.shape_gradient_end), (0.5, 0))
        assert shape.shape_gradient_texture == texture, 'the same ramp is kept'
        shape.shape_fill_type = 'LINEAR'

        # --- Drawing data follows the ramp, interpolation included ----------------------
        from k_tools_kanvas.utils.gpu import gpu_shape
        parts = gpu_shape.shape_draw_geometry(shape, 1.0)
        triangles, fringe, fringe_colors, color, gradient = parts['fill']
        assert gradient is not None and gradient[0] == 'LINEAR'
        assert len(gradient[5]) == sg.RAMP_SIZE * 4
        assert all(c[:3] == (1.0, 1.0, 1.0) for c in fringe_colors), 'fringe is coverage only'
        ramp = texture.color_ramp
        middle = gradient[5][128 * 4 + 3]
        ramp.interpolation = 'CONSTANT'
        stepped = gpu_shape.shape_draw_geometry(shape, 1.0)['fill'][4]
        assert stepped[4] != gradient[4], 'a new interpolation redraws'
        assert abs(stepped[5][128 * 4 + 3] - 1.0) < 1e-6 and abs(middle - 0.5) < 0.02, \
            'Constant holds the first color'
        ramp.interpolation = 'LINEAR'
        element = ramp.elements.new(0.5)
        element.color = (1.0, 0.0, 0.0, 1.0)
        assert len(sg.stop_records(shape)) == 3
        shape.rotation = 90.0
        turned = gpu_shape.shape_draw_geometry(shape, 1.0)['fill'][4]
        assert close(turned[2], (100.0, -50.0)), 'the gradient turns with the shape'
        shape.rotation = 0.0

        # --- Operators -------------------------------------------------------------------
        assert not bpy.ops.kanvas.gradient_edit_colors.poll(), 'the ramp already exists'
        assert bpy.ops.kanvas.gradient_rotate(angle=math.radians(90)) == {'FINISHED'}
        assert close(tuple(shape.shape_gradient_start), (0, -0.5))
        assert close(tuple(shape.shape_gradient_end), (0, 0.5))
        assert bpy.ops.kanvas.gradient_reset_points() == {'FINISHED'}
        assert close(tuple(shape.shape_gradient_start), (-0.5, 0))

        # --- Copies get a ramp of their own ----------------------------------------------
        record = sg.gradient_record(shape)
        assert bpy.ops.kanvas.duplicate_image() == {'FINISHED'}
        copy = settings.images[settings.active_image_index]
        assert copy.item_id != shape_id and sg.gradient_record(copy) == record, \
            'a duplicate keeps the gradient'
        assert copy.shape_gradient_texture != by_id(shape_id).shape_gradient_texture
        copy.shape_gradient_texture.color_ramp.elements[0].color = (0, 1, 0, 1)
        assert sg.gradient_record(by_id(shape_id)) == record, 'editing the copy leaves the original'

        assert bpy.ops.kanvas.create_shape(kind='TRIANGLE', location=(600.0, 0.0),
                                           size=(80.0, 80.0)) == {'FINISHED'}
        plain_id = settings.images[-1].item_id
        from k_tools_kanvas.operators.ops_style import apply_style, copy_style
        assert copy_style(by_id(shape_id)) and apply_style(by_id(plain_id))
        assert sg.gradient_record(by_id(plain_id)) == record, 'Paste Style brings the gradient'
        assert by_id(plain_id).shape_gradient_texture != by_id(shape_id).shape_gradient_texture
        by_id(plain_id).shape_fill_type = 'SOLID'
        assert copy_style(by_id(plain_id)) and apply_style(by_id(shape_id))
        assert by_id(shape_id).shape_fill_type == 'SOLID', 'and a solid style clears it'
        by_id(shape_id).shape_fill_type = 'LINEAR'

        # --- A shared ramp (a tree copied by Blender) is split -------------------------
        other = bpy.data.node_groups.new('Copy', 'KanvasNodeTree').kanvas_settings.images.add()
        other.item_type, other.item_id = 'SHAPE', 'shared'
        other.shape_gradient_texture = by_id(shape_id).shape_gradient_texture
        assert sg.unshare_ramps() == 1
        assert other.shape_gradient_texture != by_id(shape_id).shape_gradient_texture
        assert sg.unshare_ramps() == 0

        # --- Stops saved before the color ramp ------------------------------------------
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(0.0, 400.0),
                                           size=(100.0, 100.0)) == {'FINISHED'}
        old_id = settings.images[-1].item_id
        old = by_id(old_id)
        for color, position in (((1, 1, 0), 0.0), ((0, 1, 1), 1.0)):
            stop = old.shape_gradient_stops.add()
            stop.color, stop.alpha, stop.position = color, 1.0, position
        # As an older file loads: the type is already set and there is no ramp yet.
        old.shape_fill_type = 'RADIAL'
        old.shape_gradient_texture = None
        assert close(sg.stop_records(old)[1][:4], (0, 1, 1, 1)), 'old stops still draw'
        assert gpu_shape.shape_draw_geometry(old, 1.0)['fill'][4] is not None
        settings.active_image_index = next(i for i, item in enumerate(settings.images)
                                           if item.item_id == old_id)
        assert bpy.ops.kanvas.gradient_edit_colors() == {'FINISHED'}
        old = by_id(old_id)
        assert old.shape_gradient_texture is not None
        assert close(sg.stop_records(old)[1][:4], (0, 1, 1, 1)), 'the ramp takes the old stops'

        # --- Refitting the box keeps the gradient in place on the canvas -----------------
        base = by_id(plain_id)
        base.shape_fill_type = 'LINEAR'
        before = sg.canvas_points(base)
        assert bpy.ops.kanvas.create_shape(kind='RECTANGLE', location=(900.0, 0.0),
                                           size=(50.0, 50.0)) == {'FINISHED'}
        other_id = settings.images[-1].item_id
        from k_tools_kanvas.operators.ops_shape import combine_shapes
        combined = combine_shapes(bpy.context, settings, [by_id(plain_id), by_id(other_id)])
        after = sg.canvas_points(combined)
        assert all(close(a, b, 1e-3) for a, b in zip(before, after)), (before, after)
        assert combined.shape_fill_type == 'LINEAR', 'the base keeps its gradient'

        # --- SVG export samples a ramp SVG cannot describe -------------------------------
        combined.shape_gradient_texture.color_ramp.interpolation = 'EASE'
        assert len(sg.export_stops(combined)) == sg.EXPORT_SAMPLES
        combined.shape_gradient_texture.color_ramp.interpolation = 'LINEAR'
        assert sg.export_stops(combined) == sg.stop_records(combined), "plain ramps keep their stops"

        # --- Shader ----------------------------------------------------------------------
        from k_tools_kanvas.utils.gpu import gpu_gradient
        shader = gpu_gradient.get_gradient_shader()
        if shader is not None:
            values = sg.ramp(stops)
            texture = gpu_gradient.ramp_texture(('key',), values)
            assert texture is gpu_gradient.ramp_texture(('key',), values), 'ramps are shared'
            print('gradient shader built')
        else:
            print('no GPU: gradient shader not built (flat fallback)')
    print('test_shape_gradient: OK')
finally:
    addon.unregister()
