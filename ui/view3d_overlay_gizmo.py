"""Placing a Kanvas overlay in the 3D View: while its Adjust button is on, a frame around
it can be dragged to move it, and its top right corner to scale it. The drag is the
gizmo's own short interaction, ended by releasing the mouse; nothing keeps running
afterwards. With Adjust off there is no gizmo, so clicks reach the scene."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from ..utils import overlay_3d, view_target

COLOR = (0.3, 0.75, 1.0, 0.9)
COLOR_HOVER = (1.0, 1.0, 1.0, 1.0)


def _adjusted(context):
    """(entry, rect) of the overlay being adjusted in this view, or None. An overlay
    fitted to the camera frame is placed by the camera, not by hand."""
    scene = getattr(context, 'scene', None)
    if scene is None or scene.kanvas_overlays_hidden:
        return None
    for entry in overlay_3d.overlays(scene):
        if entry.adjusting and entry.show:
            if not view_target.shows_here(entry, context.area):
                return None
            if entry.fit_camera and overlay_3d.camera_frame(context) is not None:
                return None
            layout = overlay_3d.entry_layout(context, entry)
            return None if layout is None else (entry, layout[1])
    return None


class KANVAS_GT_overlay_frame(bpy.types.Gizmo):
    bl_idname = 'KANVAS_GT_overlay_frame'

    def setup(self):
        self._part = None
        self._start = None

    def draw(self, context):
        found = _adjusted(context)
        if found is None:
            return
        left, bottom, right, top = found[1]
        region = context.region
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        lines = [(left, bottom), (right, bottom), (right, bottom), (right, top),
                 (right, top), (left, top), (left, top), (left, bottom)]
        size = overlay_3d.HANDLE_SIZE * 0.6
        handle = [(right - size, top - size), (right + size, top - size),
                  (right + size, top + size), (right - size, top + size)]
        color = COLOR_HOVER if self.is_highlight else COLOR
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_matrix(Matrix.Identity(4))
            gpu.matrix.load_projection_matrix(Matrix((
                (2.0 / region.width, 0, 0, -1), (0, 2.0 / region.height, 0, -1),
                (0, 0, 1, 0), (0, 0, 0, 1))))
            gpu.state.blend_set('ALPHA')
            gpu.state.line_width_set(2.0)
            shader.bind()
            shader.uniform_float('color', color)
            batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)
            batch_for_shader(shader, 'TRIS', {'pos': handle},
                             indices=((0, 1, 2), (0, 2, 3))).draw(shader)
            gpu.state.line_width_set(1.0)
            gpu.state.blend_set('NONE')

    def test_select(self, context, location):
        found = _adjusted(context)
        part = None if found is None else overlay_3d.hit_part(found[1], location)
        if part is not None:
            self._part = part
        return -1 if part is None else 0

    def invoke(self, context, event):
        found = _adjusted(context)
        if found is None:
            return {'CANCELLED'}
        entry, rect = found
        mouse = (event.mouse_region_x, event.mouse_region_y)
        center = ((rect[0] + rect[2]) * 0.5, (rect[1] + rect[3]) * 0.5)
        part = overlay_3d.hit_part(rect, mouse) or 'MOVE'
        self._start = (part, mouse, tuple(entry.offset), entry.size, center)
        return {'RUNNING_MODAL'}

    def modal(self, context, event, tweak):
        found = _adjusted(context)
        if found is None or self._start is None:
            return {'CANCELLED'}
        entry = found[0]
        part, start, offset, size, center = self._start
        mouse = (event.mouse_region_x, event.mouse_region_y)
        if part == 'MOVE':
            entry.offset = (offset[0] + mouse[0] - start[0], offset[1] + mouse[1] - start[1])
        else:
            before = max(1.0, ((start[0] - center[0]) ** 2 + (start[1] - center[1]) ** 2) ** 0.5)
            now = ((mouse[0] - center[0]) ** 2 + (mouse[1] - center[1]) ** 2) ** 0.5
            entry.size = max(0.02, size * now / before)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def exit(self, context, cancel):
        if cancel and self._start is not None:
            found = _adjusted(context)
            if found is not None:
                found[0].offset, found[0].size = self._start[2], self._start[3]
        self._start = None


class KANVAS_GGT_overlay_adjust(bpy.types.GizmoGroup):
    bl_idname = 'KANVAS_GGT_overlay_adjust'
    bl_label = 'Kanvas Overlay'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        scene = getattr(context, 'scene', None)
        return (scene is not None and hasattr(scene, 'kanvas_references')
                and not scene.kanvas_overlays_hidden
                and any(entry.adjusting and entry.show
                        and view_target.shows_here(entry, context.area)
                        for entry in overlay_3d.overlays(scene)))

    def setup(self, context):
        self.frame = self.gizmos.new(KANVAS_GT_overlay_frame.bl_idname)
