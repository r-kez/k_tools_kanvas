import bpy
from ..utils.kanvas_data import get_settings

from .kanvas_context import KanvasTreeOnly


class KANVAS_MT_AlignMenu(bpy.types.Menu):
    bl_idname = "KANVAS_MT_align_menu"
    bl_label = "Align Kanvas Selection"
    bl_description = 'Align or distribute selected Kanvas items'

    def draw(self, context):
        from .ops_align import ALIGN_ICONS, ALIGN_MODES
        from ..utils.icons import get_icon

        layout = self.layout
        for mode, label, _ in ALIGN_MODES:
            layout.operator("kanvas.align_items", text=label,
                            icon_value=get_icon(ALIGN_ICONS[mode])).mode = mode
        layout.separator()
        layout.operator('kanvas.distribute_items',
                        text='Distribute Horizontally').axis = 'HORIZONTAL'
        layout.operator('kanvas.distribute_items',
                        text='Distribute Vertically').axis = 'VERTICAL'


def draw_kanvas_align_header(self, context):
    if not KanvasTreeOnly.poll(context):
        return
    row = self.layout.row(align=True)
    row.enabled = bpy.ops.kanvas.align_items.poll()
    row.menu("KANVAS_MT_align_menu", text="▾", icon='ALIGN_LEFT')


def draw_kanvas_add_entries(layout):
    layout.operator_context = 'INVOKE_DEFAULT'
    layout.operator("kanvas.add_image_browser", icon='IMAGE_DATA', text="Image")
    layout.operator("kanvas.add_multiple_images", icon='FILE_NEW', text="Multiple Images")
    layout.operator("kanvas.import_pureref", icon='IMPORT', text="PureRef Scene (.pur)")
    layout.operator("kanvas.create_text", icon='TEXT', text="Text Card").checklist = False
    layout.operator("kanvas.create_text", icon='CHECKBOX_HLT', text="Checklist").checklist = True
    layout.operator("kanvas.create_text", icon='UV_SYNC_SELECT', text="Compare A/B").compare = True
    layout.menu("KANVAS_MT_add_shape", text="Shape", icon='MESH_PLANE')
    layout.operator("kanvas.create_arrow", icon='TRIA_RIGHT', text="Arrow")
    layout.operator("kanvas.create_frame", icon='FULLSCREEN_ENTER', text="Frame")


def draw_kanvas_add_menu(self, context):
    """Add Kanvas content to the Node Editor's Add menu for Kanvas trees."""
    if not KanvasTreeOnly.poll(context):
        return
    self.layout.separator()
    draw_kanvas_add_entries(self.layout)


class KANVAS_MT_AddShapeMenu(bpy.types.Menu):
    bl_idname = "KANVAS_MT_add_shape"
    bl_label = "Shape"
    bl_description = 'Draw a rectangle, triangle, diamond, ellipse or other shape on the canvas'

    def draw(self, context):
        from .ops_shape import draw_shape_menu_entries
        draw_shape_menu_entries(self.layout)


class KANVAS_MT_AddContentMenu(bpy.types.Menu):
    bl_idname = "KANVAS_MT_add_content"
    bl_label = "Add"
    bl_description = 'Add images, text cards, arrows, frames, or a PureRef scene'

    def draw(self, context):
        draw_kanvas_add_entries(self.layout)


def register():
    bpy.types.NODE_MT_add.append(draw_kanvas_add_menu)
    bpy.types.NODE_HT_header.append(draw_kanvas_align_header)


def unregister():
    bpy.types.NODE_HT_header.remove(draw_kanvas_align_header)
    bpy.types.NODE_MT_add.remove(draw_kanvas_add_menu)


class KANVAS_MT_ContextMenu(bpy.types.Menu):
    """Kanvas context menu (right click)."""
    bl_idname = "KANVAS_MT_context_menu"
    bl_label  = "Kanvas"
    bl_description = 'Actions for the current Kanvas selection'

    def draw(self, context):
        from ..utils.gpu import owning_group
        layout   = self.layout
        settings = get_settings(context)

        selected = [img for img in settings.images if img.is_selected]
        active   = settings.images[settings.active_image_index] \
                   if (settings.images and 0 <= settings.active_image_index < len(settings.images)) \
                   else None
        n_sel    = len(selected)

        if n_sel > 0:
            content = [item for item in selected if item.item_type in {'IMAGE', 'TEXT', 'SHAPE'}]
            attached = [item for item in selected if item.parent_frame]
            frame_name = (active.frame_node_name if active and active.item_type == 'FRAME'
                          else active.parent_frame if active else '')

            layout.label(text=f"{n_sel} selected", icon='RESTRICT_SELECT_OFF')
            layout.separator()
            layout.label(text="Frame", icon='FULLSCREEN_ENTER')
            if content or any(item.item_type == 'FRAME' for item in selected):
                layout.operator("kanvas.create_frame", icon='GROUP_VERTEX',
                                text=f"Create Frame ({n_sel})" if n_sel > 1 else "Create Frame")
                if any(item.item_type == 'FRAME' and item.show_in_editor
                       for item in settings.images):
                    layout.operator("kanvas.attach_to_frame", icon='LINKED',
                                    text="Attach Selection to Frame...")
            layout.separator()
            layout.label(text="Group", icon='GROUP')
            layout.operator("kanvas.group_items", icon='GROUP', text="Group (Ctrl+G)")
            if any(item.frame_is_group or owning_group(settings, item) is not None
                   for item in selected):
                layout.operator("kanvas.ungroup_items", icon='UNLINKED',
                                text="Ungroup (Ctrl+Shift+G)")
            if attached:
                layout.operator("kanvas.detach_from_frame", icon='UNLINKED',
                                text=f"Release from Frame ({len(attached)})" if len(attached) > 1
                                else "Release from Frame")
            if frame_name:
                layout.operator("kanvas.fit_frame", icon='FULLSCREEN_ENTER',
                                text="Fit Frame to Content").frame_name = frame_name

            if n_sel > 1:
                layout.separator()
                layout.label(text="Arrange", icon='ALIGN_LEFT')
                if all(item.item_type == 'IMAGE' for item in selected):
                    layout.operator("kanvas.pack_images", icon='GRID', text=f"Pack ({n_sel})")
                for mode, label in (('LEFT', 'Left'), ('CENTER_X', 'Center X'), ('RIGHT', 'Right'),
                                    ('TOP', 'Top'), ('CENTER_Y', 'Center Y'), ('BOTTOM', 'Bottom')):
                    layout.operator('kanvas.align_items', text=f"Align {label}").mode = mode
                if len(content) >= 3:
                    layout.operator('kanvas.distribute_items',
                                    text='Distribute Horizontally').axis = 'HORIZONTAL'
                    layout.operator('kanvas.distribute_items',
                                    text='Distribute Vertically').axis = 'VERTICAL'

            if any(item.item_type == 'SHAPE' for item in content):
                layout.separator()
                layout.operator("kanvas.export_shapes_svg", icon='EXPORT', text="Export Shapes as SVG...")

            if len(content) > 1:
                layout.separator()
                layout.operator("kanvas.connect_items", icon='CON_TRACKTO',
                                text="Connect with Arrows (Ctrl+L)")

            if content:
                layout.separator()
                layout.label(text="Reset Transform", icon='LOOP_BACK')
                layout.operator("kanvas.reset_transform", text="Location").transform_type = 'LOCATION'
                if any(item.item_type == 'IMAGE' for item in content):
                    layout.operator("kanvas.reset_transform", text="Scale").transform_type = 'SCALE'
                    layout.operator("kanvas.reset_transform", text="Rotation").transform_type = 'ROTATION'

            layout.separator()
            layout.label(text="Edit", icon='GREASEPENCIL')
            if content:
                layout.operator("kanvas.duplicate_image", icon='DUPLICATE', text="Duplicate")
            layout.operator("kanvas.copy_style", icon='COPYDOWN', text="Copy Style")
            layout.operator("kanvas.paste_style", icon='PASTEDOWN', text="Paste Style")
            layout.operator("kanvas.remove_image", icon='TRASH', text=f"Delete ({n_sel})")
            layout.separator()
            layout.menu("KANVAS_MT_add_content", text="Add", icon='ADD')

        else:
            # No selection: show content creation options.
            layout.label(text="Kanvas", icon='IMAGE_DATA')
            layout.separator()
            draw_kanvas_add_entries(layout)
