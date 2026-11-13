"""Kanvas bindings stored in Blender's editable add-on keymap."""

import bpy

_items = []
_hand_item = None
_hover_item = None
# Blender looks at the generic View2D keymap (plain, Ctrl and Shift + wheel) and the
# Frames keymap (Alt + wheel) before the Node Editor keymap, so wheel shortcuts
# registered only in the Node Editor never fire. They are added to those keymaps
# too; the operator's poll keeps them inert outside a Kanvas Tree.
_OWNED_KEYMAPS = {('Node Editor', 'NODE_EDITOR'), ('View2D', 'EMPTY'), ('Frames', 'EMPTY'),
                  ('3D View', 'VIEW_3D'), ('Window', 'EMPTY')}
_MANAGED_OPERATORS = {'kanvas.interact', 'kanvas.quick_arrow',
                      'kanvas.paste_image', 'kanvas.hand_cursor', 'kanvas.hand_hover',
                      'kanvas.isolate_markup_region', 'kanvas.overlay_edit_key',
                      'kanvas.overlay_edit'}

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
    ('Vertex Type (Edit Vertices)', 'VERTEX_TYPE'),
    ('Select Contour (Edit Vertices)', 'SELECT_CONTOUR'),
    ('Edit Vertices (enter / leave)', 'VERTEX_EDIT'),
)


# (action, key, modifiers): Alt + drag moves, Alt + right drag rotates, Alt + Shift + drag scales.
OVERLAY_SHORTCUTS = (
    ('MOVE', 'LEFTMOUSE', {'alt': True}),
    ('ROTATE', 'RIGHTMOUSE', {'alt': True}),
    ('SCALE', 'LEFTMOUSE', {'alt': True, 'shift': True}),
    ('RESET', 'HOME', {'alt': True}),
    ('OPACITY_UP', 'WHEELUPMOUSE', {'alt': True, 'ctrl': True}),
    ('OPACITY_DOWN', 'WHEELDOWNMOUSE', {'alt': True, 'ctrl': True}),
)
OVERLAY_LABELS = {'MOVE': 'Overlay: Move (drag)', 'ROTATE': 'Overlay: Rotate (drag)',
                  'SCALE': 'Overlay: Scale (drag)', 'RESET': 'Overlay: Reset',
                  'OPACITY_UP': 'Overlay: Opacity up (wheel)',
                  'OPACITY_DOWN': 'Overlay: Opacity down (wheel)'}


def sync_hand_cursor():
    """Enable the MOUSEMOVE hand-cursor binding only while a tree is in Move mode."""
    if _hand_item is None:
        return
    try:
        from .operators.ops_modal import _shape_armed_areas
        moving = any(tree.bl_idname == 'KanvasNodeTree'
                     and tree.kanvas_settings.canvas_mode == 'MOVE'
                     for tree in bpy.data.node_groups)
        _hand_item.active = bool(_shape_armed_areas) or moving
        if _hover_item is not None:
            _hover_item.active = moving
        if not moving:
            from .operators.ops_cursor import release_all
            release_all()
    except (ReferenceError, RuntimeError, AttributeError):
        pass


def unregister():
    global _hand_item, _hover_item
    _hand_item = None
    _hover_item = None
    try:
        from .operators.ops_cursor import release_all
        release_all()
    except (ImportError, RuntimeError, ReferenceError):
        pass
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
    global _hand_item, _hover_item
    try:
        window_km = keyconfig.keymaps.new(name='Window', space_type='EMPTY')
        _hover_item = window_km.keymap_items.new('kanvas.hand_hover', 'MOUSEMOVE', 'ANY', any=True)
        _items.append((window_km, _hover_item))
    except (TypeError, ValueError) as exc:
        print(f"Kanvas: hand hover binding failed: {exc}")
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
    try:
        connect = km.keymap_items.new('kanvas.connect_items', 'L', 'PRESS', ctrl=True)
        _items.append((km, connect))
    except (TypeError, ValueError) as exc:
        print(f"Kanvas: invalid connect shortcut: {exc}")
    for key, direction, modifiers in (('PAGE_UP', 'UP', {}), ('PAGE_DOWN', 'DOWN', {}),
                                      ('PAGE_UP', 'TOP', {'shift': True}),
                                      ('PAGE_DOWN', 'BOTTOM', {'shift': True})):
        try:
            move = km.keymap_items.new('kanvas.move_in_stack', key, 'PRESS', **modifiers)
            move.properties.direction = direction
            _items.append((km, move))
        except (TypeError, ValueError) as exc:
            print(f"Kanvas: invalid stack shortcut {key!r}: {exc}")
    for mode, modifiers in (('PEN', {'shift': True}), ('POLYGON', {'ctrl': True})):
        try:
            draw = km.keymap_items.new('kanvas.draw_polygon', 'P', 'PRESS', **modifiers)
            draw.properties.mode = mode
            _items.append((km, draw))
        except (TypeError, ValueError) as exc:
            print(f"Kanvas: invalid {mode.lower()} shortcut: {exc}")
    for key, direction in (('RIGHT_BRACKET', 1),('LEFT_BRACKET', -1),
                           ('BACK_SLASH', 0)):
        try:
            isolate = km.keymap_items.new('kanvas.isolate_markup_region', key, 'PRESS')
            isolate.properties.direction = direction
            _items.append((km, isolate))
        except (TypeError, ValueError) as exc:
            print(f"Kanvas: invalid isolate shortcut {key!r}: {exc}")
    bind('MASK', 'M')
    bind('COLOR', 'C')
    bind('VERTEX_TYPE', 'V')
    bind('SELECT_CONTOUR', 'L')
    bind('VERTEX_EDIT', 'E')
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
    # The overlay edit key (Alt by default) in the 3D View: a one-shot that only notes the
    # key going down or up. Every modifier is bound; the operator reads the preference.
    try:
        view3d = keyconfig.keymaps.new(name='3D View', space_type='VIEW_3D',
                                       region_type='WINDOW')
        for key in ('LEFT_ALT', 'RIGHT_ALT', 'LEFT_CTRL', 'RIGHT_CTRL',
                    'LEFT_SHIFT', 'RIGHT_SHIFT'):
            item = view3d.keymap_items.new('kanvas.overlay_edit_key', key, 'ANY', any=True)
            _items.append((view3d, item))
        item = view3d.keymap_items.new('kanvas.overlay_edit_key', 'MOUSEMOVE', 'ANY', any=True)
        _items.append((view3d, item))
        # The overlay shortcuts. Alt + wheel is the timeline's, so the wheel is not used.
        # The operator lets the event go on when the pointer is not over an overlay.
        for action, key, modifiers in OVERLAY_SHORTCUTS:
            item = view3d.keymap_items.new('kanvas.overlay_edit', key, 'PRESS', **modifiers)
            item.properties.action = action
            _items.append((view3d, item))
    except (TypeError, ValueError) as exc:
        print(f"Kanvas: overlay edit key binding failed: {exc}")
    bpy.context.window_manager.keyconfigs.update()


def iter_ui_bindings(window_manager):
    """Return effective, user-editable bindings for the preferences panel."""
    if not _items:
        return
    keyconfig = window_manager.keyconfigs.user
    yield from _iter_overlay_bindings(keyconfig)
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
        elif item.idname == 'kanvas.move_in_stack':
            yield {'UP': 'Move Up (to the front)', 'DOWN': 'Move Down (to the back)',
                   'TOP': 'Move to Front', 'BOTTOM': 'Move to Back'}[item.properties.direction], \
                keyconfig, km, item
        elif item.idname == 'kanvas.draw_polygon':
            label = 'Pen (free path)' if item.properties.mode == 'PEN' else 'Polygon'
            yield label, keyconfig, km, item


def _iter_overlay_bindings(keyconfig):
    """The overlay shortcuts of the 3D View keymap, for the preferences panel."""
    km = keyconfig.keymaps.get('3D View') if keyconfig else None
    if km is None:
        return
    km = km.active()
    found = {}
    for item in km.keymap_items:
        if item.idname == 'kanvas.overlay_edit':
            found.setdefault(item.properties.action, item)
    for action, _, _ in OVERLAY_SHORTCUTS:
        if action in found:
            yield OVERLAY_LABELS[action], keyconfig, km, found[action]


def register():
    rebuild()
