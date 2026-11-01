import bpy
from ..utils.kanvas_data import get_settings
import math
from ..utils.gpu.gpu_common import rotate_point, get_prefs, get_collective_bounding_box
from ..utils.gizmo_geometry import handle_layout, collective_handle_layout
from ..utils.gpu.gpu_image import get_cached_texture
from ..utils.gpu.gpu_visibility import image_intersects_view


_active_modal_areas = set()
_box_armed_areas = set()


def clear_modal_areas():
    _active_modal_areas.clear()
    _box_armed_areas.clear()


def _modifier_held(event, modifier):
    return bool(getattr(event, modifier.lower(), False))


def _sync_modifiers(settings, event):
    settings.shift_is_held = event.shift
    settings.alt_is_held = event.alt
    settings.ctrl_is_held = event.ctrl
    if event.type.endswith('_ALT'):
        settings.alt_is_held = event.value == 'PRESS'
    elif event.type.endswith('_SHIFT'):
        settings.shift_is_held = event.value == 'PRESS'
    elif event.type.endswith('_CTRL'):
        settings.ctrl_is_held = event.value == 'PRESS'


def _rotation_step(ctrl, shift):
    return 1.0 if shift else 5.0


def _apply_rotation_delta(raw_delta, ctrl=False, shift=False):
    """Snap a relative rotation, with finer steps when both keys are held."""
    if not ctrl:
        return raw_delta
    step = _rotation_step(ctrl, shift)
    return round(raw_delta / step) * step


def _clear_image_selection(settings):
    """No active item means a frame sync cannot silently reselect an image."""
    changed = any(item.is_selected for item in settings.images)
    for item in settings.images:
        item.is_selected = False
    settings.active_image_index = -1
    return changed


def _clear_arrow_selection(settings):
    changed = any(arrow.is_selected for arrow in settings.arrows)
    for arrow in settings.arrows:
        arrow.is_selected = False
    settings.active_arrow_index = -1
    return changed


def _set_canvas_active(settings, image_index=-1, arrow_index=-1):
    """Change the UI's active row without collapsing a canvas multiselection."""
    from ..properties import suspend_selection_updates
    with suspend_selection_updates():
        settings.active_image_index = image_index
        settings.active_arrow_index = arrow_index


def _select_canvas_items(settings, invert=False):
    """Select visible board items without changing their layer or tree."""
    from ..properties import suspend_selection_updates

    before = (tuple(item.is_selected for item in settings.images),
              tuple(arrow.is_selected for arrow in settings.arrows),
              settings.active_image_index, settings.active_arrow_index)
    with suspend_selection_updates():
        for item in settings.images:
            item.is_selected = ((not item.is_selected if invert else True)
                                if item.show_in_editor and not item.is_locked else False)
        for arrow in settings.arrows:
            arrow.is_selected = (not arrow.is_selected if invert else True) if not arrow.is_locked else False

        selected_item = next((i for i, item in enumerate(settings.images)
                              if item.is_selected), -1)
        selected_arrow = next((i for i, arrow in enumerate(settings.arrows)
                               if arrow.is_selected), -1)
        settings.active_image_index = selected_item
        settings.active_arrow_index = -1 if selected_item >= 0 else selected_arrow

    after = (tuple(item.is_selected for item in settings.images),
             tuple(arrow.is_selected for arrow in settings.arrows),
             settings.active_image_index, settings.active_arrow_index)
    return before != after


def _undo_content_signature(settings):
    """Persistent canvas state; selection and gesture display state are excluded."""
    return tuple((item.item_id, item.item_type, tuple(item.location),
                  tuple(item.scale_xy), item.scale_master, tuple(item.shear_xy),
                  item.rotation, item.z_index, item.parent_frame,
                  item.frame_width, item.frame_height, item.auto_resize,
                  item.text_width, item.text_height, item.text_scale)
                 for item in settings.images)


def _event_in_canvas(context, event):
    """Only the node canvas may consume Kanvas mouse and keyboard events."""
    if context.region is not None and context.region.type != 'WINDOW':
        return False
    region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return False
    if not hasattr(event, 'mouse_x'):
        return context.region is not None and context.region.type == 'WINDOW'
    x, y = event.mouse_x, event.mouse_y
    if not (region.x <= x < region.x + region.width
            and region.y <= y < region.y + region.height):
        return False
    # UI, header and tool regions can overlap WINDOW in some layouts.
    return not any(
        r.type != 'WINDOW' and r.width > 1 and r.height > 1
        and r.x <= x < r.x + r.width and r.y <= y < r.y + r.height
        for r in context.area.regions
    )


class KanvasInteractionHelpers:
    """Shared hit testing and geometry for short Kanvas input gestures."""

    # -----------------------------------------------------------------------
    # Drag helpers
    # -----------------------------------------------------------------------

    def start_drag(self, context, img, mode, mouse_pos):
        """Prepara o estado inicial de um drag."""
        settings = get_settings(context)
        from ..utils.gpu import ensure_item_ids
        ensure_item_ids(settings)

        if mode == 'MOVE' and img.is_selected:
            selected_frame = next((item for item in settings.images
                                   if item.item_type == 'FRAME' and item.is_selected
                                   and item.show_in_editor and not item.is_locked), None)
            if selected_frame:
                self._start_frame_drag(context, selected_frame, 'MOVE', mouse_pos)
                return

        self.drag_target    = img
        self.drag_target_id = img.item_id
        self.drag_mode      = mode
        self.mouse_drag_started = False
        self.last_mouse_pos = mouse_pos
        self.init_loc       = (img.location[0], img.location[1])

        self.init_mouse_view   = (mouse_pos[0], mouse_pos[1])
        self.init_scale        = (img.scale_xy[0], img.scale_xy[1])
        self.init_scale_master = img.scale_master
        self.init_shear        = (img.shear_xy[0], img.shear_xy[1])
        self.init_rot          = img.rotation

        dx = mouse_pos[0] - img.location[0]
        dy = mouse_pos[1] - img.location[1]
        self.init_mouse_local = rotate_point((dx, dy), (0, 0), -img.rotation)

        self.multi_targets = []
        selected_images = [i for i in settings.images if i.is_selected and i.show_in_editor
                           and not i.is_locked
                           and ((i.item_type == 'IMAGE' and i.image_data)
                                or (mode == 'MOVE' and i.item_type == 'TEXT'))]

        if len(selected_images) > 1:
            # Multi-seleção: calcula bounding box coletiva para o pivot
            data_list = []
            for item in selected_images:
                tex = get_cached_texture(item.image_data) if item.image_data else None
                w, h = ((tex.texture.width, tex.texture.height) if (tex and tex.texture)
                        else item.image_data.size if item.image_data
                        else (item.text_width, item.text_height))
                if w > 0 and h > 0:
                    data_list.append((
                        item.location, item.scale_xy, item.scale_master,
                        item.shear_xy, item.rotation,
                        w, h
                    ))

                self.multi_targets.append({
                    'img':          item,
                    'item_id':      item.item_id,
                    'loc':          (item.location[0], item.location[1]),
                    'scale_master': item.scale_master,
                    'scale_xy':     (item.scale_xy[0], item.scale_xy[1]),
                    'rot':          item.rotation,
                    'orig_parent':  item.parent_frame,
                })

            bbox = get_collective_bounding_box(data_list)
            if bbox:
                self.selection_pivot = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
                cdx = mouse_pos[0] - self.selection_pivot[0]
                cdy = mouse_pos[1] - self.selection_pivot[1]
                self.init_mouse_local = (cdx, cdy)
            else:
                self.selection_pivot = (img.location[0], img.location[1])
        else:
            # Seleção única
            if img.is_selected:
                self.multi_targets.append({
                    'img':          img,
                    'item_id':      img.item_id,
                    'loc':          (img.location[0], img.location[1]),
                    'scale_master': img.scale_master,
                    'scale_xy':     (img.scale_xy[0], img.scale_xy[1]),
                    'rot':          img.rotation,
                    'orig_parent':  img.parent_frame,
                })
            self.selection_pivot = (img.location[0], img.location[1])

        if not self.multi_targets and img:
            self.multi_targets.append({
                'img':          img,
                'item_id':      img.item_id,
                'loc':          (img.location[0], img.location[1]),
                'scale_master': img.scale_master,
                'scale_xy':     (img.scale_xy[0], img.scale_xy[1]),
                'rot':          img.rotation,
                'orig_parent':  img.parent_frame,
            })

        from ..utils.arrow_geometry import capture_selected_arrow_move
        self.arrow_move_snapshots = (capture_selected_arrow_move(
            settings, (target['item_id'] for target in self.multi_targets))
            if mode == 'MOVE' else [])

        from ..utils.gpu import get_frame
        self.initial_frame_bounds = {}
        for t in self.multi_targets:
            pf = t['img'].parent_frame
            if pf and pf not in self.initial_frame_bounds:
                fr = get_frame(settings, pf)
                if fr:
                    self.initial_frame_bounds[pf] = (fr.location[0], fr.location[1], fr.frame_width, fr.frame_height)

        self.detached_in_gesture = set()
        self.f_is_held = bool(getattr(settings, 'f_is_held', False))
        self._constraint_state = {}
        self.affected_frame_names = {t['img'].parent_frame for t in self.multi_targets if t['img'].parent_frame}

        if self.f_is_held and mode == 'MOVE':
            for t in self.multi_targets:
                item = t['img']
                if item.parent_frame:
                    self.affected_frame_names.add(item.parent_frame)
                    item.parent_frame = ''
                    self.detached_in_gesture.add(item.item_id)
            if context.space_data and context.space_data.edit_tree:
                from ..utils.gpu import update_frame_bounds
                for fname in list(self.affected_frame_names):
                    update_frame_bounds(context.space_data.edit_tree, settings, fname, initial_bounds=self.initial_frame_bounds)

        if mode == 'ROTATE':
            self.initial_angle = self._get_angle(self.selection_pivot, mouse_pos)
            self.rotation_last_angle = self.initial_angle
            self.rotation_total_delta = 0.0
            self.keyboard_rotation_linear = (
                getattr(self, 'keyboard_transform', False)
                and math.dist(mouse_pos, self.selection_pivot) < 10.0
            )

    def _get_angle(self, center, mouse):
        return math.degrees(math.atan2(mouse[1] - center[1], mouse[0] - center[0]))

    def _constrain_value(self, raw, start, *, shift=False, ctrl=False, step=0.1, key=None):
        """Apply fine motion without a jump when Shift changes mid-gesture."""
        mode = key or self.drag_mode
        state = self._constraint_state.get(mode)
        if state is None:
            state = {'anchor_raw': start, 'anchor_value': start,
                     'last_raw': start, 'last_value': start, 'shift': shift}
            self._constraint_state[mode] = state
        if shift != state['shift']:
            state['anchor_raw'] = state['last_raw']
            state['anchor_value'] = state['last_value']
            state['shift'] = shift
        value = state['anchor_value'] + (raw - state['anchor_raw']) * (0.1 if shift else 1.0)
        if ctrl:
            increment = step * (0.1 if shift else 1.0)
            value = start + round((value - start) / increment) * increment
        state['last_raw'] = raw
        state['last_value'] = value
        return value

    # -----------------------------------------------------------------------
    # Gizmo / Hit testing
    # -----------------------------------------------------------------------

    def _get_gizmo_under_mouse(self, context, mouse_pos):
        """
        Retorna o índice do gizmo sob o mouse (em view space):
          0-3  → Cantos (Scale Uniform)
          4-7  → Meios (Stretch/Shear)
          8    → Rotação acima da borda superior
         -1   → Nenhum
        """
        settings = get_settings(context)
        if not settings.show_gizmos:
            return -1

        selected_images = [img for img in settings.images
                           if img.is_selected and img.show_in_editor and not img.is_locked
                           and img.image_data]
        multi_select = len(selected_images) > 1

        region = context.region
        v2d = region.view2d
        view_pixel_size = abs(v2d.region_to_view(1, 1)[0] - v2d.region_to_view(0, 0)[0])
        s_view = settings.gizmo_size * view_pixel_size
        hit_radius = max(9.0 * view_pixel_size, s_view * 0.4)

        def near(point):
            return ((point[0] - mouse_pos[0]) ** 2
                    + (point[1] - mouse_pos[1]) ** 2) <= hit_radius ** 2

        if multi_select:
            # Testa gizmos da bounding box coletiva
            data_list = []
            for img in selected_images:
                tex = get_cached_texture(img.image_data)
                w, h = (tex.texture.width, tex.texture.height) if (tex and tex.texture) else img.image_data.size
                if w > 0 and h > 0:
                    data_list.append((
                        img.location, img.scale_xy, img.scale_master,
                        img.shear_xy, img.rotation,
                        w, h
                    ))

            bbox = get_collective_bounding_box(data_list)
            if not bbox:
                return -1

            corners, _, rotate = collective_handle_layout(bbox, s_view)

            if settings.show_rotate_handles and near(rotate):
                return 8

            if settings.show_scale_handles:
                for i, p in enumerate(corners):
                    if near(p):
                        return i
            return -1

        # Seleção única
        if not (0 <= settings.active_image_index < len(settings.images)):
            return -1

        img = settings.images[settings.active_image_index]
        if (not img.is_selected or not img.show_in_editor or img.is_locked
                or not img.image_data):
            return -1

        tex_manager = get_cached_texture(img.image_data)
        w, h = (tex_manager.texture.width, tex_manager.texture.height) if (tex_manager and tex_manager.texture) else img.image_data.size
        if w <= 0 or h <= 0:
            return -1

        w = w * img.scale_xy[0] * img.scale_master
        h = h * img.scale_xy[1] * img.scale_master
        corners, edges, _, rotate = handle_layout(
            img.location, w, h, img.shear_xy, img.rotation, s_view)

        if settings.show_rotate_handles and near(rotate):
            return 8

        # Testa meios (Stretch/Shear)
        if settings.show_scale_handles:
            # Testa cantos (Scale Uniform)
            for i, p in enumerate(corners):
                if near(p):
                    return i
            for i, p in enumerate(edges):
                if near(p):
                    return i + 4

        return -1

    def _find_image_at_pos(self, context, mouse_pos):
        """
        Retorna (index, image_item) da imagem mais ao topo sob mouse_pos.
        Usa dimensões reais da GPUTexture para hitbox precisa.
        Retorna (None, None) se nada encontrado.
        """
        settings = get_settings(context)
        from ..utils.item_geometry import image_draw_indices, text_card_draw_indices
        sorted_indices = list(reversed(text_card_draw_indices(settings)))
        sorted_indices.extend(reversed(image_draw_indices(settings)))

        for idx in sorted_indices:
            img = settings.images[idx]
            if img.is_locked:
                continue
            if img.item_type == 'TEXT' and img.show_in_editor:
                from ..utils.item_geometry import item_bounds
                left, bottom, right, top = item_bounds(img)
                if left <= mouse_pos[0] <= right and bottom <= mouse_pos[1] <= top:
                    return idx, img
                continue
            if not img.show_in_editor or not img.image_data:
                continue

            tex_manager = get_cached_texture(img.image_data)
            w, h = (tex_manager.texture.width, tex_manager.texture.height) if (tex_manager and tex_manager.texture) else img.image_data.size
            if w <= 0 or h <= 0:
                continue

            # Desfaz rotação para testar hit num retângulo reto
            p_rel = rotate_point(mouse_pos, img.location, -img.rotation)
            dx = p_rel[0] - img.location[0]
            dy = p_rel[1] - img.location[1]

            shx, shy = img.shear_xy
            denom = (1.0 - shx * shy)
            if abs(denom) < 0.0001:
                denom = 0.0001

            dy_raw = (dy - dx * shy) / denom
            dx_raw = dx - dy_raw * shx

            w = w * img.scale_xy[0] * img.scale_master
            h = h * img.scale_xy[1] * img.scale_master

            if -w / 2 <= dx_raw <= w / 2 and -h / 2 <= dy_raw <= h / 2:
                return idx, img

        return None, None

    def _frame_hit(self, context, mouse_pos):
        from ..utils.gpu.gpu_frame import hit_test_frame
        from ..utils.gpu import visible_frames_in_draw_order, frame_has_content
        settings = get_settings(context)
        view = context.region.view2d
        a = view.region_to_view(0, 0)
        b = view.region_to_view(1, 0)
        pixel_size = abs(b[0] - a[0])
        for index, frame in reversed(visible_frames_in_draw_order(settings)):
            if frame.is_locked:
                continue
            part = hit_test_frame(frame, mouse_pos, pixel_size,
                                  allow_resize=not frame_has_content(settings, frame.frame_node_name))
            if part:
                return index, frame, part
        return None, None, None

    def _start_frame_drag(self, context, frame, part, mouse_pos):
        settings = get_settings(context)
        from ..utils.gpu import ensure_item_ids, frame_ancestors, frame_descendants
        ensure_item_ids(settings)
        self.drag_mode = 'FRAME_RESIZE' if part == 'RESIZE' else 'FRAME_MOVE'
        self.mouse_drag_started = False
        self.frame_target = frame
        self.frame_target_id = frame.item_id
        self.frame_start = (frame.location[0], frame.location[1],
                            frame.frame_width, frame.frame_height)
        self.init_mouse_view = mouse_pos
        self.last_mouse_pos = mouse_pos
        selected_frames = ([item for item in settings.images
                            if item.item_type in {'FRAME', 'IMAGE', 'TEXT'}
                            and item.is_selected and item.show_in_editor]
                           if self.drag_mode == 'FRAME_MOVE' else [])
        if frame not in selected_frames:
            selected_frames = [frame]
        selected_names = {item.frame_node_name for item in selected_frames
                          if item.item_type == 'FRAME'}
        roots = [item for item in selected_frames
                 if not any(parent.frame_node_name in selected_names
                            for parent in frame_ancestors(settings, item))]
        self.frame_drag_roots = [item.item_id for item in roots]
        moved = {item.item_id: item for root in roots
                 for item in ([root] + frame_descendants(settings, root.frame_node_name)
                              if root.item_type == 'FRAME' else [root])}
        self.frame_drag_names = {item.frame_node_name for item in moved.values()
                                 if item.item_type == 'FRAME'}
        self.frame_drag_old_parents = {root.parent_frame for root in roots if root.parent_frame}
        ancestors = {parent.item_id: parent for root in roots
                     for parent in frame_ancestors(settings, root)}
        self.frame_ancestor_starts = [(item.item_id, tuple(item.location),
                                       item.frame_width, item.frame_height)
                                      for item in ancestors.values()]
        self.frame_targets = [(item.item_id, tuple(item.location),
                               item.frame_width, item.frame_height) for item in moved.values()
                              if item.item_type == 'FRAME']
        self.frame_children = [(item.item_id, tuple(item.location)) for item in moved.values()
                               if item.item_type in {'IMAGE', 'TEXT'}]
        from ..utils.arrow_geometry import capture_selected_arrow_move
        self.arrow_move_snapshots = (capture_selected_arrow_move(settings, moved)
                                     if self.drag_mode == 'FRAME_MOVE' else [])

    def _resolve_drag_items(self, settings):
        """RNA collection elements can change slots when the UI list is reordered."""
        from ..utils.gpu import get_item_by_id
        if getattr(self, 'drag_target_id', None):
            self.drag_target = get_item_by_id(settings, self.drag_target_id)
        for target in getattr(self, 'multi_targets', []):
            target['img'] = get_item_by_id(settings, target['item_id'])
        if getattr(self, 'frame_target_id', None):
            self.frame_target = get_item_by_id(settings, self.frame_target_id)
        if getattr(self, 'text_target_id', None):
            self.text_target = get_item_by_id(settings, self.text_target_id)

    def _start_text_resize(self, card, mouse_pos):
        from ..utils.item_geometry import item_bounds
        from ..utils.gpu import ensure_item_ids, get_frame
        settings = get_settings(bpy.context)
        ensure_item_ids(settings)
        self.drag_mode = 'TEXT_RESIZE'
        self.text_target = card
        self.text_target_id = card.item_id
        self.text_start = (tuple(card.location), card.text_scale,
                           card.text_width, card.text_height, item_bounds(card))
        frame = get_frame(settings, card.parent_frame) if card.parent_frame else None
        self.text_frame_start = ((frame.item_id, tuple(frame.location),
                                  frame.frame_width, frame.frame_height) if frame else None)
        self.init_mouse_view = mouse_pos
        self.last_mouse_pos = mouse_pos

    def _snap_text_resize_edges(self, context, left, top, width, height, *, shift=False, ctrl=False):
        """Snap only the right and bottom edges moved by the resize handle."""
        settings = get_settings(context)
        settings.show_snap_viz_x = False
        settings.show_snap_viz_y = False
        if not ctrl:
            return width, height

        view = context.region.view2d
        pixel_size = abs(view.region_to_view(1, 0)[0]
                         - view.region_to_view(0, 0)[0])
        threshold = max(settings.snap_threshold * pixel_size * (0.5 if shift else 1.0), 1e-4)
        right, bottom = left + width, top - height
        best_x = best_y = threshold
        snapped_x = snapped_y = None

        if settings.snap_images:
            from ..utils.item_geometry import item_bounds
            from ..utils.gpu import frame_ancestors

            excluded = {self.text_target.item_id}
            for frame in frame_ancestors(settings, self.text_target):
                if frame.auto_resize:
                    excluded.add(frame.item_id)
            for other in settings.images:
                if other.item_id in excluded or not other.show_in_editor:
                    continue
                bounds = item_bounds(other)
                if not bounds:
                    continue
                x0, y0, x1, y1 = bounds
                for candidate in (x0, (x0 + x1) * 0.5, x1):
                    distance = abs(candidate - right)
                    if distance < best_x:
                        best_x, snapped_x = distance, candidate
                for candidate in (y0, (y0 + y1) * 0.5, y1):
                    distance = abs(candidate - bottom)
                    if distance < best_y:
                        best_y, snapped_y = distance, candidate

        if settings.snap_grid:
            step = max(1.0, float(settings.grid_size)) * (0.1 if shift else 1.0)
            if snapped_x is None:
                snapped_x = round(right / step) * step
            if snapped_y is None:
                snapped_y = round(bottom / step) * step

        if snapped_x is not None and snapped_x - left >= 100.0 * self.text_start[1]:
            right = snapped_x
            settings.snap_viz_x = right
            settings.show_snap_viz_x = True
        if snapped_y is not None and top - snapped_y >= 60.0 * self.text_start[1]:
            bottom = snapped_y
            settings.snap_viz_y = bottom
            settings.show_snap_viz_y = True
        return right - left, top - bottom

    def _snap_item_location(self, context, target_item, nx, ny, *, shift=False, ctrl=False):
        settings = get_settings(context)
        native_snap = context.tool_settings.use_snap_node
        should_snap = (native_snap and not ctrl) or (not native_snap and ctrl)

        settings.show_snap_viz_x = False
        settings.show_snap_viz_y = False

        if not should_snap or not target_item:
            return nx, ny

        view_pixel_size = 1.0
        try:
            if context.region and context.region.view2d:
                v2d = context.region.view2d
                p0 = v2d.region_to_view(0, 0)
                p1 = v2d.region_to_view(1, 0)
                view_pixel_size = abs(p1[0] - p0[0])
        except Exception:
            pass

        threshold = max(settings.snap_threshold * view_pixel_size, 1e-4)
        if shift:
            threshold *= 0.5

        from ..utils.item_geometry import item_bounds
        from ..utils.gpu import get_item_by_id
        snap_subjects = [target_item]
        if self.drag_mode == 'MOVE' and len(getattr(self, 'multi_targets', [])) > 1:
            snap_subjects = [get_item_by_id(settings, entry['item_id'])
                             for entry in self.multi_targets]
        elif self.drag_mode == 'FRAME_MOVE' and len(getattr(self, 'frame_targets', [])) > 1:
            snap_subjects = [get_item_by_id(settings, item_id)
                             for item_id, *_ in self.frame_targets]
        subject_bounds = [item_bounds(item) for item in snap_subjects if item]
        subject_bounds = [bound for bound in subject_bounds if bound]
        bounds = ((min(bound[0] for bound in subject_bounds),
                   min(bound[1] for bound in subject_bounds),
                   max(bound[2] for bound in subject_bounds),
                   max(bound[3] for bound in subject_bounds))
                  if subject_bounds else None)
        if bounds:
            min_x, min_y, max_x, max_y = bounds
            cur_x, cur_y = target_item.location
            dx_left = min_x - cur_x
            dx_center = (min_x + max_x) * 0.5 - cur_x
            dx_right = max_x - cur_x
            dy_bottom = min_y - cur_y
            dy_center = (min_y + max_y) * 0.5 - cur_y
            dy_top = max_y - cur_y

            cand_x = [nx + dx_left, nx + dx_center, nx + dx_right]
            cand_y = [ny + dy_bottom, ny + dy_center, ny + dy_top]
        else:
            cand_x = [nx]
            cand_y = [ny]

        snap_viz_x = None
        snap_offset_x = 0.0
        snap_viz_y = None
        snap_offset_y = 0.0

        if settings.snap_images:
            best_dx = threshold
            best_dy = threshold
            moving_ids = {t['item_id'] for t in getattr(self, 'multi_targets', [])}
            moving_ids.update(item_id for item_id, *_ in getattr(self, 'frame_targets', [])
                              if self.drag_mode == 'FRAME_MOVE')
            moving_ids.add(target_item.item_id)
            moving_frame_names = {item.frame_node_name for item in settings.images
                                  if item.item_id in moving_ids and item.item_type == 'FRAME'}
            moving_ids.update(item.item_id for item in settings.images
                              if item.parent_frame in moving_frame_names)
            # Auto-fit parents follow their children during the same gesture.
            moving_parent_names = {item.parent_frame for item in settings.images
                                   if item.item_id in moving_ids and item.parent_frame}
            moving_ids.update(item.item_id for item in settings.images
                              if item.item_type == 'FRAME' and item.auto_resize
                              and item.frame_node_name in moving_parent_names)

            for other in settings.images:
                if other.item_id in moving_ids or not other.show_in_editor:
                    continue
                o_bounds = item_bounds(other)
                if not o_bounds:
                    continue
                o_min_x, o_min_y, o_max_x, o_max_y = o_bounds
                ref_x = [o_min_x, (o_min_x + o_max_x) * 0.5, o_max_x]
                ref_y = [o_min_y, (o_min_y + o_max_y) * 0.5, o_max_y]

                for cx in cand_x:
                    for rx in ref_x:
                        diff = rx - cx
                        if abs(diff) < best_dx:
                            best_dx = abs(diff)
                            snap_offset_x = diff
                            snap_viz_x = rx

                for cy in cand_y:
                    for ry in ref_y:
                        diff = ry - cy
                        if abs(diff) < best_dy:
                            best_dy = abs(diff)
                            snap_offset_y = diff
                            snap_viz_y = ry

        if snap_viz_x is not None:
            nx += snap_offset_x
            settings.snap_viz_x = snap_viz_x
            settings.show_snap_viz_x = True
        elif settings.snap_grid:
            grid_step = max(1.0, float(settings.grid_size)) * (0.1 if shift else 1.0)
            nx = round(nx / grid_step) * grid_step
            settings.snap_viz_x = nx
            settings.show_snap_viz_x = True

        if snap_viz_y is not None:
            ny += snap_offset_y
            settings.snap_viz_y = snap_viz_y
            settings.show_snap_viz_y = True
        elif settings.snap_grid:
            grid_step = max(1.0, float(settings.grid_size)) * (0.1 if shift else 1.0)
            ny = round(ny / grid_step) * grid_step
            settings.snap_viz_y = ny
            settings.show_snap_viz_y = True

        return nx, ny

    # -----------------------------------------------------------------------
    # Drag update
    # -----------------------------------------------------------------------

    def _update_drag(self, context, mouse_x, mouse_y, shift=False, ctrl=False):
        """Atualiza a geometria do item em tempo real durante um gesto."""
        settings = get_settings(context)
        self._resolve_drag_items(settings)
        if (self.drag_mode in {'MOVE', 'FRAME_MOVE'}
                and not getattr(self, 'keyboard_transform', False)
                and not getattr(self, 'mouse_drag_started', False)
                and getattr(context, 'region', None) is not None):
            view = context.region.view2d
            p0 = view.view_to_region(*self.init_mouse_view, clip=False)
            p1 = view.view_to_region(mouse_x, mouse_y, clip=False)
            if (p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 < 9:
                return
            self.mouse_drag_started = True
        self.drop_view_location = (mouse_x, mouse_y)
        if self.drag_mode in {'MOVE', 'FRAME_MOVE'} and not getattr(self, 'f_is_held', False):
            from ..utils.gpu import (find_frame_at_location, get_item_by_id,
                                     release_guard_active)
            pixel_size = 1.0
            if getattr(context, 'region', None) and getattr(context.region, 'view2d', None):
                pixel_size = abs(context.region.view2d.region_to_view(1, 0)[0]
                                 - context.region.view2d.region_to_view(0, 0)[0])
            if self.drag_mode == 'FRAME_MOVE':
                moving = [get_item_by_id(settings, item_id)
                          for item_id in getattr(self, 'frame_drag_roots', [])]
            else:
                moving = [target['img'] for target in getattr(self, 'multi_targets', [])]
            released_here = any(release_guard_active(
                settings, item, self.drop_view_location, margin=10 * pixel_size)
                for item in moving if item)
            frame = None if released_here else find_frame_at_location(
                settings, self.drop_view_location, margin=10 * pixel_size,
                exclude_frame_names=(getattr(self, 'frame_drag_names', set())
                                     if self.drag_mode == 'FRAME_MOVE' else None))
            settings.drop_target_frame = frame.frame_node_name if frame else ''
        else:
            settings.drop_target_frame = ''

        if self.drag_mode == 'SELECT_BOX':
            settings.box_sel_end = (mouse_x, mouse_y)
            return

        if self.drag_mode == 'TEXT_RESIZE':
            self.last_mouse_pos = (mouse_x, mouse_y)
            location, start_scale, base_width, base_height, bounds = self.text_start
            left, _, _, top = bounds
            dx = mouse_x - self.init_mouse_view[0]
            dy = mouse_y - self.init_mouse_view[1]
            width = max(100.0 * start_scale, base_width * start_scale + dx)
            height = max(60.0 * start_scale, base_height * start_scale - dy)
            width, height = self._snap_text_resize_edges(
                context, left, top, width, height, shift=shift, ctrl=ctrl)
            from ..properties import suspend_frame_geometry_updates
            with suspend_frame_geometry_updates():
                self.text_target.text_width = width / start_scale
                self.text_target.text_height = height / start_scale
                self.text_target.location = (left + width * 0.5,
                                             top - height * 0.5)
            if self.text_target.parent_frame:
                from ..utils.gpu import update_frame_bounds
                update_frame_bounds(None, settings, self.text_target.parent_frame)
            return

        if self.drag_mode in {'FRAME_MOVE', 'FRAME_RESIZE'}:
            dx = mouse_x - self.init_mouse_view[0]
            dy = mouse_y - self.init_mouse_view[1]
            x, y, width, height = self.frame_start
            if self.drag_mode == 'FRAME_MOVE':
                from ..properties import suspend_frame_geometry_updates
                from ..utils.gpu import get_item_by_id
                with suspend_frame_geometry_updates():
                    nx, ny = self._snap_item_location(
                        context, self.frame_target, x + dx, y + dy, shift=shift, ctrl=ctrl)
                    final_dx = nx - x
                    final_dy = ny - y
                    for item_id, location, _, _ in self.frame_targets:
                        target = get_item_by_id(settings, item_id)
                        if target:
                            target.location = (location[0] + final_dx, location[1] + final_dy)
                    for item_id, location in self.frame_children:
                        child = get_item_by_id(settings, item_id)
                        if child:
                            child.location = (location[0] + final_dx, location[1] + final_dy)
                from ..utils.arrow_geometry import translate_selected_arrows
                translate_selected_arrows(self.arrow_move_snapshots, final_dx, final_dy)
                # The moved subtree keeps its own bounds; its stationary
                # ancestors must follow it while the mouse is still down.
                from ..utils.gpu import update_frame_bounds
                for name in getattr(self, 'frame_drag_old_parents', set()):
                    update_frame_bounds(None, settings, name)
            else:
                self.frame_target.frame_width = max(60, width + dx)
                self.frame_target.frame_height = max(60, height - dy)
            return

        if not self.drag_target:
            return

        multi_select = len(self.multi_targets) > 1

        if multi_select:
            clx = mouse_x - self.selection_pivot[0]
            cly = mouse_y - self.selection_pivot[1]
        else:
            dx = mouse_x - self.drag_target.location[0]
            dy = mouse_y - self.drag_target.location[1]
            curr_local = rotate_point((dx, dy), (0, 0), -self.drag_target.rotation)
            clx, cly   = curr_local

        tex_data = self.drag_target.image_data
        tex = get_cached_texture(tex_data) if tex_data else None
        w, h = (tex.texture.width, tex.texture.height) if (tex and tex.texture) else (tex_data.size if tex_data else (200, 200))
        half_w = w / 2
        half_h = h / 2

        if self.drag_mode == 'MOVE':
            total_dx = mouse_x - self.init_mouse_view[0]
            total_dy = mouse_y - self.init_mouse_view[1]
            total_dx = self._constrain_value(
                total_dx, 0.0, shift=shift, key='MOVE_X')
            total_dy = self._constrain_value(
                total_dy, 0.0, shift=shift, key='MOVE_Y')
            raw_nx = self.init_loc[0] + total_dx
            raw_ny = self.init_loc[1] + total_dy

            nx, ny = self._snap_item_location(
                context, self.drag_target, raw_nx, raw_ny, shift=shift, ctrl=ctrl)

            main_dx = nx - self.init_loc[0]
            main_dy = ny - self.init_loc[1]

            from ..properties import suspend_frame_geometry_updates
            with suspend_frame_geometry_updates():
                for item in self.multi_targets:
                    img = item['img']
                    img.location = (item['loc'][0] + main_dx,
                                    item['loc'][1] + main_dy)
            from ..utils.arrow_geometry import translate_selected_arrows
            translate_selected_arrows(self.arrow_move_snapshots, main_dx, main_dy)

            # Redimensionamento dinâmico em tempo real e auto-parenting enquanto arrasta
            if context.space_data and context.space_data.edit_tree:
                from ..utils.gpu import update_frame_bounds
                tree = context.space_data.edit_tree
                targets = [t['img'] for t in self.multi_targets] if self.multi_targets else ([self.drag_target] if self.drag_target else [])
                init_bounds = getattr(self, 'initial_frame_bounds', None)

                # Se a tecla F estiver pressionada/segurada, desanexa imagens do frame
                if getattr(self, 'f_is_held', False):
                    detached_any = False
                    for img in targets:
                        if img.parent_frame:
                            self.affected_frame_names.add(img.parent_frame)
                            img.parent_frame = ''
                            self.detached_in_gesture.add(img.item_id)
                            detached_any = True
                    if detached_any:
                        for fname in list(self.affected_frame_names):
                            update_frame_bounds(tree, settings, fname, initial_bounds=init_bounds)

                # 1. Atualiza bounds dos frames que contêm imagens em movimento
                for img in targets:
                    if img.parent_frame:
                        self.affected_frame_names.add(img.parent_frame)
                        update_frame_bounds(tree, settings, img.parent_frame, initial_bounds=init_bounds)

                # 2. Se a tecla F não estiver pressionada, permite anexar imagens ao cruzar frames
                if (not getattr(self, 'f_is_held', False) and not released_here
                        and len(targets) == 1):
                    unattached = [img for img in targets if not img.parent_frame and img.item_id not in getattr(self, 'detached_in_gesture', set())]
                    if unattached:
                        from ..utils.gpu import find_frame_at_location, attach_items_to_frame
                        hovered_frame = find_frame_at_location(
                            settings, (mouse_x, mouse_y), margin=10 * pixel_size)
                        if hovered_frame:
                            newly_parented = attach_items_to_frame(
                                tree, settings, unattached, hovered_frame.frame_node_name,
                                initial_bounds=init_bounds)
                        else:
                            newly_parented = set()
                        for fname in newly_parented:
                            self.affected_frame_names.add(fname)
                            update_frame_bounds(tree, settings, fname, initial_bounds=init_bounds)

        elif self.drag_mode == 'SCALE_U':
            dist_init = (self.init_mouse_local[0]**2 + self.init_mouse_local[1]**2)**0.5
            dist_curr = (clx**2 + cly**2)**0.5
            if getattr(self, 'keyboard_transform', False) and dist_init < 10.0:
                reference = max(50.0, max(w * self.init_scale[0], h * self.init_scale[1])
                                * self.init_scale_master * 0.5)
                raw_factor = 1.0 + (mouse_x - self.init_mouse_view[0]) / reference
            elif dist_init > 0:
                raw_factor = dist_curr / dist_init
            else:
                raw_factor = None
            if raw_factor is not None:
                scale_factor = self._constrain_value(
                    raw_factor, 1.0, shift=shift, ctrl=ctrl)
                for target in self.multi_targets:
                    item = target['img']
                    item.scale_master = max(0.001, target['scale_master'] * scale_factor)
                    if len(self.multi_targets) > 1:
                        item.location[0] = self.selection_pivot[0] + (target['loc'][0] - self.selection_pivot[0]) * scale_factor
                        item.location[1] = self.selection_pivot[1] + (target['loc'][1] - self.selection_pivot[1]) * scale_factor

        elif self.drag_mode == 'SCALE_X':
            raw = (abs(clx) / half_w) / self.drag_target.scale_master
            self.drag_target.scale_xy[0] = max(0.001, self._constrain_value(
                raw, self.init_scale[0], shift=shift, ctrl=ctrl))

        elif self.drag_mode == 'SCALE_Y':
            raw = (abs(cly) / half_h) / self.drag_target.scale_master
            self.drag_target.scale_xy[1] = max(0.001, self._constrain_value(
                raw, self.init_scale[1], shift=shift, ctrl=ctrl))

        elif self.drag_mode == 'SHEAR_X':
            if abs(cly) > 10:
                self.drag_target.shear_xy[0] = self._constrain_value(
                    clx / cly, self.init_shear[0], shift=shift, ctrl=ctrl)

        elif self.drag_mode == 'SHEAR_Y':
            if abs(clx) > 10:
                self.drag_target.shear_xy[1] = self._constrain_value(
                    cly / clx, self.init_shear[1], shift=shift, ctrl=ctrl)

        elif self.drag_mode == 'ROTATE':
            pivot      = self.selection_pivot if multi_select else self.drag_target.location
            curr_angle = self._get_angle(pivot, (mouse_x, mouse_y))
            if getattr(self, 'keyboard_rotation_linear', False):
                angle_change = (mouse_x - self.last_mouse_pos[0]) * 0.5
            else:
                angle_change = (curr_angle - self.rotation_last_angle + 180.0) % 360.0 - 180.0
            self.rotation_last_angle = curr_angle
            self.rotation_total_delta += angle_change * (0.1 if shift else 1.0)
            rot_delta = _apply_rotation_delta(self.rotation_total_delta, ctrl, shift)

            for target in self.multi_targets:
                item = target['img']
                item.rotation = target['rot'] + rot_delta
                if len(self.multi_targets) > 1:
                    item.location[0], item.location[1] = rotate_point(
                        target['loc'], self.selection_pivot, rot_delta
                    )

        self.last_mouse_pos = (mouse_x, mouse_y)

    # -----------------------------------------------------------------------
    # Drag stop / cancel
    # -----------------------------------------------------------------------

    def _start_box_selection(self, context, event, mouse_x, mouse_y, native=False):
        settings = get_settings(context)
        self.drag_mode = 'SELECT_BOX'
        self.box_select_native = native
        self.box_additive = event.shift
        self.box_region_start = (event.mouse_region_x, event.mouse_region_y)
        self.box_region_end = self.box_region_start
        settings.box_sel_start = (mouse_x, mouse_y)
        settings.box_sel_end = (mouse_x, mouse_y)
        settings.show_box_sel = True
        context.area.tag_redraw()

    def _stop_drag(self, context):
        """Finaliza o drag e registra um passo de undo granular."""
        settings = get_settings(context)
        self._resolve_drag_items(settings)

        if self.drag_mode == 'TEXT_RESIZE':
            self.drag_mode = 'NONE'
            self.text_target = None
            self.text_target_id = None
            self.text_frame_start = None
            context.area.tag_redraw()
            return

        if self.drag_mode in {'FRAME_MOVE', 'FRAME_RESIZE'}:
            from ..utils.gpu import (attach_items_to_frame, get_frame, get_item_by_id,
                                     update_frame_bounds, sync_kanvas_frames)
            tree = getattr(context.space_data, 'edit_tree', None) if context.space_data else None
            if self.drag_mode == 'FRAME_RESIZE' and self.frame_target:
                from ..utils.gpu import frame_has_content
                self.frame_target.auto_resize = frame_has_content(
                    settings, self.frame_target.frame_node_name)
            if self.drag_mode == 'FRAME_MOVE':
                roots = [get_item_by_id(settings, item_id)
                         for item_id in getattr(self, 'frame_drag_roots', [])]
                target = get_frame(settings, settings.drop_target_frame) if settings.drop_target_frame else None
                if target:
                    attach_items_to_frame(tree, settings, [item for item in roots if item],
                                          target.frame_node_name)
            for name in getattr(self, 'frame_drag_old_parents', set()):
                update_frame_bounds(tree, settings, name)
            if self.frame_target and self.frame_target.parent_frame:
                update_frame_bounds(tree, settings, self.frame_target.parent_frame)
            if tree:
                sync_kanvas_frames(tree, settings)
            settings.drop_target_frame = ''
            settings.show_snap_viz_x = False
            settings.show_snap_viz_y = False
            self.drag_mode = 'NONE'
            self.frame_target = None
            context.area.tag_redraw()
            return
        if self.drag_mode == 'SELECT_BOX':
            self._perform_box_selection(context)
            settings.show_box_sel = False
            self.drag_mode = 'NONE'
            self.box_select_native = False
            # The finite operator itself owns the undo step on FINISHED.
            context.area.tag_redraw()
            return

        dragged_imgs = [target['img'] for target in self.multi_targets] if self.multi_targets else ([self.drag_target] if self.drag_target else [])
        completed_mode = self.drag_mode

        self.drag_mode    = 'NONE'
        self.drag_target  = None
        self.active_gizmo = -1
        settings.show_snap_viz_x = False
        settings.show_snap_viz_y = False

        if context.space_data and context.space_data.edit_tree:
            from ..utils.gpu import (attach_items_to_frame, get_frame,
                                     update_frame_bounds, sync_kanvas_frames)
            tree = context.space_data.edit_tree
            detached = getattr(self, 'detached_in_gesture', set())
            eligible_for_parenting = [img for img in dragged_imgs if img.item_id not in detached]
            if completed_mode == 'MOVE' and eligible_for_parenting:
                hovered_frame = get_frame(settings, settings.drop_target_frame)
                if hovered_frame:
                    affected = attach_items_to_frame(
                        tree, settings, eligible_for_parenting,
                        hovered_frame.frame_node_name,
                        initial_bounds=getattr(self, 'initial_frame_bounds', None))
                else:
                    affected = set()
                for fname in affected:
                    self.affected_frame_names.add(fname)
            for fname in getattr(self, 'affected_frame_names', set()):
                update_frame_bounds(tree, settings, fname, initial_bounds=getattr(self, 'initial_frame_bounds', None))
            sync_kanvas_frames(tree, settings)

        self.detached_in_gesture = set()
        self.f_is_held = False
        settings.f_is_held = False
        self.affected_frame_names = set()
        self.initial_frame_bounds = {}
        self.drop_view_location = None
        settings.drop_target_frame = ''
        context.area.tag_redraw()


    def _perform_box_selection(self, context):
        """Select images whose visible area intersects the box."""
        settings = get_settings(context)
        start = settings.box_sel_start
        end   = settings.box_sel_end

        min_x, max_x = sorted([start[0], end[0]])
        min_y, max_y = sorted([start[1], end[1]])

        if (abs(self.box_region_end[0] - self.box_region_start[0]) < 3
                or abs(self.box_region_end[1] - self.box_region_start[1]) < 3):
            return False

        changed = False
        if not self.box_additive:
            changed = _clear_image_selection(settings)
            changed = _clear_arrow_selection(settings) or changed

        for idx, img in enumerate(settings.images):
            if (not img.show_in_editor or img.is_locked
                    or img.item_type not in {'IMAGE', 'TEXT'}):
                continue
            if img.item_type == 'TEXT':
                from ..utils.item_geometry import item_bounds
                left, bottom, right, top = item_bounds(img)
                intersects = (right >= min_x and left <= max_x
                              and top >= min_y and bottom <= max_y)
            else:
                intersects = bool(img.image_data) and image_intersects_view(
                    img, (min_x, min_y, max_x, max_y))
            if intersects:
                if not img.is_selected:
                    img.is_selected = True
                    changed = True
                _set_canvas_active(settings, image_index=idx)
        for idx, frame in enumerate(settings.images):
            if (frame.item_type != 'FRAME' or not frame.show_in_editor
                    or frame.is_locked):
                continue
            header_x = frame.location[0] + frame.frame_width / 2
            header_y = frame.location[1]
            if min_x <= header_x <= max_x and min_y <= header_y <= max_y:
                frame.is_selected = True
                _set_canvas_active(settings, image_index=idx)
                changed = True
        from ..utils.arrow_geometry import curve_intersects_rect
        for idx, arrow in enumerate(settings.arrows):
            if arrow.is_locked or not curve_intersects_rect(
                    settings, arrow, (min_x, min_y, max_x, max_y)):
                continue
            if not arrow.is_selected:
                arrow.is_selected = True
                changed = True
            if settings.active_image_index < 0:
                _set_canvas_active(settings, arrow_index=idx)
        return changed

    def _cancel_drag(self, context):
        """Cancela o drag atual e restaura o estado inicial (sem criar undo step)."""
        settings = get_settings(context)
        if self.drag_mode == 'TEXT_SCROLL':
            self.drag_target.text_scroll = self.scroll_start
            self.drag_mode = 'NONE'
            context.area.tag_redraw()
            return
        self._resolve_drag_items(settings)
        settings.show_box_sel = False
        settings.drop_target_frame = ''

        if self.drag_mode == 'TEXT_RESIZE':
            location, scale, width, height, _ = self.text_start
            from ..properties import suspend_frame_geometry_updates
            with suspend_frame_geometry_updates():
                self.text_target.text_width = width
                self.text_target.text_height = height
                self.text_target.text_scale = scale
                self.text_target.location = location
                if self.text_frame_start:
                    from ..utils.gpu import get_item_by_id
                    item_id, frame_location, frame_width, frame_height = self.text_frame_start
                    frame = get_item_by_id(settings, item_id)
                    if frame:
                        frame.location = frame_location
                        frame.frame_width = frame_width
                        frame.frame_height = frame_height
            self.text_target = None
            self.text_target_id = None
            self.text_frame_start = None
            self.drag_mode = 'NONE'
            settings.show_snap_viz_x = False
            settings.show_snap_viz_y = False
            context.area.tag_redraw()
            return

        if self.drag_mode == 'SELECT_BOX':
            self.drag_mode = 'NONE'
            self.box_select_native = False
            context.area.tag_redraw()
            return

        if self.drag_mode in {'FRAME_MOVE', 'FRAME_RESIZE'}:
            x, y, width, height = self.frame_start
            from ..properties import suspend_frame_geometry_updates
            from ..utils.gpu import get_item_by_id
            with suspend_frame_geometry_updates():
                for item_id, location, start_width, start_height in self.frame_targets:
                    target = get_item_by_id(settings, item_id)
                    if target:
                        target.location = location
                        target.frame_width = start_width
                        target.frame_height = start_height
                for item_id, location in self.frame_children:
                    child = get_item_by_id(settings, item_id)
                    if child:
                        child.location = location
                for item_id, location, start_width, start_height in getattr(
                        self, 'frame_ancestor_starts', []):
                    ancestor = get_item_by_id(settings, item_id)
                    if ancestor:
                        ancestor.location = location
                        ancestor.frame_width = start_width
                        ancestor.frame_height = start_height
            from ..utils.arrow_geometry import restore_selected_arrows
            restore_selected_arrows(getattr(self, 'arrow_move_snapshots', []))
            self.frame_target = None
            self.drag_mode = 'NONE'
            context.area.tag_redraw()
            return

        for target in self.multi_targets:
            img = target['img']
            img.location = target['loc']
            img.scale_xy = target['scale_xy']
            img.scale_master = target['scale_master']
            img.rotation = target['rot']
            if 'orig_parent' in target:
                img.parent_frame = target['orig_parent']

        from ..utils.arrow_geometry import restore_selected_arrows
        restore_selected_arrows(getattr(self, 'arrow_move_snapshots', []))

        if self.drag_target:
            self.drag_target.shear_xy = list(self.init_shear)
            if hasattr(self, 'init_loc'):
                self.drag_target.location = self.init_loc

        if context.space_data and context.space_data.edit_tree:
            from ..utils.gpu import update_frame_bounds, sync_kanvas_frames
            tree = context.space_data.edit_tree
            for fname in getattr(self, 'affected_frame_names', set()):
                update_frame_bounds(tree, settings, fname)
            sync_kanvas_frames(tree, settings)

        self.detached_in_gesture = set()
        self.f_is_held = False
        settings.f_is_held = False
        self.affected_frame_names = set()
        self.initial_frame_bounds = {}
        self.drag_mode = 'NONE'
        self.drag_target = None
        settings.show_snap_viz_x = False
        settings.show_snap_viz_y = False
        context.area.tag_redraw()

class KANVAS_OT_Interact(KanvasInteractionHelpers, bpy.types.Operator):
    """Handle one Kanvas input gesture; never run while the editor is idle."""
    bl_idname = "kanvas.interact"
    bl_label = "Kanvas Interaction"
    bl_description = 'Handle the active Kanvas canvas gesture or keyboard shortcut'
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.StringProperty(default='CLICK')

    @classmethod
    def poll(cls, context):
        space = getattr(context, 'space_data', None)
        tree = getattr(space, 'edit_tree', None) if space else None
        return (space is not None and space.type == 'NODE_EDITOR'
                and tree is not None and tree.bl_idname == 'KanvasNodeTree'
                and getattr(context, 'region', None) is not None
                and context.region.type == 'WINDOW'
                and not any(item.mask_editing or item.markup_editing
                            for item in tree.kanvas_settings.images))

    def _end(self, context, result):
        _active_modal_areas.discard(getattr(self, '_area_key', None))
        settings = get_settings(context)
        if settings:
            settings.is_modal_running = bool(_active_modal_areas)
            settings.show_box_sel = False
            settings.show_snap_viz_x = False
            settings.show_snap_viz_y = False
            settings.drop_target_frame = ''
        if context.area:
            context.area.tag_redraw()
        if result == {'FINISHED'} and getattr(self, '_undo_snapshot', None) == _undo_content_signature(settings):
            return {'CANCELLED'}
        return result

    def _begin_gesture(self, context):
        self._area_key = (context.window.as_pointer(), context.area.as_pointer())
        _active_modal_areas.add(self._area_key)
        get_settings(context).is_modal_running = True
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _update_text_scroll(self, context, region_y):
        from ..utils.gpu.gpu_text import _scroll_layout, _scrollbar_geometry
        card = self.drag_target
        layout = _scroll_layout(card, context.region)
        geometry = _scrollbar_geometry(layout, card)
        if geometry is None:
            return
        track, thumb = geometry
        travel = (track[3] - track[1]) - (thumb[3] - thumb[1])
        if travel > 0:
            fraction = max(0.0, min(1.0,
                        (track[3] - region_y - self.scroll_grab_offset) / travel))
            card.text_scroll = fraction * layout['max_scroll']
            context.area.tag_redraw()

    def _wheel_scroll_card(self, context, event, settings):
        """Plain wheel: scroll the text card under the pointer when allowed."""
        prefs = get_prefs()
        mode = getattr(prefs, 'card_wheel_scroll', 'SELECTED') if prefs else 'SELECTED'
        if mode == 'OFF':
            return {'PASS_THROUGH'}
        if settings.canvas_mode == 'MOVE':
            mode = 'HOVER'   # nothing can be selected in Move mode
        mouse = context.region.view2d.region_to_view(
            event.mouse_region_x, event.mouse_region_y)
        from ..utils.item_geometry import item_bounds, text_card_draw_indices
        for index in reversed(text_card_draw_indices(settings)):
            card = settings.images[index]
            if card.is_locked:
                continue
            left, bottom, right, top = item_bounds(card)
            if not (left <= mouse[0] <= right and bottom <= mouse[1] <= top):
                continue
            if mode == 'SELECTED' and not card.is_selected:
                return {'PASS_THROUGH'}
            from ..utils.gpu.gpu_text import wheel_scroll_card
            direction = 1 if event.type == 'WHEELUPMOUSE' else -1
            if wheel_scroll_card(card, context.region, direction):
                context.area.tag_redraw()
                return {'CANCELLED'}
            return {'PASS_THROUGH'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if not _event_in_canvas(context, event):
            return {'PASS_THROUGH'}
        settings = get_settings(context)
        if settings.batch_loading:
            return {'PASS_THROUGH'}
        if self.action == 'WHEEL' and not (event.ctrl or event.shift or event.alt):
            # Checked first: every zoom notch passes through here.
            return self._wheel_scroll_card(context, event, settings)
        if self.action == 'CLICK':
            from .ops_focus import hit_recenter_prompt
            position = (event.mouse_region_x, event.mouse_region_y)
            if hit_recenter_prompt(settings, context.area, context.region, position):
                _box_armed_areas.discard((context.window.as_pointer(),
                                          context.area.as_pointer()))
                bpy.ops.kanvas.recenter()
                return {'CANCELLED'}
        if self.action == 'TOGGLE_MODE':
            settings.canvas_mode = 'EDIT' if settings.canvas_mode == 'MOVE' else 'MOVE'
            context.area.tag_redraw()
            return {'CANCELLED'}
        if self.action == 'CLICK' and event.value == 'PRESS':
            from ..utils.gpu.gpu_mode_switch import hit_mode_switch
            clicked_mode = hit_mode_switch(
                context.area, context.region,
                (event.mouse_region_x, event.mouse_region_y))
            if clicked_mode:
                settings.canvas_mode = clicked_mode
                context.area.tag_redraw()
                return {'CANCELLED'}
        if self.action == 'CLICK' and settings.canvas_mode == 'MOVE':
            # Move mode: the left button behaves like the middle button.
            if event.value == 'PRESS':
                bpy.ops.kanvas.hand_pan('INVOKE_DEFAULT')
            # Handled either way: the press must never reach Blender's own select.
            return {'CANCELLED'}
        from ..utils.gpu import ensure_item_ids
        ensure_item_ids(settings)
        prefs = get_prefs()
        if not prefs:
            return {'PASS_THROUGH'}

        self.drag_target = None
        self.drag_target_id = None
        self.frame_target = None
        self.frame_target_id = None
        self.text_target_id = None
        self.drag_mode = 'NONE'
        self.keyboard_transform = False
        self.box_select_native = False
        self.box_additive = False
        self.active_gizmo = -1
        self.multi_targets = []
        self.box_region_start = (0, 0)
        self.box_region_end = (0, 0)
        self.pending_region_start = (0, 0)
        self.pending_view_start = (0, 0)
        _sync_modifiers(settings, event)
        self._undo_snapshot = (_undo_content_signature(settings)
                               if self.action in {'CLICK', 'MOVE', 'ROTATE', 'SCALE', 'DUPLICATE'}
                               else None)
        if self.action == 'MODIFIER':
            context.area.tag_redraw()
            return {'CANCELLED', 'PASS_THROUGH'}
        mouse = context.region.view2d.region_to_view(
            event.mouse_region_x, event.mouse_region_y)

        if self.action == 'BOX':
            area_key = (context.window.as_pointer(), context.area.as_pointer())
            if area_key in _box_armed_areas:
                _box_armed_areas.discard(area_key)
            else:
                _box_armed_areas.add(area_key)
            return {'CANCELLED'}

        if self.action == 'CANCEL_BOX':
            area_key = (context.window.as_pointer(), context.area.as_pointer())
            if area_key in _box_armed_areas:
                _box_armed_areas.discard(area_key)
                return {'CANCELLED'}
            return {'PASS_THROUGH'}

        if self.action in {'SELECT_ALL', 'SELECT_INVERT'}:
            if _select_canvas_items(settings, invert=self.action == 'SELECT_INVERT'):
                context.area.tag_redraw()
            return {'CANCELLED'}

        if self.action == 'CONTEXT':
            idx, img = self._find_image_at_pos(context, mouse)
            if img is None:
                return {'PASS_THROUGH'}
            if not img.is_selected:
                _clear_image_selection(settings)
                img.is_selected = True
            settings.active_image_index = idx
            bpy.ops.wm.call_menu(name='KANVAS_MT_context_menu')
            return {'CANCELLED'}

        if self.action == 'WHEEL':
            delta = 1 if event.type == 'WHEELUPMOUSE' else -1
            _, hit = self._find_image_at_pos(context, mouse)
            idx = settings.active_image_index
            active = settings.images[idx] if 0 <= idx < len(settings.images) else None
            if _modifier_held(event, prefs.wheel_opacity_mod):
                target = hit or active
                if target:
                    value = max(0.0, min(1.0, target.opacity + 0.05 * delta))
                    if value == target.opacity:
                        return {'CANCELLED'}
                    target.opacity = value
            elif _modifier_held(event, prefs.wheel_scale_mod):
                target = active
                if target:
                    value = max(0.001, target.scale_master * (1.1 if delta > 0 else 0.9))
                    if value == target.scale_master:
                        return {'CANCELLED'}
                    target.scale_master = value
            elif _modifier_held(event, prefs.wheel_layer_mod):
                target = hit
                if target:
                    target.z_index += delta
            else:
                return {'PASS_THROUGH'}
            if target is None:
                return {'PASS_THROUGH'}
            context.area.tag_redraw()
            return {'FINISHED'}

        if self.action != 'CLICK':
            idx = settings.active_image_index
            img = settings.images[idx] if 0 <= idx < len(settings.images) else None
            if img and img.is_locked:
                img = None
            if self.action == 'FOCUS':
                bpy.ops.kanvas.focus_selection()
                return {'CANCELLED'}
            if self.action == 'MASK':
                if bpy.ops.kanvas.paint_image_mask.poll():
                    bpy.ops.kanvas.paint_image_mask('INVOKE_DEFAULT')
                    return {'CANCELLED'}
                self.report({'INFO'}, 'Select an image to edit its mask')
                return {'CANCELLED'}
            if self.action == 'COLOR':
                if bpy.ops.kanvas.edit_color_markup.poll():
                    bpy.ops.kanvas.edit_color_markup('INVOKE_DEFAULT')
                    return {'CANCELLED'}
                return {'PASS_THROUGH'}
            if self.action == 'RENAME':
                if bpy.ops.kanvas.rename_item.poll():
                    bpy.ops.kanvas.rename_item('INVOKE_DEFAULT')
                    return {'CANCELLED'}
                return {'PASS_THROUGH'}
            if self.action in {'MOVE', 'ROTATE', 'SCALE'}:
                selected = [item for item in settings.images
                            if item.is_selected and item.show_in_editor and not item.is_locked
                            and ((item.item_type == 'IMAGE' and item.image_data)
                                 or (self.action == 'MOVE' and item.item_type == 'TEXT'))]
                if self.action == 'MOVE' and img and img.item_type == 'FRAME' and img.is_selected:
                    self.keyboard_transform = True
                    self._start_frame_drag(context, img, 'MOVE', mouse)
                    return self._begin_gesture(context)
                if not selected:
                    return {'PASS_THROUGH'}
                target = img if img in selected else selected[0]
                self.keyboard_transform = True
                mode = {'MOVE': 'MOVE', 'ROTATE': 'ROTATE', 'SCALE': 'SCALE_U'}[self.action]
                self.start_drag(context, target, mode, mouse)
                return self._begin_gesture(context)
            if self.action == 'F_PRESS':
                settings.f_is_held = True
                return {'CANCELLED'}
            if self.action == 'F_RELEASE':
                settings.f_is_held = False
                return {'CANCELLED'}
            if self.action == 'CREATE_FRAME':
                bpy.ops.kanvas.create_frame('INVOKE_DEFAULT')
                return {'CANCELLED'}
            if self.action == 'PACK':
                if sum(bool(i.is_selected and i.image_data) for i in settings.images) > 1:
                    bpy.ops.kanvas.pack_images()
                    return {'CANCELLED'}
            elif self.action == 'DELETE':
                has_selected = any(i.is_selected and not i.is_locked for i in settings.images)
                has_arrows = any(a.is_selected and not a.is_locked for a in settings.arrows)
                has_active = (0 <= settings.active_image_index < len(settings.images)
                              and not settings.images[settings.active_image_index].is_locked)
                if has_selected or has_arrows or has_active:
                    bpy.ops.kanvas.remove_image('INVOKE_DEFAULT', index=-1)
                    return {'CANCELLED'}
                if (0 <= settings.active_arrow_index < len(settings.arrows)
                        and not settings.arrows[settings.active_arrow_index].is_locked):
                    bpy.ops.kanvas.remove_arrow()
                    return {'CANCELLED'}
            elif self.action == 'DUPLICATE':
                if img is None:
                    selected = [i for i in settings.images
                                if i.is_selected and not i.is_locked and i.item_type != 'FRAME']
                    if selected:
                        img = selected[0]
                        settings.active_image_index = [i for i in settings.images].index(img)
                if not img or img.item_type == 'FRAME':
                    return {'PASS_THROUGH'}

                # Run the same duplication logic inside this gesture so
                # Shift+D plus its move produces a single undo step.
                from .ops_image import KANVAS_OT_DuplicateImage
                if KANVAS_OT_DuplicateImage.execute(self, context) != {'FINISHED'}:
                    return {'CANCELLED'}
                idx = settings.active_image_index
                if 0 <= idx < len(settings.images):
                    dup_item = settings.images[idx]
                    for item in settings.images:
                        item.is_selected = (item == dup_item)
                    self.keyboard_transform = True
                    self.start_drag(context, dup_item, 'MOVE', mouse)
                    return self._begin_gesture(context)
            elif self.action == 'DETACH':
                bpy.ops.kanvas.detach_from_frame()
                context.area.tag_redraw()
                return {'CANCELLED'}
            elif img and self.action == 'RESET_MOVE':
                if tuple(img.location) == (0.0, 0.0):
                    return {'CANCELLED'}
                img.location = (0, 0)
                context.area.tag_redraw()
                return {'FINISHED'}
            elif img and self.action == 'RESET_SCALE':
                if (tuple(img.scale_xy) == (1.0, 1.0) and img.scale_master == 1.0
                        and tuple(img.shear_xy) == (0.0, 0.0)):
                    return {'CANCELLED'}
                img.scale_xy = (1.0, 1.0)
                img.scale_master = 1.0
                img.shear_xy = (0.0, 0.0)
                context.area.tag_redraw()
                return {'FINISHED'}
            elif img and self.action == 'RESET_ROTATE':
                if img.rotation == 0.0:
                    return {'CANCELLED'}
                img.rotation = 0.0
                context.area.tag_redraw()
                return {'FINISHED'}
            return {'PASS_THROUGH'}

        area_key = (context.window.as_pointer(), context.area.as_pointer())
        if area_key in _box_armed_areas:
            _box_armed_areas.discard(area_key)
            self._start_box_selection(context, event, *mouse, native=True)
            return self._begin_gesture(context)

        from ..utils.arrow_geometry import hit_arrow
        view = context.region.view2d
        pixel_size = abs(view.region_to_view(1, 0)[0]
                         - view.region_to_view(0, 0)[0])
        arrow_index, arrow_part = hit_arrow(settings, mouse, pixel_size)
        if arrow_index is not None:
            arrow = settings.arrows[arrow_index]
            if event.shift:
                arrow.is_selected = not arrow.is_selected
                if arrow.is_selected:
                    _set_canvas_active(settings, arrow_index=arrow_index)
                else:
                    next_arrow = next((i for i, item in enumerate(settings.arrows)
                                       if item.is_selected), -1)
                    next_image = next((i for i, item in enumerate(settings.images)
                                       if item.is_selected), -1)
                    _set_canvas_active(settings, image_index=next_image if next_arrow < 0 else -1,
                                       arrow_index=next_arrow)
                context.area.tag_redraw()
                return {'CANCELLED'}
            if not arrow.is_selected:
                _clear_image_selection(settings)
                _clear_arrow_selection(settings)
            arrow.is_selected = True
            _set_canvas_active(settings, arrow_index=arrow_index)
            bpy.ops.kanvas.drag_arrow('INVOKE_DEFAULT', arrow_index=arrow_index,
                                     part=arrow_part)
            return {'CANCELLED'}

        frame_idx, frame, frame_part = self._frame_hit(context, mouse)
        idx, img = self._find_image_at_pos(context, mouse)
        if img and img.item_type == 'TEXT' and img.text_compare \
                and not (event.shift or event.ctrl or event.alt):
            from ..utils.gpu.gpu_compare import (DIVIDER_GRAB_PIXELS, hit_compare_button,
                                                 hit_compare_divider, next_mode)
            from ..utils.gpu.gpu_text import _region_bounds
            x0, y0, x1, y1 = _region_bounds(img, context.region.view2d)
            card_bounds = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            position = (event.mouse_region_x, event.mouse_region_y)
            part = hit_compare_button(img, card_bounds, position)
            if part is None and hit_compare_divider(img, card_bounds, position, DIVIDER_GRAB_PIXELS):
                part = 'DIVIDER'
            if part:
                _clear_image_selection(settings)
                _clear_arrow_selection(settings)
                img.is_selected = True
                _set_canvas_active(settings, image_index=idx)
                if part == 'MODE':
                    img.compare_mode = next_mode(img.compare_mode)
                elif part == 'DIVIDER':
                    bpy.ops.kanvas.drag_compare_divider('INVOKE_DEFAULT', item_id=img.item_id)
                else:
                    bpy.ops.kanvas.pick_compare_side('INVOKE_DEFAULT', item_id=img.item_id, side=part)
                context.area.tag_redraw()
                return {'CANCELLED'}
        if img and img.item_type == 'TEXT' and not img.text_compare \
                and not (event.shift or event.ctrl or event.alt) \
                and getattr(prefs, 'show_text_edit_button', True):
            from ..utils.gpu.gpu_text import hit_test_text_edit_button
            if hit_test_text_edit_button(img, context.region,
                                         (event.mouse_region_x, event.mouse_region_y)):
                _clear_image_selection(settings)
                _clear_arrow_selection(settings)
                img.is_selected = True
                _set_canvas_active(settings, image_index=idx)
                bpy.ops.kanvas.edit_text_popup('INVOKE_DEFAULT', item_id=img.item_id)
                context.area.tag_redraw()
                return {'CANCELLED'}
        if img and img.item_type == 'TEXT' and not (event.shift or event.ctrl or event.alt):
            from ..utils.gpu.gpu_text import hit_test_text_scrollbar
            geometry = hit_test_text_scrollbar(
                img, context.region, (event.mouse_region_x, event.mouse_region_y))
            if geometry:
                track, thumb = geometry
                if not img.is_selected:
                    _clear_image_selection(settings)
                    _clear_arrow_selection(settings)
                img.is_selected = True
                _set_canvas_active(settings, image_index=idx)
                self.drag_target = img
                self.drag_target_id = img.item_id
                self.drag_mode = 'TEXT_SCROLL'
                self.scroll_start = img.text_scroll
                self.scroll_grab_offset = (thumb[3] - event.mouse_region_y
                                           if thumb[1] <= event.mouse_region_y <= thumb[3]
                                           else (thumb[3] - thumb[1]) * 0.5)
                self._update_text_scroll(context, event.mouse_region_y)
                return self._begin_gesture(context)
        gizmo_idx = self._get_gizmo_under_mouse(context, mouse)
        if gizmo_idx != -1:
            active_idx = settings.active_image_index
            if not (0 <= active_idx < len(settings.images)):
                return {'PASS_THROUGH'}
            active = settings.images[active_idx]
            if img is None or img.item_id == active.item_id:
                modifier = _modifier_held(event, prefs.key_shear_mod)
                mode = ('SCALE_U' if gizmo_idx <= 3 else
                        ('SCALE_X' if not modifier else 'SHEAR_Y') if gizmo_idx in {5, 7} else
                        ('SCALE_Y' if not modifier else 'SHEAR_X') if gizmo_idx in {4, 6} else
                        'ROTATE')
                self.start_drag(context, active, mode, mouse)
                return self._begin_gesture(context)

        from ..utils.gpu.gpu_text import hit_test_text_resize
        view = context.region.view2d
        pixel_size = abs(view.region_to_view(1, 0)[0] - view.region_to_view(0, 0)[0])
        from ..utils.item_geometry import text_card_draw_indices
        for card_idx in reversed(text_card_draw_indices(settings)):
            card = settings.images[card_idx]
            if card.item_type == 'TEXT' and card.show_in_editor \
                    and (img is None or img.item_id == card.item_id) \
                    and hit_test_text_resize(card, mouse, pixel_size):
                if not event.shift:
                    _clear_image_selection(settings)
                    _clear_arrow_selection(settings)
                card.is_selected = True
                _set_canvas_active(settings, image_index=card_idx)
                self._start_text_resize(card, mouse)
                context.area.tag_redraw()
                return self._begin_gesture(context)

        if img:
            if (img.item_type == 'TEXT' and (img.text_markdown or img.text_checklist)
                    and event.ctrl and not (event.shift or event.alt)):
                from ..utils.gpu.gpu_text import hit_test_markdown_link
                url = hit_test_markdown_link(
                    img, context.region, (event.mouse_region_x, event.mouse_region_y))
                if url:
                    bpy.ops.wm.url_open(url=url)
                    return {'CANCELLED'}
            if img.item_type == 'TEXT' and img.text_checklist and not (event.shift or event.ctrl or event.alt):
                from ..utils.gpu.gpu_text import hit_test_checklist, hit_test_checklist_eye
                eye_index = hit_test_checklist_eye(
                    img, context.region, (event.mouse_region_x, event.mouse_region_y))
                if eye_index is not None:
                    line = img.text_lines[eye_index]
                    line.show_color_links = not line.show_color_links
                    context.area.tag_redraw()
                    return {'FINISHED'}
                task_index = hit_test_checklist(
                    img, context.region, (event.mouse_region_x, event.mouse_region_y))
                if task_index is not None:
                    img.text_lines[task_index].done = not img.text_lines[task_index].done
                    context.area.tag_redraw()
                    return {'FINISHED'}
            if event.shift:
                img.is_selected = not img.is_selected
                if img.is_selected:
                    _set_canvas_active(settings, image_index=idx)
                elif not any(item.is_selected for item in settings.images):
                    next_arrow = next((i for i, item in enumerate(settings.arrows)
                                       if item.is_selected), -1)
                    _set_canvas_active(settings, arrow_index=next_arrow)
            else:
                if not img.is_selected:
                    _clear_image_selection(settings)
                    _clear_arrow_selection(settings)
                img.is_selected = True
                _set_canvas_active(settings, image_index=idx)
            context.area.tag_redraw()
            if img.is_selected:
                self.start_drag(context, img, 'MOVE', mouse)
                return self._begin_gesture(context)
            return {'CANCELLED'}

        if frame_part == 'RESIZE':
            if not frame.is_selected:
                _clear_image_selection(settings)
                _clear_arrow_selection(settings)
            frame.is_selected = True
            _set_canvas_active(settings, image_index=frame_idx)
            self._start_frame_drag(context, frame, frame_part, mouse)
            context.area.tag_redraw()
            return self._begin_gesture(context)

        # The frame body is canvas space: a click/drag there can start box
        # selection. Select and move the frame through its header instead.
        if frame_part == 'MOVE':
            if event.shift:
                frame.is_selected = not frame.is_selected
                if frame.is_selected:
                    _set_canvas_active(settings, image_index=frame_idx)
                elif not any(item.is_selected for item in settings.images):
                    next_arrow = next((i for i, item in enumerate(settings.arrows)
                                       if item.is_selected), -1)
                    _set_canvas_active(settings, arrow_index=next_arrow)
                context.area.tag_redraw()
                return {'CANCELLED'}
            if not frame.is_selected:
                _clear_image_selection(settings)
                _clear_arrow_selection(settings)
            frame.is_selected = True
            _set_canvas_active(settings, image_index=frame_idx)
            self._start_frame_drag(context, frame, frame_part, mouse)
            context.area.tag_redraw()
            return self._begin_gesture(context)

        tree = context.space_data.edit_tree
        if event.alt and prefs.box_select_alt_drag:
            self._start_box_selection(context, event, *mouse)
            return self._begin_gesture(context)
        if prefs.box_select_on_drag and not event.ctrl:
            self.drag_mode = 'PENDING_BOX'
            self.pending_view_start = mouse
            self.pending_region_start = (event.mouse_region_x, event.mouse_region_y)
            self.box_additive = event.shift
            return self._begin_gesture(context)
        if not event.shift:
            _clear_image_selection(settings)
            _clear_arrow_selection(settings)
            context.area.tag_redraw()
        return {'CANCELLED', 'PASS_THROUGH'}

    def modal(self, context, event):
        settings = get_settings(context)
        tree = getattr(getattr(context, 'space_data', None), 'edit_tree', None)
        if tree is None or tree.bl_idname != 'KanvasNodeTree' or settings.batch_loading:
            self._cancel_drag(context)
            return self._end(context, {'CANCELLED', 'PASS_THROUGH'})
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._cancel_drag(context)
            return self._end(context, {'CANCELLED'})

        if self.drag_mode == 'TEXT_SCROLL':
            if event.type == 'MOUSEMOVE':
                self._update_text_scroll(context, event.mouse_region_y)
                return {'RUNNING_MODAL'}
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self.drag_mode = 'NONE'
                return self._end(context, {'FINISHED'})
            return {'RUNNING_MODAL', 'PASS_THROUGH'}

        _sync_modifiers(settings, event)
        if event.type in {'LEFT_ALT', 'RIGHT_ALT', 'LEFT_SHIFT', 'RIGHT_SHIFT',
                          'LEFT_CTRL', 'RIGHT_CTRL'}:
            if self.drag_mode in {'ROTATE', 'TEXT_RESIZE'}:
                self._update_drag(context, *self.last_mouse_pos,
                                  shift=settings.shift_is_held, ctrl=settings.ctrl_is_held)
            context.area.tag_redraw()
            return {'RUNNING_MODAL', 'PASS_THROUGH'}

        # Tecla F para soltar/desanexar imagens do frame durante o arrasto
        if event.type == 'F':
            if event.value == 'PRESS':
                self._resolve_drag_items(settings)
                self.f_is_held = True
                settings.f_is_held = True
                if self.drag_mode == 'MOVE':
                    targets = [t['img'] for t in self.multi_targets] if self.multi_targets else ([self.drag_target] if self.drag_target else [])
                    detached_any = False
                    for item in targets:
                        if item.parent_frame:
                            self.affected_frame_names.add(item.parent_frame)
                            item.parent_frame = ''
                            self.detached_in_gesture.add(item.item_id)
                            detached_any = True
                    if detached_any and tree:
                        from ..utils.gpu import update_frame_bounds
                        for fname in list(self.affected_frame_names):
                            update_frame_bounds(tree, settings, fname, initial_bounds=getattr(self, 'initial_frame_bounds', None))
                        context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE':
                self.f_is_held = False
                settings.f_is_held = False
                return {'RUNNING_MODAL'}

        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            if (getattr(self, 'keyboard_transform', False)
                    and event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS'):
                self._stop_drag(context)
                return self._end(context, {'FINISHED'})
            return {'RUNNING_MODAL', 'PASS_THROUGH'}
        mouse = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)

        if self.drag_mode == 'PENDING_BOX':
            dx = event.mouse_region_x - self.pending_region_start[0]
            dy = event.mouse_region_y - self.pending_region_start[1]
            if abs(dx) >= 3 or abs(dy) >= 3:
                self._start_box_selection(context, event, *self.pending_view_start, native=True)
                self.box_region_start = self.pending_region_start
                settings.box_sel_start = self.pending_view_start
                self.box_region_end = (event.mouse_region_x, event.mouse_region_y)
                settings.box_sel_end = mouse
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self.drag_mode = 'NONE'
                if not self.box_additive:
                    _clear_image_selection(settings)
                    if bpy.ops.node.select.poll():
                        bpy.ops.node.select(location=self.pending_region_start, deselect_all=True)
                return self._end(context, {'FINISHED'})

        if event.type == 'MOUSEMOVE':
            if self.drag_mode == 'SELECT_BOX':
                self.box_region_end = (event.mouse_region_x, event.mouse_region_y)
            self._update_drag(context, *mouse, shift=event.shift, ctrl=event.ctrl)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if getattr(self, 'keyboard_transform', False) and event.value == 'PRESS':
            self._update_drag(context, *mouse, shift=event.shift, ctrl=event.ctrl)
            self._stop_drag(context)
            return self._end(context, {'FINISHED'})
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.drag_mode == 'SELECT_BOX':
                self.box_region_end = (event.mouse_region_x, event.mouse_region_y)
                settings.box_sel_end = mouse
            self._stop_drag(context)
            return self._end(context, {'FINISHED'})
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._cancel_drag(context)
        self._end(context, {'CANCELLED'})
