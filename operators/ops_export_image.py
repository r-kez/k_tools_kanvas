"""Export the board, the selection or the view as a PNG picture."""

import os

import bpy
from bpy_extras.io_utils import ExportHelper

from .kanvas_context import KanvasTreeOnly
from ..utils.kanvas_data import get_settings


def _window_region(context):
    area = getattr(context, 'area', None)
    if area is None:
        return None
    if context.region is not None and context.region.type == 'WINDOW':
        return context.region
    return next((region for region in area.regions if region.type == 'WINDOW'), None)


def _view_rect(context):
    region = _window_region(context)
    if region is None:
        return None
    view = region.view2d
    x0, y0 = view.region_to_view(0, 0)
    x1, y1 = view.region_to_view(region.width, region.height)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _view_scale(context):
    """Pixels per canvas unit at the current zoom."""
    region = _window_region(context)
    if region is None:
        return 1.0
    view = region.view2d
    span = abs(view.region_to_view(1000, 0)[0] - view.region_to_view(0, 0)[0])
    return 1000.0 / span if span > 1e-9 else 1.0


def _canvas_color():
    from ..utils.gpu.gpu_common import get_prefs
    prefs = get_prefs()
    if prefs is not None and getattr(prefs, 'canvas_background_enabled', False):
        return (*prefs.canvas_background_color[:3], 1.0)
    try:
        back = bpy.context.preferences.themes[0].node_editor.space.back
        return (*back[:3], 1.0)
    except (AttributeError, IndexError):
        return (0.16, 0.16, 0.16, 1.0)


class KANVAS_OT_ExportBoardImage(KanvasTreeOnly, bpy.types.Operator, ExportHelper):
    """Save a picture of the board as PNG: the selection, the whole board or the view,
    drawn as on the canvas without the selection and handles."""
    bl_idname = 'kanvas.export_board_image'
    bl_label = 'Export Image'
    bl_description = ('Save a PNG picture of the selection, the whole board or the view, as '
                      'drawn on the canvas, without selection outlines or handles')
    bl_options = {'REGISTER'}

    filename_ext = '.png'
    filter_glob: bpy.props.StringProperty(default='*.png', options={'HIDDEN'})  # type: ignore
    scope: bpy.props.EnumProperty(  # type: ignore
        name='Area', description='Which part of the board goes into the picture',
        items=(('SELECTION', 'Selection', 'Around the selected items and arrows'),
               ('ALL', 'Whole Board', 'Around every visible item and arrow'),
               ('VIEW', 'View', 'What the editor shows now')),
        default='SELECTION')
    scale: bpy.props.FloatProperty(  # type: ignore
        name='Scale', description=('Pixels per canvas unit: 1 is the size items have on the '
                                   'canvas at 100% zoom, 2 is twice as sharp'),
        default=1.0, min=0.05, max=32.0, soft_max=8.0)
    margin: bpy.props.IntProperty(  # type: ignore
        name='Margin', description='Empty space around the picture, in pixels',
        default=16, min=0, max=2048)
    background: bpy.props.EnumProperty(  # type: ignore
        name='Background', description='What lies behind the items',
        items=(('TRANSPARENT', 'Transparent', 'Nothing: the picture keeps transparency'),
               ('CANVAS', 'Canvas', 'The color of the canvas'),
               ('COLOR', 'Color', 'A color of your choice')),
        default='TRANSPARENT')
    color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Color', description='Background color', subtype='COLOR', size=4,
        default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0)
    load_image: bpy.props.BoolProperty(  # type: ignore
        name='Load into Blender',
        description=('Also add the picture to this file as a packed Blender image, for use '
                     'as a texture'),
        default=False)

    def invoke(self, context, event):
        settings = get_settings(context)
        has_selection = (any(item.is_selected for item in settings.images)
                         or any(arrow.is_selected for arrow in settings.arrows))
        self.scope = 'SELECTION' if has_selection else 'ALL'
        if not self.filepath:
            tree = getattr(context.space_data, 'edit_tree', None)
            name = bpy.path.clean_name(tree.name if tree else 'Kanvas')
            folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ''
            self.filepath = os.path.join(folder, name + '.png')
        return ExportHelper.invoke(self, context, event)

    def _rect(self, context):
        from ..utils.board_render import board_rect
        if self.scope == 'VIEW':
            return _view_rect(context)
        return board_rect(get_settings(context), self.scope)

    def draw(self, context):
        from ..utils.board_render import MAX_SIDE, output_size
        layout = self.layout
        layout.prop(self, 'scope')
        layout.prop(self, 'scale')
        layout.prop(self, 'margin')
        rect = self._rect(context)
        if rect is None:
            layout.label(text='Nothing to export', icon='ERROR')
        else:
            width, height = output_size(rect, self._pixels_per_unit(context), self.margin)
            icon = 'ERROR' if max(width, height) > MAX_SIDE else 'IMAGE_DATA'
            layout.label(text=f'{width} x {height} px', icon=icon)
        layout.prop(self, 'background')
        if self.background == 'COLOR':
            layout.prop(self, 'color', text='')
        layout.prop(self, 'load_image')

    def _pixels_per_unit(self, context):
        # The view is exported as it looks on screen, then scaled.
        return self.scale * (_view_scale(context) if self.scope == 'VIEW' else 1.0)

    def execute(self, context):
        from ..utils.board_render import MAX_SIDE, output_size, render, write_png
        settings = get_settings(context)
        rect = self._rect(context)
        if rect is None or rect[2] <= rect[0] or rect[3] <= rect[1]:
            self.report({'WARNING'}, 'Nothing to export: select items, or choose Whole Board')
            return {'CANCELLED'}
        scale = self._pixels_per_unit(context)
        width, height = output_size(rect, scale, self.margin)
        if max(width, height) > MAX_SIDE:
            self.report({'ERROR'}, f'{width} x {height} px is too large (at most {MAX_SIDE} px '
                                   'on a side): lower the Scale')
            return {'CANCELLED'}
        background = {'TRANSPARENT': (0.0, 0.0, 0.0, 0.0), 'CANVAS': _canvas_color(),
                      'COLOR': tuple(self.color)}[self.background]
        path = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), '.png')
        try:
            picture = render(settings, rect, scale, self.margin, background,
                             space=context.space_data, frame_number=context.scene.frame_current)
            write_png(path, picture)
        except Exception as exc:
            self.report({'ERROR'}, f'Could not export the picture: {exc}')
            return {'CANCELLED'}
        if self.load_image:
            image = bpy.data.images.load(path, check_existing=False)
            image.pack()
        self.report({'INFO'}, f'Saved {width} x {height} px to {path}')
        return {'FINISHED'}
