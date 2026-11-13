"""A lean Node Editor header for Kanvas boards: no View, Select or Overlays.

Blender draws the header in one function and has no call to take a menu out of it, so
the function that draws it (the first of the header's draw functions; what add-ons
append comes after it) is swapped for one that draws the Kanvas header on a Kanvas
board and Blender's own everywhere else. `unregister` puts Blender's back. The
`simplified_node_header` preference turns it off.
"""

import bpy

_MARK = '_kanvas_original_draw'


class KANVAS_MT_editor_menus(bpy.types.Menu):
    """The header menus a Kanvas board keeps."""
    bl_idname = 'KANVAS_MT_editor_menus'
    bl_label = ''

    def draw(self, _context):
        # View, Select and Node act on Blender's own nodes: only Add is Kanvas's.
        self.layout.menu('NODE_MT_add')


def is_kanvas_header(context):
    space = getattr(context, 'space_data', None)
    tree = getattr(space, 'edit_tree', None)
    return tree is not None and tree.bl_idname == 'KanvasNodeTree'


def _enabled():
    from ..utils.gpu.gpu_common import get_prefs
    prefs = get_prefs()
    return prefs is None or getattr(prefs, 'simplified_node_header', True)


def draw_kanvas_header(layout, context):
    """The Node Editor header of a Kanvas board."""
    snode = context.space_data
    layout.template_header()
    KANVAS_MT_editor_menus.draw_collapsible(context, layout)
    layout.separator_spacer()
    layout.template_ID(snode, 'node_tree', new='node.new_node_tree')
    layout.prop(snode, 'pin', text='', emboss=False)
    layout.separator_spacer()
    if len(snode.path) > 1:
        op = layout.operator('node.tree_path_parent', text='', icon='FILE_PARENT')
        op.parent_tree_index = len(snode.path) - 2
    row = layout.row(align=True)
    row.prop(context.tool_settings, 'use_snap_node', text='')
    row.active = snode.node_tree is not None


def _draw_funcs():
    return bpy.types.NODE_HT_header._dyn_ui_initialize()


def install():
    funcs = _draw_funcs()
    original = funcs[0]
    if hasattr(original, _MARK):
        return       # already swapped (a reload)
    blender_draw = original

    def draw(self, context):
        if is_kanvas_header(context) and _enabled():
            draw_kanvas_header(self.layout, context)
        else:
            blender_draw(self, context)

    setattr(draw, _MARK, blender_draw)
    funcs[0] = draw


def uninstall():
    funcs = _draw_funcs()
    original = getattr(funcs[0], _MARK, None)
    if original is not None:
        funcs[0] = original


def register():
    install()


def unregister():
    uninstall()
