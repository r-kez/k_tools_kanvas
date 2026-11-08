"""Edit the gradient fill of the active shape (its colors are a Blender color ramp)."""

import math

import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils.kanvas_data import get_settings


def active_gradient_shape(context):
    """The active shape, when it has a gradient fill."""
    settings = get_settings(context)
    index = settings.active_image_index if settings else -1
    if not settings or not (0 <= index < len(settings.images)):
        return None
    item = settings.images[index]
    if item.item_type != 'SHAPE' or item.shape_fill_type == 'SOLID' or item.is_locked:
        return None
    return item


class _GradientOperator(KanvasTreeOnly):
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return super().poll(context) and active_gradient_shape(context) is not None


def _redraw(context):
    if context.area:
        context.area.tag_redraw()


class KANVAS_OT_GradientEditColors(_GradientOperator, bpy.types.Operator):
    bl_idname = 'kanvas.gradient_edit_colors'
    bl_label = 'Edit Gradient Colors'
    bl_description = ('Give this gradient its own color ramp to edit (shapes saved by an '
                      'older version keep their colors)')

    @classmethod
    def poll(cls, context):
        item = active_gradient_shape(context)
        return super().poll(context) and item is not None and item.shape_gradient_texture is None

    def execute(self, context):
        from ..utils.shape_gradient import ensure_ramp
        ensure_ramp(active_gradient_shape(context))
        _redraw(context)
        return {'FINISHED'}


class KANVAS_OT_GradientRotate(_GradientOperator, bpy.types.Operator):
    bl_idname = 'kanvas.gradient_rotate'
    bl_label = 'Turn Gradient'
    bl_description = ('Turn the gradient around its middle (a radial one around its center), '
                      'inside the shape box')

    angle: bpy.props.FloatProperty(  # type: ignore
        name='Angle', default=math.radians(90.0), subtype='ANGLE')

    def execute(self, context):
        item = active_gradient_shape(context)
        start, end = tuple(item.shape_gradient_start), tuple(item.shape_gradient_end)
        if item.shape_fill_type == 'RADIAL':
            pivot = start
        else:
            pivot = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5)
        c, s = math.cos(self.angle), math.sin(self.angle)

        def turn(point):
            x, y = point[0] - pivot[0], point[1] - pivot[1]
            return pivot[0] + x * c - y * s, pivot[1] + x * s + y * c

        item.shape_gradient_start, item.shape_gradient_end = turn(start), turn(end)
        _redraw(context)
        return {'FINISHED'}


class KANVAS_OT_GradientResetPoints(_GradientOperator, bpy.types.Operator):
    bl_idname = 'kanvas.gradient_reset_points'
    bl_label = 'Reset Gradient Points'
    bl_description = ('Put the gradient back across the whole shape: left to right, or a '
                      'circle from the middle')

    def execute(self, context):
        from ..utils.shape_gradient import DEFAULT_POINTS
        item = active_gradient_shape(context)
        item.shape_gradient_start, item.shape_gradient_end = DEFAULT_POINTS[item.shape_fill_type]
        _redraw(context)
        return {'FINISHED'}
