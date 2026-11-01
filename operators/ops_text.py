"""Create and edit Kanvas text cards from the sidebar."""

import bpy
from ..utils.kanvas_data import get_settings, unique_item_name
import uuid

from .kanvas_context import KanvasTreeOnly


def active_text(settings):
    index = settings.active_image_index
    if 0 <= index < len(settings.images):
        item = settings.images[index]
        if item.item_type == 'TEXT':
            return item
    return None


class KANVAS_OT_CreateText(KanvasTreeOnly, bpy.types.Operator):
    """Add a text card or checklist at the cursor or view center."""
    bl_idname = 'kanvas.create_text'
    bl_label = 'Add Text Card'
    bl_description = 'Add a text card, checklist or image comparison at the cursor or view center'
    bl_options = {'REGISTER', 'UNDO'}

    location: bpy.props.FloatVectorProperty(size=2, options={'SKIP_SAVE'})  # type: ignore
    checklist: bpy.props.BoolProperty(default=False)  # type: ignore
    compare: bpy.props.BoolProperty(default=False)  # type: ignore

    def invoke(self, context, event):
        region = context.region
        if region and region.type == 'WINDOW':
            x, y = event.mouse_region_x, event.mouse_region_y
        else:
            region = next((part for part in context.area.regions if part.type == 'WINDOW'), None)
            if region is None:
                return {'CANCELLED'}
            x, y = region.width * 0.5, region.height * 0.5
        self.location = region.view2d.region_to_view(x, y)
        return self.execute(context)

    def execute(self, context):
        settings = get_settings(context)
        for item in settings.images:
            item.is_selected = False
        card_name = unique_item_name(settings, 'Compare' if self.compare else 'Checklist' if self.checklist else 'Text Note')
        card = settings.images.add()
        card.item_id = uuid.uuid4().hex
        card.item_type = 'TEXT'
        card.name = card_name
        card.text_show_header = True
        card.location = self.location
        card.text_checklist = self.checklist and not self.compare
        if self.compare:
            card.text_compare = True
            card.text_width, card.text_height = 480.0, 320.0
        line = card.text_lines.add()
        line.line_id = uuid.uuid4().hex
        line.value = '' if self.compare else 'New task' if self.checklist else 'Write here...'
        if self.checklist and not self.compare:
            from .ops_checklist import _TASK_COLORS
            line.color = _TASK_COLORS[0]
        card.z_index = max((item.z_index for item in settings.images), default=0) + 1
        from ..utils.gpu import find_frame_at_location, sync_kanvas_frames, update_frame_bounds
        frame = find_frame_at_location(settings, card.location)
        if frame:
            card.parent_frame = frame.frame_node_name
            update_frame_bounds(context.space_data.edit_tree, settings, frame.frame_node_name)
        card.is_selected = True
        settings.active_image_index = len(settings.images) - 1
        if frame:
            sync_kanvas_frames(context.space_data.edit_tree, settings)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_EditTextPopup(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.edit_text_popup'
    bl_label = 'Edit Text Card'
    bl_description = 'Edit the text card directly from the canvas'
    bl_options = {'INTERNAL'}

    item_id: bpy.props.StringProperty(options={'SKIP_SAVE'})  # type: ignore

    def _card(self, context):
        settings = get_settings(context)
        return next((item for item in settings.images
                     if item.item_id == self.item_id and item.item_type == 'TEXT'), None)

    def invoke(self, context, event):
        if self._card(context) is None:
            return {'CANCELLED'}
        return context.window_manager.invoke_popup(self, width=360)

    def draw(self, context):
        card = self._card(context)
        if card is None:
            self.layout.label(text='Text card no longer exists', icon='ERROR')
            return
        layout = self.layout
        layout.prop(card, 'name', text='Title', icon='CHECKBOX_HLT' if card.text_checklist else 'TEXT')
        layout.prop(card, 'text_show_header', text='Show Title')
        if card.text_checklist:
            actions = layout.row(align=True)
            actions.operator('kanvas.add_text_line', icon='ADD', text='Add Task')
            actions.operator_menu_enum('kanvas.sort_checklist', 'mode', text='Sort', icon='SORTALPHA')
            for index, line in enumerate(card.text_lines):
                row = layout.row(align=True)
                row.prop(line, 'done', text='')
                row.prop(line, 'show_color_links', text='',
                         icon='HIDE_OFF' if line.show_color_links else 'HIDE_ON',
                         emboss=False)
                row.prop(line, 'color', text='')
                row.prop(line, 'value', text='')
                up = row.row(align=True)
                up.enabled = index > 0
                move = up.operator('kanvas.move_checklist_task', icon='TRIA_UP', text='')
                move.index, move.direction = index, -1
                down = row.row(align=True)
                down.enabled = index < len(card.text_lines) - 1
                move = down.operator('kanvas.move_checklist_task', icon='TRIA_DOWN', text='')
                move.index, move.direction = index, 1
                row.operator('kanvas.remove_text_line', icon='X', text='').index = index
        elif hasattr(layout, 'textbox'):
            layout.textbox(card, 'text_body', initial_visible_lines=6,
                           placeholder='Write here...')
        else:
            for index, line in enumerate(card.text_lines):
                row = layout.row(align=True)
                row.prop(line, 'value', text=str(index + 1))
                row.operator('kanvas.remove_text_line', icon='X', text='').index = index
            layout.operator('kanvas.add_text_line', icon='ADD', text='Add Line')

    def execute(self, context):
        return {'FINISHED'}


class KANVAS_OT_AddTextLine(KanvasTreeOnly, bpy.types.Operator):
    """Append a line to the active text card or checklist."""
    bl_idname = 'kanvas.add_text_line'
    bl_label = 'Add Text Line'
    bl_description = 'Add a line to the active text card or checklist'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and active_text(get_settings(context)) is not None

    def execute(self, context):
        settings = get_settings(context)
        card = active_text(settings)
        line = card.text_lines.add()
        line.line_id = uuid.uuid4().hex
        if card.text_checklist:
            from ..utils.color_palette import color_for_index
            line.color = color_for_index(
                len(card.text_lines) - 1,
                [other.color for other in card.text_lines if other != line])
            from .ops_checklist import sync_checklist_regions, is_associated
            for image in settings.images:
                if image.item_type == 'IMAGE' and is_associated(image, card.item_id):
                    sync_checklist_regions(settings, image)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_RemoveTextLine(KanvasTreeOnly, bpy.types.Operator):
    """Remove a line from the active card, keeping at least one editable line."""
    bl_idname = 'kanvas.remove_text_line'
    bl_label = 'Remove Text Line'
    bl_description = 'Remove this line from the text card or checklist'
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(default=-1)  # type: ignore

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and active_text(get_settings(context)) is not None

    def execute(self, context):
        settings = get_settings(context)
        lines = active_text(settings).text_lines
        if not 0 <= self.index < len(lines):
            return {'CANCELLED'}
        if len(lines) == 1:
            if not lines[0].value:
                return {'CANCELLED'}
            lines[0].value = ''
        else:
            from ..utils.arrow_geometry import endpoint, set_endpoint
            line_id = lines[self.index].line_id
            for arrow in settings.arrows:
                for side in ('start', 'end'):
                    if getattr(arrow, side + '_line_id') == line_id and line_id:
                        set_endpoint(arrow, side, endpoint(settings, arrow, side))
            for image in settings.images:
                if image.item_type != 'IMAGE':
                    continue
                for region in image.markup_regions:
                    if (region.checklist_card_id == active_text(settings).item_id
                            and region.checklist_line_id == line_id):
                        region.checklist_card_id = ''
                        region.checklist_line_id = ''
            lines.remove(self.index)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_MoveChecklistTask(KanvasTreeOnly, bpy.types.Operator):
    """Move a checklist task one position up or down."""
    bl_idname = 'kanvas.move_checklist_task'
    bl_label = 'Move Checklist Task'
    bl_description = 'Move this checklist task up or down'
    bl_options = {'INTERNAL', 'UNDO'}

    index: bpy.props.IntProperty(default=-1)  # type: ignore
    direction: bpy.props.IntProperty(default=0)  # type: ignore

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and active_text(get_settings(context)) is not None

    def execute(self, context):
        settings = get_settings(context)
        card = active_text(settings)
        lines = card.text_lines
        target = self.index + self.direction
        if not card.text_checklist or not (0 <= self.index < len(lines) and 0 <= target < len(lines)):
            return {'CANCELLED'}
        lines.move(self.index, target)
        from .ops_checklist import sync_card_images
        sync_card_images(settings, card)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_SortChecklist(KanvasTreeOnly, bpy.types.Operator):
    """Reorder checklist tasks by completion or name."""
    bl_idname = 'kanvas.sort_checklist'
    bl_label = 'Sort Checklist'
    bl_description = 'Sort checklist tasks by completion or alphabetical order'
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(  # type: ignore
        name='Order',
        items=[
            ('OPEN_FIRST', 'Open First', 'Move completed tasks to the end'),
            ('DONE_FIRST', 'Completed First', 'Move completed tasks to the beginning'),
            ('ALPHA_ASC', 'Alphabetical A-Z', 'Sort task text from A to Z'),
            ('ALPHA_DESC', 'Alphabetical Z-A', 'Sort task text from Z to A'),
        ],
    )

    @classmethod
    def poll(cls, context):
        return (KanvasTreeOnly.poll(context)
                and (card := active_text(get_settings(context))) is not None
                and card.text_checklist)

    def execute(self, context):
        settings = get_settings(context)
        card = active_text(settings)
        lines = card.text_lines
        desired = list(range(len(lines)))
        if self.mode == 'OPEN_FIRST':
            desired.sort(key=lambda index: lines[index].done)
        elif self.mode == 'DONE_FIRST':
            desired.sort(key=lambda index: not lines[index].done)
        elif self.mode == 'ALPHA_ASC':
            desired.sort(key=lambda index: lines[index].value.casefold())
        elif self.mode == 'ALPHA_DESC':
            desired.sort(key=lambda index: lines[index].value.casefold(), reverse=True)
        else:
            return {'CANCELLED'}
        if desired == list(range(len(lines))):
            return {'CANCELLED'}
        # Move collection members rather than rewriting text: line IDs keep
        # checklist arrow anchors attached to their original tasks.
        current_order = list(range(len(lines)))
        for target, original in enumerate(desired):
            current = current_order.index(original)
            lines.move(current, target)
            current_order.insert(target, current_order.pop(current))
        from .ops_checklist import sync_card_images
        sync_card_images(settings, card)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_PickCompareSide(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.pick_compare_side'
    bl_label = 'Pick Comparison Image'
    bl_description = ('Click an image on the board to show it as A or B in this comparison card. '
                      'Shift+click clears the side. Esc cancels')
    bl_options = {'REGISTER', 'UNDO'}

    item_id: bpy.props.StringProperty(options={'SKIP_SAVE'})  # type: ignore
    side: bpy.props.EnumProperty(  # type: ignore
        items=[('A', 'A', ''), ('B', 'B', '')], options={'SKIP_SAVE'},
    )

    def invoke(self, context, event):
        self._area = context.area
        self._window = context.window
        self._region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if self._region is None:
            return {'CANCELLED'}
        self._window.cursor_modal_set('EYEDROPPER')
        context.workspace.status_text_set(
            f'Click the image to show as {self.side}  |  Shift+click: clear  |  Esc: cancel')
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
                return {'RUNNING_MODAL'}
            settings = get_settings(context)
            card = next((item for item in settings.images
                         if item.item_id == self.item_id and item.text_compare), None)
            if card is None:
                self._end(context)
                return {'CANCELLED'}
            from .ops_markup import image_under_point
            image, _uv = image_under_point(settings, region.view2d.region_to_view(x, y))
            if image is None and not event.shift:
                self.report({'WARNING'}, 'Click on an image')
                return {'RUNNING_MODAL'}
            self._end(context)
            target = '' if event.shift else image.item_id
            if self.side == 'A':
                card.compare_a_id = target
            else:
                card.compare_b_id = target
            self.report({'INFO'}, f'{self.side}: {image.name if target else "cleared"}')
            self._area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'LEFTMOUSE'}:
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL', 'PASS_THROUGH'}


class KANVAS_OT_DragCompareDivider(KanvasTreeOnly, bpy.types.Operator):
    """Move the divider of a comparison card while the mouse button is held."""
    bl_idname = 'kanvas.drag_compare_divider'
    bl_label = 'Move Comparison Divider'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    item_id: bpy.props.StringProperty(options={'SKIP_SAVE'})  # type: ignore

    def _card(self, context):
        return next((item for item in get_settings(context).images
                     if item.item_id == self.item_id and item.text_compare), None)

    def _update(self, context, event):
        from ..utils.gpu.gpu_compare import split_from_position
        from ..utils.gpu.gpu_text import _region_bounds
        card = self._card(context)
        if card is None:
            return False
        x0, y0, x1, y1 = _region_bounds(card, self._region.view2d)
        bounds = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        card.compare_split = split_from_position(card, bounds, event.mouse_x - self._region.x)
        self._area.tag_redraw()
        return True

    def invoke(self, context, event):
        self._area = context.area
        self._window = context.window
        self._region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if self._region is None or self._card(context) is None:
            return {'CANCELLED'}
        self._window.cursor_modal_set('MOVE_X')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self):
        try:
            self._window.cursor_modal_restore()
        except (ReferenceError, RuntimeError):
            pass

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end()
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._end()
            return {'FINISHED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if not self._update(context, event):
                self._end()
                return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}
