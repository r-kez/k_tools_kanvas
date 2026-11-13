"""Named color regions painted over Kanvas reference images."""

import bpy
import blf
import gpu
import time
import uuid

from .kanvas_context import KanvasTreeOnly
from .ops_mask import MaskPainterMixin, _active_image
from ..utils.gpu.gpu_theme import draw_rounded_fill, draw_rounded_border
from ..utils.gpu.gpu_markup import region_index_at_uv


from ..utils.color_palette import color_for_index, spread_colors
_active_color_dialogs = set()


def _add_region(item):
    count = len(item.markup_regions)
    region = item.markup_regions.add()
    region.region_id = uuid.uuid4().hex
    region.name = f'Region {count + 1}'
    region.color = color_for_index(
        count, [existing.color for existing in item.markup_regions if existing != region])
    item.markup_active_index = count
    item.markup_visible = True
    item.markup_revision += 1
    return region


def _cycle_region(item, direction):
    if not item.markup_regions:
        return False
    item.markup_active_index = ((item.markup_active_index + direction)
                                % len(item.markup_regions))
    return True


def _color_step(event):
    """Accept character keys on both US and dedicated <> keyboard layouts."""
    if event.ctrl or event.alt or event.value != 'PRESS':
        return 0
    character = getattr(event, 'unicode', '')
    if character in {'<', '>'}:
        return -1 if character == '<' else 1
    if event.type in {'COMMA', 'LEFT_BRACKET'}:
        return -1
    if event.type in {'PERIOD', 'RIGHT_BRACKET'}:
        return 1
    if event.type == 'GRLESS':
        return 1 if event.shift else -1
    return 0


def _palette_buttons(item, region, area=None):
    """Clickable color strip in local WINDOW coordinates."""
    count = len(item.markup_regions)
    bottom = max(4, region.height - 83)
    left_limit, right_limit = 0, region.width
    if area is not None:
        palette_y = region.y + bottom + 20
        for part in area.regions:
            if (part.type == 'WINDOW' or part.width <= 1 or part.height <= 1
                    or not part.y <= palette_y < part.y + part.height):
                continue
            if part.x <= region.x + 10:
                left_limit = max(left_limit, part.x + part.width - region.x)
            if part.x + part.width >= region.x + region.width - 10:
                right_limit = min(right_limit, part.x - region.x)
    available = max(80, right_limit - left_limit)
    slots = max(1, min(8, (available - 125) // 34))
    shown = min(count, slots)
    overflow = count > shown
    first = min(max(0, item.markup_active_index - shown // 2), count - shown)
    actions = []
    if overflow:
        actions.append(('PREVIOUS', -1))
    actions.extend(('SELECT', index) for index in range(first, first + shown))
    if overflow:
        actions.append(('NEXT', -1))
    actions.append(('ADD', -1))
    width = len(actions) * 34 + 12
    left = max(4, left_limit + (available - width) / 2)
    return [(action, index, (left + 6 + slot * 34, bottom + 6,
                             left + 34 + slot * 34, bottom + 34))
            for slot, (action, index) in enumerate(actions)]


def _palette_action_at(buttons, x, y):
    return next(((action, index) for action, index, bounds in buttons
                 if bounds[0] <= x < bounds[2]
                 and bounds[1] <= y < bounds[3]), None)


def _repeat_swatch_click(previous, index, x, y, now):
    return (previous is not None and previous[0] == index
            and now - previous[1] <= 0.45
            and (x - previous[2]) ** 2 + (y - previous[3]) ** 2 <= 100)


def _color_popup_region(context, item_id, region_id, tree_name=''):
    tree = getattr(getattr(context, 'space_data', None), 'edit_tree', None)
    if tree_name and (tree is None or tree.name != tree_name):
        tree = bpy.data.node_groups.get(tree_name)
    if tree is None or tree.bl_idname != 'KanvasNodeTree':
        return None
    item = next((part for part in tree.kanvas_settings.images
                 if part.item_id == item_id), None)
    if item is None:
        return None
    return next((part for part in item.markup_regions
                 if part.region_id == region_id), None)


def _redraw_kanvas_areas(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'NODE_EDITOR':
                area.tag_redraw()


class _MarkupEditProxy:
    """Expose the active color region to the shared mask painting tools."""

    _is_markup = True
    _property_map = {
        'mask_enabled': 'markup_visible',
        'mask_editing': 'markup_editing',
        'mask_tool': 'markup_tool',
        'mask_brush_size': 'markup_brush_size',
        'mask_erase': 'markup_erase',
        'mask_revision': 'markup_revision',
    }

    def __init__(self, item):
        object.__setattr__(self, '_item', item)

    def __getattr__(self, name):
        item = self._item
        if name == 'mask_dabs':
            return item.markup_regions[item.markup_active_index].dabs
        if name == 'mask_polygons':
            return item.markup_regions[item.markup_active_index].polygons
        if name == 'mask_next_sequence':
            return item.markup_regions[item.markup_active_index].next_sequence
        if name == '_markup_color':
            return tuple(item.markup_regions[item.markup_active_index].color)
        if name == '_markup_name':
            return item.markup_regions[item.markup_active_index].name
        return getattr(item, self._property_map.get(name, name))

    def __setattr__(self, name, value):
        if name == 'mask_next_sequence':
            self._item.markup_regions[self._item.markup_active_index].next_sequence = value
        elif name == 'mask_revision':
            delta = value - self._item.markup_revision
            self._item.markup_revision = value
            self._item.markup_regions[self._item.markup_active_index].revision += delta
        else:
            setattr(self._item, self._property_map.get(name, name), value)


class KANVAS_OT_AddMarkupRegion(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.add_markup_region'
    bl_label = 'Add Color Region'
    bl_description = 'Add a named color region to the active image'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and not item.mask_editing

    def execute(self, context):
        item = _active_image(context)
        _add_region(item)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_AddMarkupRegionInEdit(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.add_markup_region_in_edit'
    bl_label = 'Add Color Region'
    bl_description = 'Add a color while editing; included in this Color Mode session'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and item.markup_editing

    def execute(self, context):
        _add_region(_active_image(context))
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_RemoveMarkupRegion(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.remove_markup_region'
    bl_label = 'Remove Color Region'
    bl_description = 'Remove the selected color region and its paint'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and bool(item.markup_regions) and not item.markup_editing

    def execute(self, context):
        item = _active_image(context)
        index = min(item.markup_active_index, len(item.markup_regions) - 1)
        region = item.markup_regions[index]
        from ..utils.kanvas_data import get_settings
        settings = get_settings(context)
        card = next((card for card in settings.images
                     if region.checklist_card_id and card.item_id == region.checklist_card_id
                     and card.item_type == 'TEXT' and card.text_checklist), None)
        task = next((i for i, line in enumerate(card.text_lines)
                     if line.line_id == region.checklist_line_id), -1) if card else -1
        if task >= 0:
            # A task and its color go together: removing one removes the other.
            from .ops_checklist import remove_task
            remove_task(settings, card, task)
            context.area.tag_redraw()
            return {'FINISHED'}
        item.markup_regions.remove(index)
        item.markup_active_index = max(0, min(index, len(item.markup_regions) - 1))
        item.markup_revision += 1
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_MoveMarkupRegion(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.move_markup_region'
    bl_label = 'Reorder Color'
    bl_description = 'Move this color; linked task colors also reorder the checklist'
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.IntProperty(default=0)  # type: ignore

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and len(item.markup_regions) > 1 and not item.markup_editing

    def execute(self, context):
        from ..utils.kanvas_data import get_settings
        from .ops_checklist import is_associated, sync_card_images

        image = _active_image(context)
        if self.direction not in {-1, 1}:
            return {'CANCELLED'}
        index = image.markup_active_index
        if not 0 <= index < len(image.markup_regions):
            return {'CANCELLED'}
        region = image.markup_regions[index]
        settings = get_settings(context)
        if region.checklist_card_id and is_associated(image, region.checklist_card_id):
            card = next((item for item in settings.images
                         if item.item_id == region.checklist_card_id
                         and item.item_type == 'TEXT' and item.text_checklist), None)
            if card is not None:
                task_index = next((index for index, line in enumerate(card.text_lines)
                                   if line.line_id == region.checklist_line_id), -1)
                target = task_index + self.direction
                if not 0 <= task_index < len(card.text_lines) or not 0 <= target < len(card.text_lines):
                    return {'CANCELLED'}
                card.text_lines.move(task_index, target)
                sync_card_images(settings, card)
                context.area.tag_redraw()
                return {'FINISHED'}
        target = index + self.direction
        if not 0 <= target < len(image.markup_regions):
            return {'CANCELLED'}
        image.markup_regions.move(index, target)
        image.markup_active_index = target
        image.markup_revision += 1
        context.area.tag_redraw()
        return {'FINISHED'}


def _isolation_targets(context):
    """Selected images that have color regions (or the active image)."""
    settings = context.space_data.edit_tree.kanvas_settings
    selected = [item for item in settings.images
                if item.item_type == 'IMAGE' and item.is_selected
                and item.image_data and item.markup_regions]
    if selected:
        return selected
    item = _active_image(context)
    return [item] if item is not None and item.markup_regions else []


class KANVAS_OT_IsolateMarkupRegion(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.isolate_markup_region'
    bl_label = 'Isolate Color Region'
    bl_description = ('Show one color region at a time. Cycle with ] (next) and '
                      '[ (previous); \\ shows all again')
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.IntProperty(  # type: ignore
        default=1, description='1 next, -1 previous, 0 show all, 2 isolate the active region',
    )

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and bool(_isolation_targets(context))

    def execute(self, context):
        from ..utils.gpu.gpu_markup import isolated_index
        message = ''
        for item in _isolation_targets(context):
            count = len(item.markup_regions)
            current = isolated_index(item)
            if self.direction == 0:
                target = -1
            elif self.direction == 2:
                active = min(item.markup_active_index, count - 1)
                target = -1 if current == active else active
            elif self.direction > 0:
                # off -> first -> ... -> last -> off
                target = 0 if current < 0 else (current + 1 if current + 1 < count else -1)
            else:
                target = count - 1 if current < 0 else current - 1
            if target < 0:
                item.markup_isolate_id = ''
                message = 'Showing all colors'
            else:
                region = item.markup_regions[target]
                item.markup_visible = True
                item.markup_isolate_id = region.region_id
                item.markup_active_index = target
                message = f'Isolated {target + 1}/{count}: {region.name}'
            item.markup_revision += 1
        if message:
            self.report({'INFO'}, message)
        context.area.tag_redraw()
        return {'FINISHED'}


def extract_palette_regions(item, count):
    """Add one color region per dominant color of the image; returns the regions."""
    from ..utils.palette_extract import dominant_colors, hex_name
    from ..utils.sam_engine import prepare_image   # display-space pixels, reduced
    pixels, _size = prepare_image(item.image_data)
    regions = []
    for color, _share in dominant_colors(pixels / 255.0, count):
        region = _add_region(item)
        # Colors are drawn as stored (display space), so this matches the image.
        region.color = color
        region.name = hex_name(color)
        regions.append(region)
    return regions


class KANVAS_OT_ExtractPalette(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.extract_palette'
    bl_label = 'Extract Colors'
    bl_description = 'Add one color region for each dominant color of this image'
    bl_options = {'REGISTER', 'UNDO'}

    count: bpy.props.IntProperty(  # type: ignore
        name='Colors', description='How many dominant colors to extract',
        default=6, min=2, max=12,
    )

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and not item.mask_editing and not item.markup_editing

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            regions = extract_palette_regions(_active_image(context), self.count)
        except Exception as exc:
            self.report({'ERROR'}, f'Could not read the image colors: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Added {len(regions)} colors from the image')
        context.area.tag_redraw()
        return {'FINISHED'}


def image_under_point(settings, point):
    """Topmost visible image containing a canvas point, with the UV there."""
    from ..utils.arrow_geometry import image_uv_at
    candidates = sorted((item for item in settings.images
                         if item.item_type == 'IMAGE' and item.show_in_editor
                         and item.image_data),
                        key=lambda item: item.z_index, reverse=True)
    for item in candidates:
        uv = image_uv_at(item, point)
        if uv is not None:
            return item, uv
    return None, None


class KANVAS_OT_PickPixelColor(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.pick_pixel_color'
    bl_label = 'Pick Color'
    bl_description = ('Click a pixel of an image to add a color region with its exact color and '
                      'copy the hex code. Shift+click only copies the code. Reads the original '
                      'pixel, before brightness, contrast or tint. Esc cancels')
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        self._area = context.area
        self._window = context.window
        self._region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if self._region is None:
            return {'CANCELLED'}
        self._window.cursor_modal_set('EYEDROPPER')
        context.workspace.status_text_set('Click a pixel to pick its color  |  Shift+click: copy hex only  |  Esc: cancel')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, context):
        try:
            self._window.cursor_modal_restore()
            context.workspace.status_text_set(None)
        except (ReferenceError, RuntimeError):
            pass

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = self._region
            x, y = event.mouse_x - region.x, event.mouse_y - region.y
            if not (0 <= x < region.width and 0 <= y < region.height):
                return {'RUNNING_MODAL'}   # a click on the sidebar or header is ignored
            from ..utils.kanvas_data import get_settings
            from ..utils.palette_extract import hex_name, pixel_color_at
            settings = get_settings(context)
            item, uv = image_under_point(settings, region.view2d.region_to_view(x, y))
            if item is None:
                self.report({'WARNING'}, 'Click on an image')
                return {'RUNNING_MODAL'}
            try:
                color = pixel_color_at(item.image_data, uv)
            except Exception as exc:
                self._end(context)
                self.report({'ERROR'}, f'Could not read the pixel: {exc}')
                return {'CANCELLED'}
            code = hex_name(color)
            context.window_manager.clipboard = code
            self._end(context)
            if event.shift:
                self.report({'INFO'}, f'Copied {code}')
                return {'CANCELLED'}
            region_item = _add_region(item)
            region_item.color = color
            region_item.name = code
            self.report({'INFO'}, f'Added {code} to {item.name} (hex copied)')
            self._area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'LEFTMOUSE'}:
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL', 'PASS_THROUGH'}


class KANVAS_OT_ExportMarkupMasks(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.export_markup_masks'
    bl_label = 'Export Color Masks'
    bl_description = ('Save each painted color region of this image as a black and white mask, '
                      'plus an optional ID map, to use as textures or selections in Blender')
    bl_options = {'INTERNAL'}

    directory: bpy.props.StringProperty(subtype='DIR_PATH')  # type: ignore
    resolution: bpy.props.EnumProperty(  # type: ignore
        name='Resolution',
        description='Pixel size of the exported masks',
        items=[
            ('SOURCE', 'Image Size', 'The size of the image on the board (up to 4096 pixels)'),
            ('MASK', 'Mask Size', 'The reduced size the paint is stored at (up to 512 pixels), faster and smaller'),
        ],
        default='SOURCE',
    )
    id_map: bpy.props.BoolProperty(  # type: ignore
        name='ID Map',
        description='Also save one image showing every region in its own color',
        default=True,
    )

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return (item is not None and not item.markup_editing
                and any(region.dabs or region.polygons for region in item.markup_regions))

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        self.layout.prop(self, 'resolution')
        self.layout.prop(self, 'id_map')

    def execute(self, context):
        from ..utils.markup_export import export_markup_masks
        directory = bpy.path.abspath(self.directory)
        if not directory:
            self.report({'ERROR'}, 'Choose a folder')
            return {'CANCELLED'}
        try:
            paths = export_markup_masks(_active_image(context), directory,
                                        self.resolution, self.id_map)
        except (OSError, RuntimeError) as exc:
            self.report({'ERROR'}, f'Could not export the masks: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Saved {len(paths)} image(s) in {directory}')
        return {'FINISHED'}


class KANVAS_OT_RandomizeMarkupColors(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.randomize_markup_colors'
    bl_label = 'Randomize Colors'
    bl_description = ('Give every color region of this image a new random color, '
                      'spread apart so they stay easy to tell apart')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and bool(item.markup_regions) and not item.markup_editing

    def execute(self, context):
        from .ops_checklist import is_associated, sync_checklist_regions
        settings = context.space_data.edit_tree.kanvas_settings
        item = _active_image(context)
        cards = {card.item_id: card for card in settings.images
                 if card.item_type == 'TEXT' and card.text_checklist}
        touched_cards = set()
        for region, color in zip(item.markup_regions,
                                 spread_colors(len(item.markup_regions))):
            region.color = color
            # A linked region takes its color from the checklist task.
            card = cards.get(region.checklist_card_id)
            line = next((line for line in card.text_lines
                         if line.line_id == region.checklist_line_id), None) if card else None
            if line is not None:
                line.color = color
                touched_cards.add(card.item_id)
        for image in settings.images:
            if image.item_type != 'IMAGE' or image == item:
                continue
            if any(is_associated(image, card_id) for card_id in touched_cards):
                sync_checklist_regions(settings, image)
        item.markup_revision += 1
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_SelectMarkupRegion(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.select_markup_region'
    bl_label = 'Select Color Region'
    bl_description = 'Choose the color region to paint or edit'
    bl_options = {'REGISTER'}

    index: bpy.props.IntProperty()  # type: ignore

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return item is not None and bool(item.markup_regions)

    def execute(self, context):
        item = _active_image(context)
        if not 0 <= self.index < len(item.markup_regions):
            return {'CANCELLED'}
        item.markup_active_index = self.index
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_EditMarkupColorPopup(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.edit_markup_color_popup'
    bl_label = 'Edit Color'
    bl_description = 'Open the color control for this region'
    bl_options = {'INTERNAL'}

    item_id: bpy.props.StringProperty()  # type: ignore
    region_id: bpy.props.StringProperty()  # type: ignore
    tree_name: bpy.props.StringProperty()  # type: ignore
    color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Color', subtype='COLOR', size=3, min=0.0, max=1.0,
    )

    def invoke(self, context, event):
        region = _color_popup_region(context, self.item_id, self.region_id,
                                     self.tree_name)
        if region is None:
            return {'CANCELLED'}
        self.color = tuple(region.color)
        _active_color_dialogs.add(self.item_id)
        result = context.window_manager.invoke_props_dialog(
            self, width=280, title='Edit Color')
        if result != {'RUNNING_MODAL'}:
            _active_color_dialogs.discard(self.item_id)
        return result

    def draw(self, context):
        region = _color_popup_region(context, self.item_id, self.region_id,
                                     self.tree_name)
        if region is None:
            self.layout.label(text='Color unavailable')
            return
        self.layout.label(text=region.name)
        self.layout.prop(self, 'color', text='Color')

    def execute(self, context):
        _active_color_dialogs.discard(self.item_id)
        region = _color_popup_region(context, self.item_id, self.region_id,
                                     self.tree_name)
        if region is None:
            return {'CANCELLED'}
        if region.checklist_card_id and region.checklist_line_id:
            from ..utils.kanvas_data import get_settings
            settings = get_settings(context)
            card = next((item for item in settings.images
                         if item.item_id == region.checklist_card_id
                         and item.item_type == 'TEXT'), None)
            line = next((line for line in card.text_lines
                         if line.line_id == region.checklist_line_id), None) if card else None
            if line is not None:
                line.color = tuple(self.color)
            else:
                region.color = tuple(self.color)
        else:
            region.color = tuple(self.color)
        _redraw_kanvas_areas(context)
        return {'FINISHED'}

    def cancel(self, context):
        _active_color_dialogs.discard(self.item_id)


class KANVAS_OT_EditColorMarkup(MaskPainterMixin, KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.edit_color_markup'
    bl_label = 'Edit Color Markup'
    bl_description = 'Paint the selected color region with Brush, Polygon, or Rectangle'
    bl_options = {'REGISTER', 'UNDO'}
    _mode_label = 'Color Mode'

    @classmethod
    def poll(cls, context):
        item = _active_image(context) if KanvasTreeOnly.poll(context) else None
        return (item is not None and not item.mask_editing
                and not item.markup_editing)

    def invoke(self, context, event):
        item = _active_image(context)
        if item is None:
            return {'CANCELLED'}
        from .ops_checklist import sync_checklist_regions
        from ..utils.kanvas_data import get_settings
        sync_checklist_regions(get_settings(context), item)
        previous_revision = item.markup_revision
        created_region = False
        if not item.markup_regions:
            _add_region(item)
            created_region = True
        item.markup_active_index = min(item.markup_active_index,
                                       len(item.markup_regions) - 1)
        active_region = item.markup_regions[item.markup_active_index]
        visibility_changed = not active_region.visible
        if visibility_changed:
            active_region.visible = True
            item.markup_revision += 1
        self._last_region_index = item.markup_active_index
        self._palette_pressed = False
        self._palette_hover = None
        self._last_swatch_click = None
        self._palette_popup_pending_index = None
        self._sample_held = False
        self._sample_hover_index = None
        self._sample_mouse = None
        result = self._start_edit(context, event, _MarkupEditProxy(item))
        if created_region or visibility_changed:
            self._initial_mask_state = (previous_revision,
                                        *self._initial_mask_state[1:])
        return result

    def _item(self):
        item = super()._item()
        return _MarkupEditProxy(item) if item is not None else None

    def _raw_item(self):
        item = super()._item()
        return item

    def _palette_hit(self, item, event):
        region = self._window_region()
        if region is None or not self._in_canvas(event):
            return None
        x, y = event.mouse_x - region.x, event.mouse_y - region.y
        return _palette_action_at(_palette_buttons(item, region, self._area), x, y)

    def _draw_cursor(self):
        super()._draw_cursor()
        if bpy.context.area != self._area:
            return
        item = self._raw_item()
        region = self._window_region()
        if item is None or region is None:
            return
        buttons = _palette_buttons(item, region, self._area)
        if not buttons:
            return
        left = buttons[0][2][0] - 6
        right = buttons[-1][2][2] + 6
        bottom = buttons[0][2][1] - 6
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        previous_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')
        try:
            draw_rounded_fill(shader, (left, bottom, right, bottom + 40), 7,
                              (0.045, 0.06, 0.075, 0.9))
            for action, index, bounds in buttons:
                if action == 'SELECT':
                    color = tuple(item.markup_regions[index].color)
                    draw_rounded_fill(shader, bounds, 5, (*color, 1.0))
                    border = ((1.0, 1.0, 1.0, 1.0)
                              if index == item.markup_active_index
                              else (0.65, 0.7, 0.75, 0.8))
                    draw_rounded_border(shader, bounds, 5,
                                        2 if index == item.markup_active_index else 1,
                                        border)
                else:
                    draw_rounded_fill(shader, bounds, 5, (0.13, 0.17, 0.2, 1.0))
                    blf.size(0, 17)
                    blf.color(0, 0.92, 0.96, 1.0, 1.0)
                    blf.position(0, bounds[0] + 9, bounds[1] + 6, 0)
                    blf.draw(0, {'PREVIOUS': '<', 'NEXT': '>', 'ADD': '+'}[action])
            if self._palette_hover is not None:
                action, index = self._palette_hover
                label = (f'{item.markup_regions[index].name} · Double-click to edit'
                         if action == 'SELECT'
                         else {'PREVIOUS': 'Previous color', 'NEXT': 'Next color',
                               'ADD': 'Add color'}[action])
                blf.size(0, 11)
                label_width = blf.dimensions(0, label)[0] + 16
                label_left = (region.width - label_width) / 2
                label_bottom = bottom - 24
                draw_rounded_fill(shader, (label_left, label_bottom,
                                          label_left + label_width,
                                          label_bottom + 20), 4,
                                  (0.045, 0.06, 0.075, 0.9))
                blf.color(0, 0.95, 0.97, 1.0, 1.0)
                blf.position(0, label_left + 8, label_bottom + 4, 0)
                blf.draw(0, label)
        finally:
            gpu.state.blend_set(previous_blend)
        self._draw_sample_cursor(item, region)

    def _draw_sample_cursor(self, item, region):
        if not getattr(self, '_sample_held', False) or not self._sample_mouse:
            return
        mx = self._sample_mouse[0] - region.x
        my = self._sample_mouse[1] - region.y
        if not (0 <= mx < region.width and 0 <= my < region.height):
            return
        hover_idx = getattr(self, '_sample_hover_index', None)
        if hover_idx is not None and 0 <= hover_idx < len(item.markup_regions):
            region_item = item.markup_regions[hover_idx]
            color = tuple(region_item.color)
            name = region_item.name or f'Region {hover_idx + 1}'
            label = f'Pick: {name}'
            has_target = True
        else:
            color = (0.7, 0.7, 0.7)
            label = 'Pick Mask (S)'
            has_target = False

        font_size = 11
        blf.size(0, font_size)
        text_w = blf.dimensions(0, label)[0]

        box_w = text_w + 34
        box_h = 24
        box_x = mx + 16
        box_y = my - 12
        if box_x + box_w > region.width - 10:
            box_x = mx - box_w - 16
        if box_y < 10:
            box_y = my + 16
        if box_y + box_h > region.height - 10:
            box_y = region.height - box_h - 10

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        previous_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')
        try:
            bounds = (box_x, box_y, box_x + box_w, box_y + box_h)
            draw_rounded_fill(shader, bounds, 5, (0.045, 0.06, 0.075, 0.92))
            border_color = (*color[:3], 0.95) if has_target else (0.4, 0.5, 0.6, 0.7)
            draw_rounded_border(shader, bounds, 5, 2 if has_target else 1, border_color)

            swatch_cx = box_x + 13
            swatch_cy = box_y + box_h * 0.5
            swatch_r = 5
            swatch_bounds = (swatch_cx - swatch_r, swatch_cy - swatch_r,
                             swatch_cx + swatch_r, swatch_cy + swatch_r)
            draw_rounded_fill(shader, swatch_bounds, 3, (*color[:3], 1.0))

            blf.color(0, 0.96, 0.97, 0.98, 1.0)
            blf.position(0, box_x + 24, box_y + 6, 0)
            blf.draw(0, label)
        finally:
            gpu.state.blend_set(previous_blend)

    def _switch_region(self, item):
        self._commit_stroke(self._item())
        self._painting = False
        self._last_uv = None
        self._stroke_anchor_uv = None
        self._clear_line()
        self._polygon_cancel()
        self._rectangle_cancel()
        self._last_region_index = item.markup_active_index
        region = item.markup_regions[item.markup_active_index]
        if not region.visible:
            region.visible = True
            item.markup_revision += 1
        self._area.tag_redraw()

    def _open_region_color(self, item, index):
        self._commit_stroke(self._item())
        if item.markup_active_index != index:
            item.markup_active_index = index
            self._switch_region(item)
        self._last_swatch_click = None
        self._palette_popup_pending_index = None
        try:
            result = bpy.ops.kanvas.edit_markup_color_popup(
                'INVOKE_DEFAULT', item_id=self._item_id,
                region_id=item.markup_regions[index].region_id,
                tree_name=self._tree.name)
        except RuntimeError as exc:
            self.report({'WARNING'}, f'Could not open color dialog: {exc}')
            return
        if result == {'CANCELLED'}:
            self.report({'WARNING'}, 'Could not open color dialog')

    def modal(self, context, event):
        if getattr(self, '_item_id', None) in _active_color_dialogs:
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        item = self._raw_item()
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._sample_mouse = (event.mouse_x, event.mouse_y)
        if item is not None and event.type in {'S', 'I'} and not event.ctrl and not event.alt:
            if event.value == 'PRESS':
                if not getattr(self, '_sample_held', False):
                    self._sample_held = True
                    self._commit_stroke(self._item())
                    self._painting = False
                    self._last_uv = None
                    uv = self._mouse_uv(event, item)
                    self._sample_hover_index = region_index_at_uv(item, uv) if uv is not None else None
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE':
                if getattr(self, '_sample_held', False):
                    self._sample_held = False
                    self._sample_hover_index = None
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
        if item is not None and getattr(self, '_sample_held', False):
            if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
                uv = self._mouse_uv(event, item)
                hovered = region_index_at_uv(item, uv) if uv is not None else None
                if hovered != getattr(self, '_sample_hover_index', None):
                    self._sample_hover_index = hovered
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if event.type == 'LEFTMOUSE':
                if event.value == 'PRESS':
                    uv = self._mouse_uv(event, item)
                    if uv is not None:
                        sampled_index = region_index_at_uv(item, uv)
                        if sampled_index is not None:
                            if item.markup_active_index != sampled_index:
                                item.markup_active_index = sampled_index
                                self._switch_region(item)
                            self._sample_hover_index = sampled_index
                            target_region = item.markup_regions[sampled_index]
                            self.report({'INFO'}, f"Selected mask: {target_region.name}")
                            context.area.tag_redraw()
                return {'RUNNING_MODAL'}
        if item is not None and event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            hit = self._palette_hit(item, event)
            if hit != self._palette_hover:
                self._palette_hover = hit
                context.area.tag_redraw()
            if hit is not None:
                if self._painting:
                    self._commit_stroke(self._item())
                    self._painting = False
                    self._last_uv = None
                return {'RUNNING_MODAL'}
        if item is not None and event.type == 'LEFTMOUSE':
            if event.value == 'RELEASE' and self._palette_popup_pending_index is not None:
                index = self._palette_popup_pending_index
                self._palette_popup_pending_index = None
                self._palette_pressed = False
                if self._palette_hit(item, event) == ('SELECT', index):
                    self._open_region_color(item, index)
                return {'RUNNING_MODAL'}
            if event.value == 'RELEASE' and self._palette_pressed:
                self._palette_pressed = False
                return {'RUNNING_MODAL'}
            hit = self._palette_hit(item, event)
            if event.value == 'PRESS' and hit is not None:
                self._palette_pressed = True
                self._commit_stroke(self._item())
                action, index = hit
                if action == 'SELECT':
                    now = time.monotonic()
                    previous = self._last_swatch_click
                    self._last_swatch_click = (index, now, event.mouse_x, event.mouse_y)
                    if _repeat_swatch_click(previous, index,
                                            event.mouse_x, event.mouse_y, now):
                        self._palette_popup_pending_index = index
                        return {'RUNNING_MODAL'}
                if action == 'ADD':
                    _add_region(item)
                elif action == 'SELECT':
                    item.markup_active_index = index
                else:
                    _cycle_region(item, -1 if action == 'PREVIOUS' else 1)
                self._switch_region(item)
                return {'RUNNING_MODAL'}
            if event.value == 'DOUBLE_CLICK' and hit is not None and hit[0] == 'SELECT':
                self._palette_pressed = True
                self._palette_popup_pending_index = hit[1]
                return {'RUNNING_MODAL'}
        if item is not None and event.value == 'PRESS':
            if (event.type == 'E' and event.shift
                    and not event.ctrl and not event.alt and item.markup_regions):
                self._open_region_color(item, item.markup_active_index)
                return {'RUNNING_MODAL'}
            if event.type == 'C' and event.shift and not event.ctrl and not event.alt:
                self._commit_stroke(self._item())
                _add_region(item)
                self._switch_region(item)
                return {'RUNNING_MODAL'}
            direction = _color_step(event)
            if direction and item.markup_regions:
                self._commit_stroke(self._item())
                _cycle_region(item, direction)
                self._switch_region(item)
                return {'RUNNING_MODAL'}
        if item is not None and item.markup_active_index != self._last_region_index:
            self._switch_region(item)
        return super().modal(context, event)
