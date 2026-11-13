"""A sidebar (N panel) with only the K-Tools panels on a Kanvas board.

Every other panel in the Node Editor sidebar, Blender's and other add-ons', gets a
`poll` that says no on a Kanvas board and defers to its own everywhere else. A tab with
no panel left disappears. Panels registered later are caught by a slow rescan.
`unregister` puts every poll back. The `simplified_node_sidebar` preference turns it off.
"""

import bpy

from .node_header import is_kanvas_header

_ROOT = __package__.rpartition('.')[0]
_patched = {}       # panel class -> (its own poll before, or None; was re-registered)


def _enabled():
    from ..utils.gpu.gpu_common import get_prefs
    prefs = get_prefs()
    return prefs is None or getattr(prefs, 'simplified_node_sidebar', True)


def _sidebar_panels():
    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)
    seen = set()
    for cls in walk(bpy.types.Panel):
        if (cls not in seen and getattr(cls, 'bl_space_type', None) == 'NODE_EDITOR'
                and getattr(cls, 'bl_region_type', None) == 'UI'
                and not cls.__module__.startswith(_ROOT)):
            seen.add(cls)
            yield cls


def _patch(cls):
    inherited = getattr(cls, 'poll', None)
    own = cls.__dict__.get('poll')
    # A panel that never had a poll gets none from Blender's registry until it is
    # registered again with one.
    reregister = inherited is None

    def poll(klass, context):
        if is_kanvas_header(context) and _enabled():
            return False
        return True if inherited is None else inherited(context)

    if reregister:
        bpy.utils.unregister_class(cls)
        cls.poll = classmethod(poll)
        bpy.utils.register_class(cls)
    else:
        cls.poll = classmethod(poll)
    _patched[cls] = (own, reregister)


def _restore(cls):
    own, reregistered = _patched.pop(cls)

    def put_back():
        if own is not None:
            cls.poll = own
        elif 'poll' in cls.__dict__:
            del cls.poll

    if reregistered:
        bpy.utils.unregister_class(cls)
        put_back()
        bpy.utils.register_class(cls)
    else:
        put_back()


def patch_panels():
    """Hide the foreign sidebar panels that are not hidden yet."""
    for cls in list(_sidebar_panels()):
        if cls not in _patched:
            try:
                _patch(cls)
            except Exception:
                _patched.pop(cls, None)


def restore_panels():
    for cls in list(_patched):
        try:
            _restore(cls)
        except Exception:
            _patched.pop(cls, None)


def _rescan():
    patch_panels()
    return 5.0


def register():
    patch_panels()
    if not bpy.app.timers.is_registered(_rescan):
        bpy.app.timers.register(_rescan, first_interval=5.0, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_rescan):
        bpy.app.timers.unregister(_rescan)
    restore_panels()
