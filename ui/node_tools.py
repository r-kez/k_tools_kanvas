"""The toolbar (T) of a Kanvas board: Kanvas's own tools, none of Blender's. Only Edit
for now; the pencil will join it. Creating items stays in the Add menu.

Tools are registered like any add-on's, then the function that lists the Node Editor's
tools is wrapped: on a Kanvas board it yields only the `kanvas.*` tools, anywhere else
everything but them. A slow timer keeps the active tool honest: a board never keeps a
Blender tool active (it falls back to Edit) and another tree never keeps a Kanvas one.
`unregister` puts the list back. The `simplified_node_toolbar` preference turns the
filtering off, which shows Blender's tools and hides the Kanvas ones.
"""

import bpy

from .node_header import is_kanvas_header

PREFIX = 'kanvas.'
EDIT_TOOL = 'kanvas.edit'
PENCIL_TOOL = 'kanvas.pencil'
ERASER_TOOL = 'kanvas.eraser'
_PRESS = {'type': 'LEFTMOUSE', 'value': 'PRESS'}
# Where the pointer is, and Alt going down or up, so the pencil and eraser marks follow it.
_CURSOR = (('kanvas.pencil_cursor', {'type': 'MOUSEMOVE', 'value': 'ANY', 'any': True}, {}),
           ('kanvas.pencil_cursor', {'type': 'LEFT_ALT', 'value': 'ANY', 'any': True}, {}),
           ('kanvas.pencil_cursor', {'type': 'RIGHT_ALT', 'value': 'ANY', 'any': True}, {}))
BLENDER_TOOL = 'builtin.select'
_ORIGINAL = '_kanvas_original_tools_from_context'

# (idname, label, description, icon, keymap). Creating things is the Add menu's job.
TOOLS = (
    (EDIT_TOOL, 'Edit', 'Select, move and edit images, cards and frames',
     'ops.generic.select', ()),
    (PENCIL_TOOL, 'Pencil', 'Drag to draw. The first stroke makes a Pencil Drawing and the '
     'strokes after it join it; E on a drawing draws on it again. Hold Alt to erase, Shift '
     'to draw a loose drawing',
     'ops.gpencil.draw',
     (*_CURSOR,
      ('kanvas.pencil_stroke', _PRESS, {}),
      ('kanvas.pencil_stroke', {**_PRESS, 'shift': True}, {'properties': [('loose', True)]}),
      ('kanvas.pencil_erase', {**_PRESS, 'alt': True}, {}),
      ('kanvas.pencil_pick', {**_PRESS, 'ctrl': True}, {}),
      ('kanvas.pencil_pick', {**_PRESS, 'ctrl': True, 'shift': True},
       {'properties': [('extend', True)]}))),
    (ERASER_TOOL, 'Eraser', 'Drag over the strokes of a Pencil Drawing to rub them out where you pass',
     'ops.gpencil.draw_eraser', (*_CURSOR, ('kanvas.pencil_erase', _PRESS, {}))),
)


def _enabled():
    from ..utils.gpu.gpu_common import get_prefs
    prefs = get_prefs()
    return prefs is None or getattr(prefs, 'simplified_node_toolbar', True)


def _ids(item):
    if item is None:
        return ()
    if type(item) is tuple:     # a group; a ToolDef is a named tuple
        return tuple(tool.idname for tool in item if tool is not None)
    return (item.idname,)


def filtered(items, kanvas):
    """`items` (tools, groups of tools and None separators) as a board or another tree
    shows them: the Kanvas tools alone, or all but them."""
    kept = []
    for item in items:
        ids = _ids(item)
        if item is None:
            if kanvas:
                kept.append(None)
        elif all(i.startswith(PREFIX) for i in ids) == kanvas:
            kept.append(item)
    while kept and kept[0] is None:
        kept.pop(0)
    while kept and kept[-1] is None:
        kept.pop()
    return [item for index, item in enumerate(kept)
            if item is not None or kept[index - 1] is not None]


def _tool_classes():
    classes = []
    for idname, label, description, icon, keymap in TOOLS:
        name = 'KANVAS_TOOL_' + idname.split('.', 1)[1].upper()
        classes.append(type(name, (bpy.types.WorkSpaceTool,), {
            'bl_space_type': 'NODE_EDITOR', 'bl_context_mode': None,
            'bl_idname': idname, 'bl_label': label, 'bl_description': description,
            'bl_icon': icon, 'bl_keymap': keymap, 'bl_widget': None,
        }))
    return classes


_registered = []


def _helper():
    return bpy.types.NODE_PT_tools_active


def _install_filter():
    helper = _helper()
    if hasattr(helper, _ORIGINAL):
        return
    original = helper.tools_from_context

    def tools_from_context(cls, context, mode=None):
        kanvas = is_kanvas_header(context) and _enabled()
        yield from filtered(original(context, mode), kanvas)

    setattr(helper, _ORIGINAL, helper.__dict__['tools_from_context'])
    helper.tools_from_context = classmethod(tools_from_context)


def _remove_filter():
    helper = _helper()
    stored = helper.__dict__.get(_ORIGINAL)
    if stored is not None:
        helper.tools_from_context = stored
        delattr(helper, _ORIGINAL)


def _keep_tool_honest():
    """Fall back to Edit on a board holding a Blender tool, and to Blender's select tool
    on any other tree holding a Kanvas one."""
    try:
        windows = tuple(bpy.context.window_manager.windows)
    except AttributeError:
        return 1.0
    for window in windows:
        # The active tool belongs to the workspace, shared by every Node Editor in it:
        # with a board and another tree side by side neither can be put right, so leave it.
        editors = [(area, getattr(area.spaces.active, 'edit_tree', None))
                   for area in window.screen.areas if area.type == 'NODE_EDITOR']
        boards = [area for area, tree in editors
                  if tree is not None and tree.bl_idname == 'KanvasNodeTree']
        if not editors or (boards and len(boards) != len(editors)):
            continue
        board = bool(boards) and _enabled()
        tool = window.workspace.tools.from_space_node()
        if tool is not None and tool.idname != PENCIL_TOOL:
            # Leaving the pencil ends the drawing it was drawing on.
            for area in boards:
                for item in area.spaces.active.edit_tree.kanvas_settings.images:
                    if item.pencil_editing:
                        item.pencil_editing = False
                        for stroke in item.shape_strokes:
                            stroke.selected = False
        if tool is None or board == tool.idname.startswith(PREFIX):
            continue
        area = (boards or [editors[0][0]])[0]
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        try:
            with bpy.context.temp_override(window=window, area=area, region=region):
                bpy.ops.wm.tool_set_by_id(name=EDIT_TOOL if board else BLENDER_TOOL,
                                          space_type='NODE_EDITOR')
        except RuntimeError:
            pass
    return 1.0


def register():
    _registered.clear()
    for index, cls in enumerate(_tool_classes()):
        bpy.utils.register_tool(cls, separator=index > 0)
        _registered.append(cls)
    _install_filter()
    if not bpy.app.timers.is_registered(_keep_tool_honest):
        bpy.app.timers.register(_keep_tool_honest, first_interval=1.0, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_keep_tool_honest):
        bpy.app.timers.unregister(_keep_tool_honest)
    _remove_filter()
    for cls in reversed(_registered):
        try:
            bpy.utils.unregister_tool(cls)
        except (ValueError, RuntimeError, KeyError):
            pass
    _registered.clear()
