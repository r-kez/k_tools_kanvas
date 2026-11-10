"""Perspective correction of an image: straighten it, turn or reset its corners, drag a corner.

The corners are dragged like the handles of a mark: the click starts `kanvas.edit_perspective_corner`
(from the canvas click code, while the Perspective tab shows the corners), which is modal only
for the length of the drag.
"""

import math

import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils import perspective as persp
from ..utils.kanvas_data import get_settings

DEFAULT_CORNERS = persp.DEFAULT_CORNERS


def _item(settings, item_id):
    return next((item for item in settings.images if item.item_id == item_id), None)


def _active_image(context):
    settings = get_settings(context)
    index = settings.active_image_index
    if 0 <= index < len(settings.images):
        item = settings.images[index]
        if item.item_type == 'IMAGE' and item.image_data and item.image_data.size[0] > 0:
            return item
    return None


class _ImageOperator(KanvasTreeOnly):
    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and _active_image(context) is not None


class KANVAS_OT_PerspectiveStraighten(_ImageOperator, bpy.types.Operator):
    bl_idname = 'kanvas.perspective_straighten'
    bl_label = 'Straighten'
    bl_description = ('Show the image straightened: the four corners become a rectangle. '
                      'Nothing of the image is lost; press again to see it as it is')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        item = _active_image(context)
        if not persp.set_straightened(item, not item.persp_enabled):
            self.report({'WARNING'}, 'The corners do not make a rectangle, or the image is cropped')
            return {'CANCELLED'}
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_PerspectiveWhole(_ImageOperator, bpy.types.Operator):
    bl_idname = 'kanvas.perspective_whole'
    bl_label = 'Show Whole Image'
    bl_description = ('Show all of the photo straightened, not only the rectangle. What lies '
                      'beyond the photo is clear, and the rectangle stays where it was')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        item = _active_image(context)
        persp.set_whole(item, not item.persp_whole)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_PerspectiveEstimate(_ImageOperator, bpy.types.Operator):
    bl_idname = 'kanvas.perspective_estimate'
    bl_label = 'Estimate Proportions'
    bl_description = ('Work out the proportions of the rectangle from the corners as they are now. '
                      'Moving a corner afterwards leaves them as they are')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        item = _active_image(context)
        if persp.estimated_ratio(item) is None:
            self.report({'WARNING'}, 'The corners do not make a rectangle')
            return {'CANCELLED'}
        persp.fix_proportions(item)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_PerspectiveReset(_ImageOperator, bpy.types.Operator):
    bl_idname = 'kanvas.perspective_reset'
    bl_label = 'Reset Corners'
    bl_description = 'Put the corners back inside the image and show the image as it is'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        item = _active_image(context)
        persp.set_straightened(item, False)
        item.persp_corners = DEFAULT_CORNERS
        item.persp_auto = True
        item.persp_whole = False
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_PerspectiveRotate(_ImageOperator, bpy.types.Operator):
    bl_idname = 'kanvas.perspective_rotate'
    bl_label = 'Turn Corners'
    bl_description = ('Pass each corner to the next one: the image comes out turned a quarter. '
                      'The first corner is the bottom left of the straightened image')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        item = _active_image(context)
        c = tuple(item.persp_corners)
        item.persp_corners = c[2:] + c[:2]
        if not item.persp_auto:
            item.persp_aspect = max(0.05, min(20.0, 1.0 / max(1e-6, item.persp_aspect)))
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_EditPerspectiveCorner(KanvasTreeOnly, bpy.types.Operator):
    """Drag a corner of the rectangle to straighten. Started by a click on the corner while
    the Perspective tab shows them."""
    bl_idname = 'kanvas.edit_perspective_corner'
    bl_label = 'Move Corner'
    bl_options = {'REGISTER', 'UNDO'}

    item_id: bpy.props.StringProperty(options={'SKIP_SAVE'})  # type: ignore
    corner: bpy.props.IntProperty(min=0, max=3, options={'SKIP_SAVE'})  # type: ignore

    def invoke(self, context, event):
        item = _item(get_settings(context), self.item_id)
        if item is None or not item.image_data:
            return {'CANCELLED'}
        self.start = tuple(item.persp_corners)
        context.workspace.status_text_set('Move corner: drag  |  Esc: cancel')
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _end(self, context, result):
        context.workspace.status_text_set(None)
        context.area.tag_redraw()
        return result

    def modal(self, context, event):
        item = _item(get_settings(context), self.item_id)
        if item is None:
            return self._end(context, {'CANCELLED'})
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            item.persp_corners = self.start
            return self._end(context, {'CANCELLED'})
        if event.type == 'MOUSEMOVE':
            from .ops_arrow import _canvas_point
            from ..utils import measure as mm
            point = _canvas_point(context, event)
            uv = None if point is None else mm.canvas_to_uv(item, point)
            if uv is not None:
                uv = (min(1.0, max(0.0, uv[0])), min(1.0, max(0.0, uv[1])))
                corners = list(item.persp_corners)
                corners[self.corner * 2:self.corner * 2 + 2] = uv
                width, height = item.image_data.size
                quad = [(corners[i], corners[i + 1]) for i in range(0, 8, 2)]
                if persp.is_valid_quad(quad, width, height):      # never into a bow tie
                    item.persp_corners = corners
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return self._end(context, {'FINISHED'})
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        item = _item(get_settings(context), self.item_id)
        if item is not None:
            item.persp_corners = self.start
        context.workspace.status_text_set(None)
