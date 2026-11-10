"""Send Kanvas images to the 3D View as reference image empties, and manage them from
the 3D View: update a reference after editing its image, select it, find its image on
the board, remove it."""

import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils.kanvas_data import get_settings
from ..utils import reference_3d as ref


def _select_reference(self, context):
    """Clicking a row of the reference list selects its empty."""
    references = self.kanvas_references
    if not 0 <= self.kanvas_reference_index < len(references):
        return
    obj = references[self.kanvas_reference_index].object
    view_layer = getattr(context, 'view_layer', None)
    if obj is None or view_layer is None or obj.name not in view_layer.objects:
        return
    for other in view_layer.objects:
        if other.select_get() and other != obj:
            other.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj


def _kanvas_tree_poll(self, tree):
    return tree.bl_idname == 'KanvasNodeTree'


class KanvasReference(bpy.types.PropertyGroup):
    """A Kanvas image shown in the 3D View, and how its picture was made."""
    kind: bpy.props.EnumProperty(  # type: ignore
        items=(('EMPTY', 'Reference Image', 'An image empty in the scene'),),
        default='EMPTY')
    object: bpy.props.PointerProperty(type=bpy.types.Object)  # type: ignore
    board: bpy.props.PointerProperty(type=bpy.types.NodeTree, poll=_kanvas_tree_poll)  # type: ignore
    item_id: bpy.props.StringProperty()  # type: ignore
    view: bpy.props.EnumProperty(items=ref.VIEW_ITEMS, default='FRONT')  # type: ignore
    crop_to_mask: bpy.props.BoolProperty(  # type: ignore
        name='Crop to Mask',
        description='Only the part of the image its mask shows, without the hidden margin',
        default=True)
    keep_stretch: bpy.props.BoolProperty(  # type: ignore
        name='Keep Stretch and Shear',
        description='Keep the stretch and shear the image has on the board',
        default=False)
    include_markup: bpy.props.BoolProperty(  # type: ignore
        name='Color Markup', description='Paint the color markup of the image over it',
        default=False)


class KanvasReferenceTarget(bpy.types.PropertyGroup):
    """One selected image in the Send to 3D View dialog."""
    item_id: bpy.props.StringProperty()  # type: ignore
    label: bpy.props.StringProperty()  # type: ignore
    use: bpy.props.BoolProperty(name='Send', default=True)  # type: ignore
    view: bpy.props.EnumProperty(  # type: ignore
        name='View', description='Which view the reference faces', items=ref.VIEW_ITEMS,
        default='FRONT')


def _selected_images(settings):
    from ..utils.item_picture import is_picture_item
    images = [item for item in settings.images if item.is_selected and is_picture_item(item)]
    active = settings.active_image_index
    if 0 <= active < len(settings.images):
        first = settings.images[active]
        if first in images:   # the active image first: it gets the Front view
            images.remove(first)
            images.insert(0, first)
    return images


class KANVAS_OT_AddReference3D(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.add_3d_reference'
    bl_label = 'Send to 3D View'
    bl_description = ('Add the selected images to the 3D View as reference images, as they '
                      'look on the board and cropped to their mask, at the 3D cursor')
    bl_options = {'REGISTER', 'UNDO'}

    targets: bpy.props.CollectionProperty(type=KanvasReferenceTarget)  # type: ignore
    size: bpy.props.FloatProperty(  # type: ignore
        name='Size', description='Length of the longer side of the image in the scene',
        default=5.0, min=0.0001, soft_max=100.0, subtype='DISTANCE', unit='LENGTH')
    depth: bpy.props.EnumProperty(  # type: ignore
        name='Type', description='How the reference is drawn with the objects of the scene',
        items=ref.DEPTH_ITEMS, default='DEFAULT')
    opacity: bpy.props.FloatProperty(  # type: ignore
        name='Opacity', description='Opacity of the reference in the 3D View',
        default=1.0, min=0.0, max=1.0, subtype='FACTOR')
    axis_aligned: bpy.props.BoolProperty(  # type: ignore
        name='Only Axis Aligned',
        description=('Show a Front, Side, Top or Bottom reference only when looking along '
                     'its axis, as a blueprint'),
        default=True)
    perspective: bpy.props.BoolProperty(  # type: ignore
        name='Show in Perspective',
        description='Also show the reference in perspective views, not only orthographic ones',
        default=True)
    crop_to_mask: bpy.props.BoolProperty(  # type: ignore
        name='Crop to Mask',
        description='Only the part of each image its mask shows, without the hidden margin',
        default=True)
    keep_stretch: bpy.props.BoolProperty(  # type: ignore
        name='Keep Stretch and Shear',
        description='Keep the stretch and shear the images have on the board',
        default=False)
    include_markup: bpy.props.BoolProperty(  # type: ignore
        name='Color Markup', description='Paint the color markup of each image over it',
        default=False)

    @classmethod
    def poll(cls, context):
        return KanvasTreeOnly.poll(context) and bool(_selected_images(get_settings(context)))

    def invoke(self, context, event):
        self.targets.clear()
        for index, item in enumerate(_selected_images(get_settings(context))):
            target = self.targets.add()
            target.item_id, target.label = item.item_id, item.name or item.image_data.name
            target.view = ref.BLUEPRINT_ORDER[index % len(ref.BLUEPRINT_ORDER)]
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)
        for target in self.targets:
            row = column.row(align=True)
            if len(self.targets) > 1:
                row.prop(target, 'use', text='')
            row.label(text=target.label, icon='IMAGE_DATA')
            row.prop(target, 'view', text='')
        layout.separator()
        column = layout.column()
        column.use_property_split = True
        column.prop(self, 'size')
        column.prop(self, 'depth')
        column.prop(self, 'opacity', slider=True)
        column.prop(self, 'axis_aligned')
        column.prop(self, 'perspective')
        column.separator()
        column.prop(self, 'crop_to_mask')
        column.prop(self, 'keep_stretch')
        column.prop(self, 'include_markup')

    def execute(self, context):
        tree = context.space_data.edit_tree
        settings = get_settings(context)
        scene = context.scene
        ref.prune(scene)
        targets = [(t.item_id, t.view) for t in self.targets if t.use or len(self.targets) == 1]
        if not targets:   # run again from Redo or a script: the selection
            targets = [(item.item_id, ref.BLUEPRINT_ORDER[i % len(ref.BLUEPRINT_ORDER)])
                       for i, item in enumerate(_selected_images(settings))]
        made, failed = [], []
        location = scene.cursor.location.copy()
        for item_id, view in targets:
            options = dict(crop_to_mask=self.crop_to_mask, keep_stretch=self.keep_stretch,
                           include_markup=self.include_markup)
            probe = _Options(item_id=item_id, **options)
            try:
                item, picture = ref.make_picture(tree, probe)
                image = ref.store_picture(picture, item)
            except Exception as exc:
                item = ref.board_item(tree, item_id)
                failed.append(f'{item.name if item else item_id}: {exc}')
                continue
            obj = ref.create_empty(context, image, item.name or image.name, view, location,
                                   self.size, self.depth, self.opacity, self.axis_aligned,
                                   self.perspective)
            entry = scene.kanvas_references.add()
            entry.kind, entry.object, entry.board = 'EMPTY', obj, tree
            entry.item_id, entry.view = item_id, view
            entry.crop_to_mask = self.crop_to_mask
            entry.keep_stretch = self.keep_stretch
            entry.include_markup = self.include_markup
            made.append(obj.name)
        if made:
            scene.kanvas_reference_index = len(scene.kanvas_references) - 1
        for message in failed:
            self.report({'WARNING'}, message)
        if not made:
            return {'CANCELLED'}
        self.report({'INFO'}, f'Added {len(made)} reference image{"s" if len(made) > 1 else ""} '
                              f'to the 3D View')
        return {'FINISHED'}


class _Options:
    """The options `make_picture` reads, for a reference not listed yet."""

    def __init__(self, **values):
        self.__dict__.update(values)


def _entry_index(context, index):
    """The row an operator acts on: `index`, or the active row for -1. None when that
    row is gone or its empty was deleted."""
    references = context.scene.kanvas_references
    if index < 0:
        index = context.scene.kanvas_reference_index
    if 0 <= index < len(references) and not ref.is_deleted(references[index]):
        return index
    return None


def _entry(context, index):
    index = _entry_index(context, index)
    return None if index is None else context.scene.kanvas_references[index]


class _ReferenceOperator:
    index: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE'})  # type: ignore

    @classmethod
    def poll(cls, context):
        return getattr(context, 'scene', None) is not None and _entry(context, -1) is not None


class KANVAS_OT_UpdateReference3D(_ReferenceOperator, bpy.types.Operator):
    bl_idname = 'kanvas.update_3d_reference'
    bl_label = 'Update Reference'
    bl_description = ('Make the picture of the reference again from its image on the Kanvas '
                      'board, after editing its mask or adjustments')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        entry = _entry(context, -1) if getattr(context, 'scene', None) else None
        return entry is not None and ref.board_item(entry.board, entry.item_id) is not None

    def execute(self, context):
        entry = _entry(context, self.index)
        if entry is None:
            return {'CANCELLED'}
        obj = entry.object
        try:
            item, picture = ref.make_picture(entry.board, entry)
            obj.data = ref.store_picture(picture, item, obj.data if obj.data else None)
        except Exception as exc:
            self.report({'WARNING'}, f'Could not update {obj.name}: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Updated {obj.name}')
        return {'FINISHED'}


class KANVAS_OT_UpdateAllReferences3D(bpy.types.Operator):
    bl_idname = 'kanvas.update_all_3d_references'
    bl_label = 'Update All References'
    bl_description = 'Make every reference picture of this scene again from its Kanvas image'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        scene = getattr(context, 'scene', None)
        return scene is not None and any(not ref.is_deleted(e) for e in scene.kanvas_references)

    def execute(self, context):
        ref.prune(context.scene)
        updated, failed = 0, 0
        for entry in context.scene.kanvas_references:
            if entry.kind != 'EMPTY':
                continue
            try:
                item, picture = ref.make_picture(entry.board, entry)
                entry.object.data = ref.store_picture(picture, item, entry.object.data)
                updated += 1
            except Exception as exc:
                self.report({'WARNING'}, f'{entry.object.name}: {exc}')
                failed += 1
        self.report({'INFO'}, f'Updated {updated} reference{"s" if updated != 1 else ""}'
                              + (f', {failed} could not be updated' if failed else ''))
        return {'FINISHED'} if updated else {'CANCELLED'}


class KANVAS_OT_RemoveReference3D(_ReferenceOperator, bpy.types.Operator):
    bl_idname = 'kanvas.remove_3d_reference'
    bl_label = 'Remove Reference'
    bl_description = ('Delete the reference image from the scene. The image stays on the '
                      'Kanvas board')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        index = _entry_index(context, self.index)
        if index is None:
            return {'CANCELLED'}
        obj = context.scene.kanvas_references[index].object
        image = obj.data
        context.scene.kanvas_references.remove(index)
        bpy.data.objects.remove(obj)
        if image is not None and image.get('kanvas_reference') and image.users == 0:
            bpy.data.images.remove(image)
        ref.prune(context.scene)
        return {'FINISHED'}


class KANVAS_OT_ShowReferenceInKanvas(_ReferenceOperator, bpy.types.Operator):
    bl_idname = 'kanvas.show_reference_in_kanvas'
    bl_label = 'Show in Kanvas'
    bl_description = 'Select the image of this reference on its board and frame it in a Kanvas editor'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        entry = _entry(context, -1) if getattr(context, 'scene', None) else None
        return entry is not None and ref.board_item(entry.board, entry.item_id) is not None

    def execute(self, context):
        entry = _entry(context, self.index)
        if entry is None or ref.board_item(entry.board, entry.item_id) is None:
            return {'CANCELLED'}
        found = _kanvas_editor(context)
        if found is None:
            self.report({'WARNING'}, 'Open a Kanvas editor to show the image')
            return {'CANCELLED'}
        window, area = found
        space = area.spaces.active
        space.node_tree = entry.board
        settings = entry.board.kanvas_settings
        from ..properties import suspend_selection_updates
        with suspend_selection_updates():
            for index, item in enumerate(settings.images):
                item.is_selected = item.item_id == entry.item_id
                if item.is_selected:
                    settings.active_image_index = index
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with context.temp_override(window=window, area=area, region=region, space_data=space):
            bpy.ops.kanvas.focus_selection()
        area.tag_redraw()
        return {'FINISHED'}


def _kanvas_editor(context):
    """(window, area) of a node editor showing Kanvas, the largest first."""
    found = []
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'NODE_EDITOR' and area.ui_type == 'KanvasNodeTree':
                found.append((area.width * area.height, window, area))
    if not found:
        return None
    _, window, area = max(found, key=lambda f: f[0])
    return window, area


def register():
    bpy.types.Scene.kanvas_references = bpy.props.CollectionProperty(type=KanvasReference)
    bpy.types.Scene.kanvas_reference_index = bpy.props.IntProperty(
        default=-1, update=_select_reference)


def unregister():
    del bpy.types.Scene.kanvas_reference_index
    del bpy.types.Scene.kanvas_references
