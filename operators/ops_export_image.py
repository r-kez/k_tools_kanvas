"""Export the board, the selection, the view or one image as a PNG picture."""

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
               ('VIEW', 'View', 'What the editor shows now'),
               ('IMAGE', 'Image', 'The active image alone, upright and at its own '
                'resolution: adjustments, flip and mask kept, its place, rotation and '
                'scale on the board left out')),
        default='SELECTION')
    scale: bpy.props.FloatProperty(  # type: ignore
        name='Scale', description=('Pixels per canvas unit: 1 is the size items have on the '
                                   'canvas at 100% zoom, 2 is twice as sharp. For Image, '
                                   'pixels per image pixel: 1 is the size of the image'),
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
    only_selected: bpy.props.BoolProperty(  # type: ignore
        name='Only Selected',
        description=('Draw only the selected items (with what is inside a selected frame or '
                     'group) and the arrows between them. Off, everything inside the area '
                     'shows, like a crop of the board'),
        default=True)
    crop_to_mask: bpy.props.BoolProperty(  # type: ignore
        name='Crop to Mask',
        description=('A masked image counts only for what its mask shows, so the picture has '
                     'no transparent margin where the mask hides the image'),
        default=True)
    keep_stretch: bpy.props.BoolProperty(  # type: ignore
        name='Keep Stretch and Shear',
        description=('With Image: keep the stretch and shear the image has on the board, as '
                     'edits of the image (a fixed aspect ratio, a corrected slant). Off, the '
                     'picture has the proportions of the image file'),
        default=False)
    include_markup: bpy.props.BoolProperty(  # type: ignore
        name='Color Markup',
        description='Paint the color markup of the image over it, as on the canvas',
        default=False)
    include_drawings: bpy.props.BoolProperty(  # type: ignore
        name='Pencil Drawings',
        description='With Image: draw the pencil drawings stuck to the image over it, cut at '
                    'its edge',
        default=True)
    bit_depth: bpy.props.EnumProperty(  # type: ignore
        name='Color Depth',
        description='Bits per channel of the PNG',
        items=(('8', '8', '8 bits a channel: smaller files'),
               ('16', '16', '16 bits a channel: smooth gradients and adjustments, for '
                'painting or compositing further')),
        default='8')
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
            item = export_target(settings)
            if item is not None and _only_picture_selected(settings):
                self.scope = 'IMAGE'
                fallback = item.image_data.name if item.item_type == 'IMAGE' else 'Drawing'
                name = bpy.path.clean_name(item.name or fallback)
            folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ''
            self.filepath = os.path.join(folder, name + '.png')
        return ExportHelper.invoke(self, context, event)

    def _rect(self, context):
        from ..utils.board_render import board_rect
        if self.scope == 'VIEW':
            return _view_rect(context)
        return board_rect(get_settings(context), self.scope, self.only_selected,
                          self.crop_to_mask)

    def _size(self, context):
        """(width, height) of the picture, or None when there is nothing to export."""
        from ..utils.board_render import output_size
        if self.scope == 'IMAGE':
            from ..utils.item_picture import drawing_size, picture_size
            item = export_target(get_settings(context))
            if item is not None and item.item_type == 'SHAPE':
                size = drawing_size(item, self.scale)
            else:
                size = None if item is None else picture_size(
                    item, self.scale, self.crop_to_mask, self.keep_stretch)
            return None if size is None else (size[0] + 2 * self.margin,
                                              size[1] + 2 * self.margin)
        rect = self._rect(context)
        if rect is None or rect[2] <= rect[0] or rect[3] <= rect[1]:
            return None
        return output_size(rect, self._pixels_per_unit(context), self.margin)

    def draw(self, context):
        from ..utils.board_render import MAX_SIDE
        layout = self.layout
        layout.prop(self, 'scope')
        if self.scope == 'SELECTION':
            layout.prop(self, 'only_selected')
        if self.scope != 'VIEW':
            layout.prop(self, 'crop_to_mask')
        if self.scope == 'IMAGE':
            target = export_target(get_settings(context))
            if target is None or target.item_type == 'IMAGE':
                layout.prop(self, 'keep_stretch')
                layout.prop(self, 'include_markup')
                layout.prop(self, 'include_drawings')
        layout.prop(self, 'scale')
        layout.prop(self, 'margin')
        size = self._size(context)
        if size is None:
            text = ('Select an image or a pencil drawing' if self.scope == 'IMAGE'
                    and export_target(get_settings(context)) is None
                    else 'Nothing to export')
            layout.label(text=text, icon='ERROR')
        else:
            width, height = size
            icon = 'ERROR' if max(width, height) > MAX_SIDE else 'IMAGE_DATA'
            layout.label(text=f'{width} x {height} px', icon=icon)
        layout.prop(self, 'background')
        if self.background == 'COLOR':
            layout.prop(self, 'color', text='')
        layout.row().prop(self, 'bit_depth', expand=True)
        layout.prop(self, 'load_image')

    def _pixels_per_unit(self, context):
        # The view is exported as it looks on screen, then scaled.
        return self.scale * (_view_scale(context) if self.scope == 'VIEW' else 1.0)

    def execute(self, context):
        from ..utils.board_render import MAX_SIDE, output_size, render, write_png
        settings = get_settings(context)
        if self.scope == 'IMAGE':
            return self._export_image(settings)
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
        background = self._background()
        path = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), '.png')
        from ..utils.board_render import selection_contents
        only = (selection_contents(settings)
                if self.scope == 'SELECTION' and self.only_selected else None)
        try:
            # Annotations belong to no item: a picture of the selection leaves them out.
            picture = render(settings, rect, scale, self.margin, background,
                             space=None if only else context.space_data,
                             frame_number=context.scene.frame_current, only=only,
                             bit_depth=int(self.bit_depth))
            write_png(path, picture)
        except Exception as exc:
            self.report({'ERROR'}, f'Could not export the picture: {exc}')
            return {'CANCELLED'}
        if self.load_image:
            image = bpy.data.images.load(path, check_existing=False)
            image.pack()
        self.report({'INFO'}, f'Saved {width} x {height} px to {path}')
        return {'FINISHED'}

    def _background(self):
        return {'TRANSPARENT': (0.0, 0.0, 0.0, 0.0), 'CANVAS': _canvas_color(),
                'COLOR': tuple(self.color)}[self.background]

    def _export_image(self, settings):
        from ..utils.board_render import write_png
        from ..utils.item_picture import render_drawing, render_item
        item = export_target(settings)
        if item is None:
            self.report({'WARNING'}, 'Nothing to export: select an image or a pencil drawing')
            return {'CANCELLED'}
        path = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), '.png')
        try:
            if item.item_type == 'SHAPE':
                picture = render_drawing(settings, item, self.scale, int(self.bit_depth))
            else:
                from ..utils.pencil_anchor import drawings_of
                picture = render_item(settings, item, self.scale, self.crop_to_mask,
                                      self.include_markup, self.keep_stretch,
                                      int(self.bit_depth),
                                      drawings_of(settings, item) if self.include_drawings
                                      else ())
            picture = framed(picture, self.margin, self._background())
            write_png(path, picture)
        except Exception as exc:
            self.report({'ERROR'}, f'Could not export the picture: {exc}')
            return {'CANCELLED'}
        if self.load_image:
            image = bpy.data.images.load(path, check_existing=False)
            image.pack()
        height, width = picture.shape[:2]
        self.report({'INFO'}, f'Saved {width} x {height} px to {path}')
        return {'FINISHED'}


class KANVAS_OT_CopyImageToClipboard(KanvasTreeOnly, bpy.types.Operator):
    """Copy the selected image to the system clipboard as it looks on the canvas."""
    bl_idname = 'kanvas.copy_image_to_clipboard'
    bl_label = 'Copy to Clipboard'
    bl_description = ('Copy the selected image, with its adjustments, mask and color '
                      'markup, or the selected pencil drawing, to the clipboard, to paste '
                      'in other programs')
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        if not super().poll(context):
            return False
        return export_target(get_settings(context)) is not None

    def execute(self, context):
        from ..utils.clipboard_image import copy_picture
        from ..utils.item_picture import render_drawing, render_item
        settings = get_settings(context)
        item = export_target(settings)
        if item is None:
            self.report({'WARNING'}, 'Select an image or a pencil drawing to copy')
            return {'CANCELLED'}
        try:
            if item.item_type == 'SHAPE':
                picture = render_drawing(settings, item, 1.0, 8)
            else:
                from ..utils.pencil_anchor import drawings_of
                picture = render_item(settings, item, 1.0, True, True, False, 8,
                                      drawings_of(settings, item))
            copy_picture(picture)
        except Exception as exc:
            self.report({'ERROR'}, f'Could not copy the picture: {exc}')
            return {'CANCELLED'}
        height, width = picture.shape[:2]
        self.report({'INFO'}, f'Copied {width} x {height} px to the clipboard')
        return {'FINISHED'}


def export_image_item(settings):
    """The image Export Image > Image saves: the active item when it is a selected
    image, else the first selected image. None without one."""
    from ..utils.item_picture import is_picture_item
    index = settings.active_image_index
    if 0 <= index < len(settings.images):
        item = settings.images[index]
        if item.is_selected and is_picture_item(item):
            return item
    return next((item for item in settings.images
                 if item.is_selected and is_picture_item(item)), None)


def export_target(settings):
    """What Export Image > Image and Copy to Clipboard take: the image of
    `export_image_item`, else the selected Pencil Drawing (the active one when it is
    selected). None without either."""
    from ..utils.item_picture import is_drawing_item
    item = export_image_item(settings)
    if item is not None:
        return item
    index = settings.active_image_index
    if 0 <= index < len(settings.images):
        active = settings.images[index]
        if active.is_selected and is_drawing_item(active):
            return active
    return next((i for i in settings.images if i.is_selected and is_drawing_item(i)), None)


def _only_picture_selected(settings):
    from ..utils.item_picture import is_drawing_item
    selected = [item for item in settings.images if item.is_selected]
    return (len(selected) == 1
            and (selected[0].item_type == 'IMAGE' or is_drawing_item(selected[0]))
            and not any(arrow.is_selected for arrow in settings.arrows))


def framed(picture, margin, background):
    """`picture` (straight alpha, uint8 or uint16) with `margin` pixels around it, laid
    over `background` (RGBA 0..1) as the board export does."""
    import numpy as np
    height, width = picture.shape[:2]
    top = float(np.iinfo(picture.dtype).max)
    back = np.array([c * top for c in background], dtype=np.float32)
    result = np.empty((height + 2 * margin, width + 2 * margin, 4), dtype=picture.dtype)
    result[:] = np.clip(back + 0.5, 0, top).astype(picture.dtype)
    inner = result[margin:margin + height, margin:margin + width]
    if back[3] <= 0:
        inner[:] = picture
        return result
    alpha = picture[..., 3:4].astype(np.float32) / top
    color = picture[..., :3].astype(np.float32) * alpha + back[:3] * (1.0 - alpha)
    out_alpha = picture[..., 3:4].astype(np.float32) + back[3] * (1.0 - alpha)
    inner[..., :3] = np.clip(color + 0.5, 0, top).astype(picture.dtype)
    inner[..., 3:4] = np.clip(out_alpha + 0.5, 0, top).astype(picture.dtype)
    return result
