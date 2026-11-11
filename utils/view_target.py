"""Which 3D View shows the Kanvas overlays and live references.

By default every 3D View shows an overlay or live reference. With `limit_view` on, only
the 3D View with the ID `view_id` does (each entry has its own). The ID is the one the K-Tools View Sync add-on uses: the
3D Views counted over all windows in order, starting at 0. Pressing Identify shows each
view's ID in the view for a moment.
"""

import time

import bpy

FLASH_SECONDS = 3.0

_flash_handle = None
_flash_until = 0.0


def view_areas(window_manager=None):
    """Every 3D View area of every window, in ID order: [(window_index, area)]."""
    window_manager = window_manager or bpy.context.window_manager
    found = []
    for window_index, window in enumerate(window_manager.windows):
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                found.append((window_index, area))
    return found


def area_id(area):
    """The ID of a 3D View area, None when it is not one of the open ones."""
    for index, (_, other) in enumerate(view_areas()):
        if other == area:
            return index
    return None


def target_exists(entry):
    return 0 <= entry.view_id < len(view_areas())


def shows_here(entry, area):
    """Whether the 3D View `area` shows this reference entry."""
    if not entry.limit_view:
        return True
    return area is not None and area_id(area) == entry.view_id


def tag_3d_views():
    for _, area in view_areas():
        area.tag_redraw()


# --- Showing the IDs -------------------------------------------------------------------

def _draw_ids():
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    context = bpy.context
    remaining = _flash_until - time.time()
    area, region = context.area, context.region
    if remaining <= 0 or area is None or area.type != 'VIEW_3D':
        return
    index = area_id(area)
    if index is None:
        return
    alpha = min(1.0, remaining / 0.5)
    text = f'View {index}'
    blf.size(0, 48)
    width, height = blf.dimensions(0, text)
    x, y = (region.width - width) * 0.5, (region.height - height) * 0.5
    pad = 20
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    corners = [(x - pad, y - pad), (x + width + pad, y - pad),
               (x + width + pad, y + height + pad), (x - pad, y + height + pad)]
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float('color', (0.0, 0.0, 0.0, 0.5 * alpha))
    batch_for_shader(shader, 'TRIS', {'pos': corners}, indices=((0, 1, 2), (2, 3, 0))).draw(shader)
    blf.color(0, 1.0, 1.0, 1.0, alpha)
    blf.position(0, x, y, 0)
    blf.draw(0, text)
    gpu.state.blend_set('NONE')


def _stop_flash():
    """Timer: take the IDs away once their time is up."""
    global _flash_handle
    if time.time() < _flash_until:
        return 0.2
    if _flash_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_flash_handle, 'WINDOW')
        _flash_handle = None
    tag_3d_views()
    return None


def flash_ids():
    """Show the ID of every 3D View for a few seconds."""
    global _flash_handle, _flash_until
    _flash_until = time.time() + FLASH_SECONDS
    if _flash_handle is None:
        _flash_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_ids, (), 'WINDOW', 'POST_PIXEL')
    if not bpy.app.timers.is_registered(_stop_flash):
        bpy.app.timers.register(_stop_flash, first_interval=0.2)
    tag_3d_views()


def register():
    pass


def unregister():
    global _flash_handle
    if bpy.app.timers.is_registered(_stop_flash):
        bpy.app.timers.unregister(_stop_flash)
    if _flash_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_flash_handle, 'WINDOW')
        _flash_handle = None
