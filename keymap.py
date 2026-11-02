"""Kanvas bindings stored in Blender's editable add-on keymap."""

import bpy

_items = []
_hand_item = None
# Blender looks at the generic View2D keymap (plain, Ctrl and Shift + wheel) and the
# Frames keymap (Alt + wheel) before the Node Editor keymap, so wheel shortcuts
# registered only in the Node Editor never fire. They are added to those keymaps
# too; the operator's poll keeps them inert outside a Kanvas Tree.
_OWNED_KEYMAPS = {('Node Editor', 'NODE_EDITOR'), ('View2D', 'EMPTY'), ('Frames', 'EMPTY')}
_MANAGED_OPERATORS = {'kanvas.interact', 'kanvas.quick_arrow',
                      'kanvas.paste_image', 'kanvas.hand_cursor',
                      'kanvas.isolate_markup_region'}

UI_ACTIONS = (
    ('Move', 'MOVE'),
    ('Rotate', 'ROTATE'),
    ('Scale', 'SCALE'),
    ('Reset Position', 'RESET_MOVE'),
    ('Reset Rotation', 'RESET_ROTATE'),
    ('Reset Scale', 'RESET_SCALE'),
    ('Duplicate', 'DUPLICATE'),
    ('Group', 'GROUP'),
    ('Ungroup', 'UNGROUP'),
    ('Delete', 'DELETE'),
    ('Box Select', 'BOX'),
    ('Select Visible', 'SELECT_ALL'),
    ('Invert Selection', 'SELECT_INVERT'),
    ('Pack', 'PACK'),
    ('Create Frame', 'CREATE_FRAME'),
    ('Release from Frame', 'DETACH'),
    ('Rename', 'RENAME'),
    ('Focus Selection', 'FOCUS'),
    ('Mask Mode', 'MASK'),
    ('Color Mode', 'COLOR'),
)


def sync_hand_cursor():
    """Enable the MOUSEMOVE hand-cursor binding only while a tree is in Move mode."""
    if _hand_item is None:
        return
    try:
        _hand_item.active = any(
            tree.bl_idname == 'KanvasNodeTree'
            and tree.kanvas_settings.canvas_mode == 'MOVE'
            for tree in bpy.data.node_groups)
    except (ReferenceError, RuntimeError, AttributeError):
        pass


def unregister():
    global _hand_item
    _hand_item = None
    for km, item in _items:
        try:
            km.keymap_items.remove(item)
        except (ReferenceError, RuntimeError, ValueError):
            pass
    _items.clear()
    keyconfig = getattr(bpy.context.window_manager.keyconfigs, 'addon', None)
    if keyconfig is None:
        return
    for km in keyconfig.keymaps:
        if (km.name, km.space_type) not in _OWNED_KEYMAPS:
            continue
        for item in tuple(km.keymap_items):
            if item.idname in _MANAGED_OPERATORS:
                km.keymap_items.remove(item)


def rebuild():
    unregister()
    keyconfig = getattr(bpy.context.window_manager.keyconfigs, 'addon', None)
    if keyconfig is None:
        return
    km = keyconfig.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')

    view2d = keyconfig.keymaps.new(name='View2D', space_type='EMPTY', region_type='WINDOW')
    frames = keyconfig.keymaps.new(name='Frames', space_type='EMPTY', region_type='WINDOW')

    def bind(action, key, *, value='PRESS', shift=False, ctrl=False, alt=False, any=False,
             keymap=None):
        if not key:
            return
        target = keymap or km
        try:
            item = target.keymap_items.new(
                'kanvas.interact', key, value,
                shift=shift, ctrl=ctrl, alt=alt, any=any,
            )
            item.properties.action = action
            _items.append((target, item))
        except (TypeError, ValueError) as exc:
            print(f"Kanvas: invalid shortcut {key!r} for {action}: {exc}")

    bind('CLICK', 'LEFTMOUSE', any=True)
    bind('RENAME', 'F2')
    bind('FOCUS', 'NUMPAD_PERIOD')
    for key in ('LEFT_ALT', 'RIGHT_ALT', 'LEFT_SHIFT', 'RIGHT_SHIFT',
                'LEFT_CTRL', 'RIGHT_CTRL'):
        bind('MODIFIER', key, any=True)
        bind('MODIFIER', key, value='RELEASE', any=True)
    bind('CONTEXT', 'RIGHTMOUSE', any=True)
    bind('BOX', 'B')
    bind('SELECT_ALL', 'A', ctrl=True)
    bind('SELECT_INVERT', 'I', ctrl=True)
    bind('TOGGLE_MODE', 'TAB')
    global _hand_item
    try:
        _hand_item = km.keymap_items.new('kanvas.hand_cursor', 'MOUSEMOVE', 'ANY', any=True)
        _items.append((km, _hand_item))
        sync_hand_cursor()
    except (TypeError, ValueError) as exc:
        print(f"Kanvas: hand cursor binding failed: {exc}")
    bind('CANCEL_BOX', 'ESC')
    bind('PACK', 'P')
    try:
        paste = km.keymap_items.new('kanvas.paste_image', 'V', 'PRESS', ctrl=True)
        _items.append((km, paste))
    except (TypeError, ValueError) as exc:
        print(f"Kanvas: invalid paste shortcut: {exc}")
    for key, direction in (('RIGHT_BRACKET', 1), ('LEFT_BRACKET', -1),
                           ('BACK_SLASH', 0)):
        try:
            isolate = km.keymap_items.new('kanvas.isolate_markup_region', key, 'PRESS')
            isolate.properties.direction = direction
            _items.append((km, isolate))
        except (TypeError, ValueError) as exc:
            print(f"Kanvas: invalid isolate shortcut {key!r}: {exc}")
    bind('MASK', 'M')
    bind('COLOR', 'C')
    bind('F_PRESS', 'F')
    bind('F_RELEASE', 'F', value='RELEASE')
    try:
        quick_arrow = km.keymap_items.new('kanvas.quick_arrow', 'A', 'PRESS')
        _items.append((km, quick_arrow))
    except (TypeError, ValueError) as exc:
        print(f"Kanvas: invalid quick arrow shortcut: {exc}")
    bind('CREATE_FRAME', 'F', shift=True)
    bind('MOVE', 'G')
    bind('SCALE', 'S')
    bind('ROTATE', 'R')
    bind('DELETE', 'X')
    bind('DELETE', 'DEL')
    bind('DUPLICATE', 'D', shift=True)
    bind('GROUP', 'G', ctrl=True)
    bind('UNGROUP', 'G', ctrl=True, shift=True)
    bind('DETACH', 'U', alt=True)
    bind('RESET_MOVE', 'G', alt=True)
    bind('RESET_SCALE', 'S', alt=True)
    bind('RESET_ROTATE', 'R', alt=True)
    # Wheel shortcuts live where Blender resolves the wheel first (see _OWNED_KEYMAPS).
    # Plain wheel scrolls a long text card when allowed and otherwise passes
    # through, so Blender still zooms.
    for modifier, keymap in ((None, view2d), ('CTRL', view2d), ('SHIFT', view2d),
                             ('ALT', frames)):
        kw = {modifier.lower(): True} if modifier else {}
        bind('WHEEL', 'WHEELUPMOUSE', keymap=keymap, **kw)
        bind('WHEEL', 'WHEELDOWNMOUSE', keymap=keymap, **kw)
    bpy.context.window_manager.keyconfigs.update()


def iter_ui_bindings(window_manager):
    """Return effective, user-editable bindings for the preferences panel."""
    if not _items:
        return
    keyconfig = window_manager.keyconfigs.user
    km = keyconfig.keymaps.get('Node Editor') if keyconfig else None
    if km is None:
        return
    km = km.active()
    by_action = {}
    for item in km.keymap_items:
        if item.idname == 'kanvas.interact':
            by_action.setdefault(item.properties.action, []).append(item)
    for label, action in UI_ACTIONS:
        for index, item in enumerate(by_action.get(action, ())):
            item_label = f'{label} (alternate)' if index else label
            yield item_label, keyconfig, km, item
    for item in km.keymap_items:
        if item.idname == 'kanvas.quick_arrow':
            yield 'Quick Arrow (hold)', keyconfig, km, item
        elif item.idname == 'kanvas.paste_image':
            yield 'Paste Image', keyconfig, km, item


def register():
    rebuild()
