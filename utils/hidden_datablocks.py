"""Keep Kanvas' own images out of Blender's image pickers.

Blender hides datablocks whose name starts with a dot from its ID dropdowns and
search lists (they remain visible in the Outliner's Blender File view). Kanvas
therefore prefixes the images it owns: the pictures on the canvas, the generated
mask / color layers and the icon textures. The preference "Hide Kanvas Images in
Blender Lists" switches this on and off; turning it off restores the names.
"""

import os
import time

import bpy

HIDE_PREFIX = '.'
GENERATED_PREFIXES = ('Kanvas Mask ', 'Kanvas Color Markup ')
_SWEEP_INTERVAL = 5.0
_last_sweep = 0.0


def enabled():
    from .gpu.gpu_common import get_prefs
    prefs = get_prefs()
    return prefs is None or getattr(prefs, 'hide_datablocks', True)


def hidden_name(name, hide=None):
    """`name` in its hidden or visible form (the current preference by default)."""
    if hide is None:
        hide = enabled()
    base = name[len(HIDE_PREFIX):] if name.startswith(HIDE_PREFIX) else name
    return HIDE_PREFIX + base if hide else base


def _icon_dir():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icons')


def owned_images():
    """Every image Kanvas created or displays."""
    result, seen = [], set()

    def add(image):
        if image is not None and image.name_full not in seen:
            seen.add(image.name_full)
            result.append(image)

    for tree in bpy.data.node_groups:
        if tree.bl_idname != 'KanvasNodeTree':
            continue
        for item in tree.kanvas_settings.images:
            add(item.image_data)
    icons = _icon_dir()
    for image in bpy.data.images:
        base = image.name.lstrip(HIDE_PREFIX)
        if base.startswith(GENERATED_PREFIXES) or image.filepath.startswith(icons):
            add(image)
    return result


def sweep():
    """Rename the owned images to match the preference. Returns how many changed."""
    global _last_sweep
    _last_sweep = time.monotonic()
    hide = enabled()
    changed = 0
    for image in owned_images():
        if image.library is not None or image.override_library is not None:
            continue   # linked data cannot be renamed
        wanted = hidden_name(image.name, hide)
        if wanted != image.name:
            image.name = wanted
            changed += 1
    return changed


def sweep_throttled():
    """Cheap periodic pass for images added since the last sweep (imports, paste)."""
    if time.monotonic() - _last_sweep >= _SWEEP_INTERVAL:
        sweep()
