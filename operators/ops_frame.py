"""Operators for Kanvas-owned frames."""
import uuid
import bpy
from ..utils.kanvas_data import get_settings, unique_item_name
from ..utils.gpu import (attach_items_to_frame, can_attach_to_frame, frame_ancestors, get_frame,
                         sync_kanvas_frames, update_frame_bounds)
from ..properties import suspend_frame_geometry_updates


def kanvas_tree(context):
    space = getattr(context, 'space_data', None)
    tree = getattr(space, 'edit_tree', None) if space else None
    return tree if tree and tree.bl_idname == 'KanvasNodeTree' else None


def _selection_roots(settings, targets):
    """A selected subtree is attached through its outermost selected frame."""
    selected_frames = {item.frame_node_name for item in targets if item.item_type == 'FRAME'}
    roots = []
    for item in targets:
        parent = get_frame(settings, item.parent_frame) if item.parent_frame else None
        if parent and (parent.frame_node_name in selected_frames or any(
                ancestor.frame_node_name in selected_frames
                for ancestor in frame_ancestors(settings, parent))):
            continue
        roots.append(item)
    return roots


class KANVAS_OT_DetachFromFrame(bpy.types.Operator):
    """Release selected items from their frames without moving them (Alt+U)."""
    bl_idname = "kanvas.detach_from_frame"
    bl_label = "Release from Frame"
    bl_description = 'Release selected items from their frames without moving them (Alt+U)'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return kanvas_tree(context) is not None

    def execute(self, context):
        settings = get_settings(context)
        tree = kanvas_tree(context)
        targets = [item for item in settings.images
                   if item.item_type in {'IMAGE', 'TEXT', 'SHAPE', 'FRAME'} and item.is_selected
                   and not item.is_locked and item.parent_frame]
        if not targets and 0 <= settings.active_image_index < len(settings.images):
            item = settings.images[settings.active_image_index]
            if (item.item_type in {'IMAGE', 'TEXT', 'SHAPE', 'FRAME'} and item.parent_frame
                    and not item.is_locked):
                targets = [item]
        if not targets:
            return {'CANCELLED'}
        old_frames = {item.parent_frame for item in targets if item.parent_frame}
        with suspend_frame_geometry_updates():
            for item in targets:
                item.released_parent_frame = item.parent_frame
                item.parent_frame = ''
        for frame_name in old_frames:
            update_frame_bounds(tree, settings, frame_name)
        sync_kanvas_frames(tree, settings)
        context.area.tag_redraw()
        return {'FINISHED'}


def _frame_choices(self, context):
    if context is None or not get_settings(context):
        return []
    return [(item.frame_node_name, item.name, "")
            for item in get_settings(context).images
            if item.item_type == 'FRAME' and not item.frame_is_group
            and item.show_in_editor and not item.is_locked]


class KANVAS_OT_AttachToFrame(bpy.types.Operator):
    """Attach selected images, cards and frames to an existing frame."""
    bl_idname = "kanvas.attach_to_frame"
    bl_label = "Attach Selection to Frame"
    bl_description = 'Attach selected items to a frame while keeping their canvas positions'
    bl_options = {'REGISTER', 'UNDO'}

    frame_name: bpy.props.StringProperty(name="Frame ID", default="")  # type: ignore
    target: bpy.props.EnumProperty(name="Frame", items=_frame_choices)  # type: ignore

    @classmethod
    def poll(cls, context):
        if kanvas_tree(context) is None:
            return False
        items = get_settings(context).images
        return any(item.is_selected and not item.is_locked
                   and item.item_type in {'IMAGE', 'TEXT', 'SHAPE', 'FRAME'}
                   and any(frame.item_type == 'FRAME' and not frame.frame_is_group
                           and frame.show_in_editor and not frame.is_locked
                           and frame.frame_node_name != item.frame_node_name for frame in items)
                   for item in items)

    def invoke(self, context, event):
        if self.frame_name:
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "target")

    def execute(self, context):
        settings = get_settings(context)
        frame_name = self.frame_name or self.target
        targets = [item for item in settings.images
                   if item.is_selected and not item.is_locked
                   and item.item_type in {'IMAGE', 'TEXT', 'SHAPE', 'FRAME'}
                   and not (item.item_type == 'FRAME' and item.frame_node_name == frame_name)]
        target_frame = get_frame(settings, frame_name)
        if (not targets or not target_frame or target_frame.is_locked
                or target_frame.frame_is_group):
            # Groups take members through Ctrl+G, which keeps groups from nesting.
            return {'CANCELLED'}
        targets = _selection_roots(settings, targets)
        invalid = [item for item in targets if not can_attach_to_frame(settings, item, frame_name)]
        if invalid:
            self.report({'WARNING'}, "A frame cannot contain itself or an ancestor")
            return {'CANCELLED'}
        changed = attach_items_to_frame(kanvas_tree(context), settings, targets, frame_name)
        if not changed:
            return {'CANCELLED'}
        sync_kanvas_frames(kanvas_tree(context), settings)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_FitFrame(bpy.types.Operator):
    """Resize a frame to include its current contents."""
    bl_idname = "kanvas.fit_frame"
    bl_label = "Fit Frame to Content"
    bl_description = 'Resize the frame around its visible contents'
    bl_options = {'REGISTER', 'UNDO'}

    frame_name: bpy.props.StringProperty(name="Frame ID", default="")  # type: ignore

    @classmethod
    def poll(cls, context):
        return kanvas_tree(context) is not None

    def execute(self, context):
        settings = get_settings(context)
        frame_name = self.frame_name
        if not frame_name and 0 <= settings.active_image_index < len(settings.images):
            active = settings.images[settings.active_image_index]
            frame_name = active.frame_node_name if active.item_type == 'FRAME' else active.parent_frame
        frame = get_frame(settings, frame_name)
        if frame is None:
            return {'CANCELLED'}
        before = (frame.auto_resize, frame.frame_width, frame.frame_height,
                  tuple(frame.location))
        frame.auto_resize = True
        update_frame_bounds(kanvas_tree(context), settings, frame_name)
        sync_kanvas_frames(kanvas_tree(context), settings)
        if (frame.auto_resize, frame.frame_width, frame.frame_height,
                tuple(frame.location)) == before:
            return {'CANCELLED'}
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_CreateFrame(bpy.types.Operator):
    """Create a Kanvas frame around selected items, or an empty one."""
    bl_idname = "kanvas.create_frame"
    bl_label = "Create Kanvas Frame"
    bl_description = 'Create a frame around the selected items or at the cursor'
    bl_options = {'REGISTER', 'UNDO'}

    label: bpy.props.StringProperty(name="Label", default="Kanvas Frame")  # type: ignore
    cursor: bpy.props.FloatVectorProperty(size=2, options={'SKIP_SAVE'})  # type: ignore

    @classmethod
    def poll(cls, context):
        return kanvas_tree(context) is not None

    def execute(self, context):
        settings = get_settings(context)
        tree = kanvas_tree(context)
        targets = [item for item in settings.images
                   if item.is_selected and (item.item_type in {'TEXT', 'SHAPE', 'FRAME'}
                                            or (item.item_type == 'IMAGE' and item.image_data))]
        targets = _selection_roots(settings, targets)
        from ..utils.item_geometry import front_z
        layer = max((item.z_index for item in targets), default=front_z(settings) - 1)
        frame_label = unique_item_name(settings, self.label)
        frame = settings.images.add()
        frame.z_index = layer if targets else front_z(settings)
        frame.item_id = uuid.uuid4().hex
        frame.item_type = 'FRAME'
        frame.frame_node_name = 'kanvas_' + uuid.uuid4().hex
        frame_id = frame.frame_node_name
        frame.name = frame_label
        frame.location = self.cursor
        frame.auto_resize = True
        attach_items_to_frame(tree, settings, targets, frame_id)
        for item in settings.images:
            item.is_selected = (item.item_type == 'FRAME' and item.frame_node_name == frame_id)
        sync_kanvas_frames(tree, settings)
        for index, item in enumerate(settings.images):
            if item.frame_node_name == frame_id and item.item_type == 'FRAME':
                settings.active_image_index = index
                break
        context.area.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        region = getattr(context, 'region', None)
        if region is not None and region.type == 'WINDOW':
            x = max(0, min(region.width, event.mouse_region_x))
            y = max(0, min(region.height, event.mouse_region_y))
            self.cursor = region.view2d.region_to_view(x, y)
        return self.execute(context)
