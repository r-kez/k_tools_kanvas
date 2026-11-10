import bpy
from ..kanvas_data import get_settings
import blf
import gpu
import uuid
from gpu_extras.batch import batch_for_shader
from .gpu_grid import draw_axes, draw_canvas_backdrop
from .gpu_guides import draw_snap_guides
from .gpu_frame import draw_kanvas_frame, frame_header_height
from .gpu_image import get_kanvas_texture, invalidate_texture_cache, prune_texture_cache, clear_texture_cache, get_cached_texture
from .gpu_selection import draw_selection_box
from .gpu_visibility import image_intersects_view
from .gpu_annotation import draw_canvas_annotations
from .gpu_text import draw_text_card, draw_text_label, _region_bounds
from .gpu_theme import (enable_soft_text_shadow, disable_soft_text_shadow,
                        draw_canvas_text)
from .gpu_arrow import draw_arrows, draw_arrow_labels, draw_text_anchor_handles
from .gpu_checklist import draw_checklist_links
from .gpu_recenter import draw_recenter_prompt
from .gpu_common import begin_draw_pass, end_draw_pass, value_view_uniforms
from ..item_geometry import (item_bounds, image_draw_indices, layer_draw_indices,
                             text_card_draw_indices)

def get_frame(settings, frame_name):
    return next((item for item in settings.images
                 if item.item_type == 'FRAME' and item.frame_node_name == frame_name), None)


def is_group(item):
    return item.item_type == 'FRAME' and item.frame_is_group


def owning_group(settings, item):
    """The group that holds this item directly or through frames, or None."""
    name, seen = item.parent_frame, set()
    while name and name not in seen:
        seen.add(name)
        parent = get_frame(settings, name)
        if parent is None:
            return None
        if parent.frame_is_group:
            return parent
        name = parent.parent_frame
    return None


def prune_empty_groups(settings):
    """A group without members has no reason to exist."""
    used = {item.parent_frame for item in settings.images if item.parent_frame}
    for index in range(len(settings.images) - 1, -1, -1):
        item = settings.images[index]
        if is_group(item) and item.frame_node_name not in used:
            if settings.active_image_index == index:
                settings.active_image_index = -1
            settings.images.remove(index)


def ensure_item_ids(settings):
    """Backfill old files and repair IDs copied by Blender's duplicate operation."""
    seen = set()
    for item in settings.images:
        if not item.item_id or item.item_id in seen:
            item.item_id = uuid.uuid4().hex
        seen.add(item.item_id)
        if item.item_type == 'TEXT':
            line_ids = set()
            for line in item.text_lines:
                if not line.line_id or line.line_id in line_ids:
                    line.line_id = uuid.uuid4().hex
                line_ids.add(line.line_id)


def get_item_by_id(settings, item_id):
    return next((item for item in settings.images if item.item_id == item_id), None)


def frame_ancestors(settings, frame):
    """Return parent frames, stopping safely at damaged or cyclic links."""
    result, seen = [], {frame.frame_node_name}
    name = frame.parent_frame
    while name and name not in seen:
        seen.add(name)
        parent = get_frame(settings, name)
        if parent is None:
            break
        result.append(parent)
        name = parent.parent_frame
    return result


def frame_descendants(settings, frame_name):
    """All descendants in collection order, including nested frames."""
    result, pending, seen, seen_items = [], [frame_name], {frame_name}, set()
    while pending:
        parent_name = pending.pop(0)
        for item in settings.images:
            identity = item.item_id or item.as_pointer()
            if item.parent_frame != parent_name or identity in seen_items:
                continue
            seen_items.add(identity)
            result.append(item)
            if item.item_type == 'FRAME' and item.frame_node_name not in seen:
                seen.add(item.frame_node_name)
                pending.append(item.frame_node_name)
    return result


def frames_with_images(settings):
    """Frame IDs containing an image directly or through a nested frame."""
    parents = {item.frame_node_name: item.parent_frame for item in settings.images
               if item.item_type == 'FRAME'}
    result = set()
    for item in settings.images:
        if item.item_type != 'IMAGE' or not item.image_data:
            continue
        name, seen = item.parent_frame, set()
        while name in parents and name not in seen:
            result.add(name)
            seen.add(name)
            name = parents[name]
    return result


def frame_has_images(settings, frame_name):
    return frame_name in frames_with_images(settings)


def frame_has_content(settings, frame_name):
    """A direct child includes cards and nested frames as well as images."""
    return any(item.parent_frame == frame_name for item in settings.images)


def can_attach_to_frame(settings, item, frame_name):
    if item.item_type not in {'IMAGE', 'TEXT', 'SHAPE', 'FRAME'} or not get_frame(settings, frame_name):
        return False
    if item.item_type == 'FRAME':
        if item.frame_node_name == frame_name:
            return False
        target = get_frame(settings, frame_name)
        if item.frame_is_group and (target.frame_is_group or owning_group(settings, target)):
            return False
        if any(parent.frame_node_name == item.frame_node_name
               for parent in frame_ancestors(settings, target)):
            return False
    return True


def _ordered_items(settings):
    """The items in list order: the stacking order, front first, frames before their
    children (see `item_geometry.stack_order`)."""
    from ..item_geometry import stack_order
    return [settings.images[index] for index in stack_order(settings)]


def _ordered_items_by_frame(settings):
    """The former list order (frames first, then loose items), kept for reference."""
    items = list(settings.images)
    frames = [item for item in items if item.item_type == 'FRAME']
    frame_names = {frame.frame_node_name for frame in frames}
    result, visited = [], set()

    def visit(frame):
        if frame.item_id in visited:
            return
        visited.add(frame.item_id)
        result.append(frame)
        for child in items:
            if child.parent_frame == frame.frame_node_name:
                if child.item_type == 'FRAME':
                    visit(child)
                elif child.item_id not in visited:
                    visited.add(child.item_id)
                    result.append(child)

    for frame in frames:
        if not frame.parent_frame or frame.parent_frame not in frame_names:
            visit(frame)
    for frame in frames:
        visit(frame)
    result.extend(item for item in items if item.item_id not in visited)
    return result


def _item_snapshot(item):
    """Identity independent of UI order, names, frame membership and layers."""
    return item.item_id


def sync_kanvas_frames(tree, settings):
    """Convert legacy/native NodeFrames and group the persistent Kanvas items."""
    if not tree:
        return
    ensure_item_ids(settings)
    native_frames = [node for node in tree.nodes if node.type == 'FRAME']
    native_parent = {node.name: node.parent.name if node.parent and node.parent.type == 'FRAME' else ''
                     for node in native_frames}
    for node in native_frames:
        item = get_frame(settings, node.name)
        if item is None:
            item = settings.images.add()
            item.item_id = uuid.uuid4().hex
            item.item_type = 'FRAME'
            item.frame_node_name = node.name
            item.name = node.label or node.name
            item.auto_resize = getattr(node, "shrink", True)
        position = node.location.copy()
        parent = node.parent
        while parent:
            position += parent.location
            parent = parent.parent
        item.location = position
        item.frame_width = max(60, node.width)
        item.frame_height = max(60, node.height)
        if node.use_custom_color:
            item.frame_color = node.color
        item.parent_frame = native_parent[node.name]
    for node in native_frames:
        tree.nodes.remove(node)

    ensure_item_ids(settings)
    prune_empty_groups(settings)
    frame_names = {item.frame_node_name for item in settings.images if item.item_type == 'FRAME'}
    for item in settings.images:
        if item.parent_frame and item.parent_frame not in frame_names:
            item.parent_frame = ''
        if item.item_type == 'FRAME' and item.parent_frame:
            if not can_attach_to_frame(settings, item, item.parent_frame):
                item.parent_frame = ''

    items = list(settings.images)
    desired_order = _ordered_items(settings)

    if len(desired_order) != len(items):
        return  # Segurança: contagem divergiu, evita corrupção

    # Preserva snapshot do item ativo para restaurar índice depois
    active_snap = None
    if 0 <= settings.active_image_index < len(settings.images):
        active_snap = _item_snapshot(settings.images[settings.active_image_index])

    # --- Reordenação por permutação (sem as_pointer()) ---
    # Gera snapshot de cada item na ordem desejada
    desired_snaps = [_item_snapshot(item) for item in desired_order]
    n = len(desired_order)

    # Para cada posição atual em settings.images, descobre qual posição desejada lhe corresponde.
    # Usa matching sequencial para tratar duplicatas corretamente.
    remaining_desired = list(range(n))
    perm = [-1] * n  # perm[current_idx] = desired_idx

    for current_idx in range(n):
        snap = _item_snapshot(settings.images[current_idx])
        for k, desired_idx in enumerate(remaining_desired):
            if desired_snaps[desired_idx] == snap:
                perm[current_idx] = desired_idx
                remaining_desired.pop(k)
                break

    # Selection sort: para cada posição i, coloca lá o item com desired_idx == i.
    # Atualiza perm a cada move para refletir as mudanças de posição.
    for i in range(n):
        # Encontra j >= i tal que perm[j] == i
        for j in range(i, n):
            if perm[j] == i:
                if j != i:
                    settings.images.move(j, i)
                    # Atualiza perm: o item de j foi para i; itens [i, j-1] deslocaram para [i+1, j]
                    val = perm.pop(j)
                    perm.insert(i, val)
                break

    # Restaura o índice ativo localizando o item pelo snapshot
    if active_snap is not None:
        for idx in range(len(settings.images)):
            if _item_snapshot(settings.images[idx]) == active_snap:
                if settings.active_image_index != idx:
                    from ...properties import suspend_selection_updates
                    with suspend_selection_updates():
                        settings.active_image_index = idx
                break

def is_sync_needed(tree, settings):
    """Check whether native frames need conversion or the list needs grouping."""
    if not tree:
        return False
    ensure_item_ids(settings)

    if any(node.type == 'FRAME' for node in tree.nodes):
        return True
    items = list(settings.images)
    desired_order = _ordered_items(settings)
    frame_names = {item.frame_node_name for item in items if item.item_type == 'FRAME'}
    if any(item.parent_frame and item.parent_frame not in frame_names for item in items):
        return True
    if any(item.item_type == 'FRAME' and item.parent_frame
           and not can_attach_to_frame(settings, item, item.parent_frame) for item in items):
        return True

    if len(items) != len(desired_order):
        return True

    for i, target_item in enumerate(desired_order):
        if _item_snapshot(items[i]) != _item_snapshot(target_item):
            return True

    return False


def _get_frame_bounds(frame):
    x, y = frame.location
    return x, y - frame.frame_height, x + frame.frame_width, y


FRAME_PADDING_TOP = 24.0
FRAME_PADDING_SIDE = 24.0
FRAME_PADDING_BOTTOM = 24.0

GROUP_PADDING = 8.0
MARGIN_X = FRAME_PADDING_SIDE                          # 24.0
MARGIN_BOTTOM = FRAME_PADDING_BOTTOM                   # 24.0


def auto_fit_frame(tree, settings, frame_name, initial_bounds=None):
    """Resize a Kanvas frame around its direct children."""
    frame = get_frame(settings, frame_name)
    if frame is None:
        return
    children = [item for item in settings.images
                if item.item_type in {'IMAGE', 'TEXT', 'SHAPE', 'FRAME'} and item.parent_frame == frame_name]
    if not children:
        if initial_bounds and frame_name in initial_bounds:
            orig_x, orig_y, orig_w, orig_h = initial_bounds[frame_name]
            frame.location = (orig_x, orig_y)
            frame.frame_width = orig_w
            frame.frame_height = orig_h
        return
    bounds = [item_bounds(item) for item in children]
    bounds = [bound for bound in bounds if bound is not None]
    if bounds:
        min_x = min(bound[0] for bound in bounds)
        min_y = min(bound[1] for bound in bounds)
        max_x = max(bound[2] for bound in bounds)
        max_y = max(bound[3] for bound in bounds)
        if frame.frame_is_group:
            # A group hugs its members: no header, a thin margin for the outline.
            pad = GROUP_PADDING
            frame.location = (min_x - pad, max_y + pad)
            frame.frame_width = max(1.0, max_x - min_x + 2 * pad)
            frame.frame_height = max(1.0, max_y - min_y + 2 * pad)
            return
        margin_top = frame_header_height(frame) + FRAME_PADDING_TOP
        frame.location = (min_x - MARGIN_X, max_y + margin_top)
        frame.frame_width = max(100.0, max_x - min_x + 2 * MARGIN_X)
        frame.frame_height = max(80.0, (max_y - min_y) + margin_top + MARGIN_BOTTOM)


def expand_frame_to_fit(frame, settings):
    """Ensure the frame encloses attached items without shrinking manual bounds."""
    if frame is None:
        return
    children = [item for item in settings.images
                if item.item_type in {'IMAGE', 'TEXT', 'SHAPE', 'FRAME'} and item.parent_frame == frame.frame_node_name]
    if not children:
        return
    bounds = [item_bounds(item) for item in children]
    bounds = [bound for bound in bounds if bound is not None]
    if bounds:
        min_x = min(bound[0] for bound in bounds)
        min_y = min(bound[1] for bound in bounds)
        max_x = max(bound[2] for bound in bounds)
        max_y = max(bound[3] for bound in bounds)

        cur_left = frame.location[0]
        cur_top = frame.location[1]
        cur_right = cur_left + frame.frame_width
        cur_bottom = cur_top - frame.frame_height

        new_left = min(cur_left, min_x - MARGIN_X)
        new_right = max(cur_right, max_x + MARGIN_X)
        new_top = max(cur_top, max_y + frame_header_height(frame) + FRAME_PADDING_TOP)
        new_bottom = min(cur_bottom, min_y - MARGIN_BOTTOM)

        frame.location = (new_left, new_top)
        frame.frame_width = max(100.0, new_right - new_left)
        frame.frame_height = max(80.0, new_top - new_bottom)


def update_frame_bounds(tree, settings, frame_name, initial_bounds=None):
    """Update a frame, then its ancestors from the inside outward."""
    from ...properties import suspend_frame_geometry_updates
    seen = set()
    with suspend_frame_geometry_updates():
        while frame_name and frame_name not in seen:
            seen.add(frame_name)
            frame = get_frame(settings, frame_name)
            if frame is None:
                break
            if frame_has_content(settings, frame_name) and not frame.auto_resize:
                frame.auto_resize = True
            if getattr(frame, "auto_resize", True):
                auto_fit_frame(tree, settings, frame_name, initial_bounds=initial_bounds)
            else:
                expand_frame_to_fit(frame, settings)
            frame_name = frame.parent_frame


def find_frame_at_location(settings, location, margin=0.0, exclude_frame_names=None):
    """Return the frontmost frame under or close to a 2D view position."""
    if location is None:
        return None
    candidates = []
    x, y = location
    excluded = exclude_frame_names or set()
    depth = {frame.frame_node_name: order
             for order, (_, frame) in enumerate(visible_frames_in_draw_order(settings))}
    for index, frame in enumerate(settings.images):
        if (frame.item_type != 'FRAME' or not frame.show_in_editor or frame.frame_is_group
                or frame.frame_node_name in excluded):
            continue
        x0, y0, x1, y1 = _get_frame_bounds(frame)
        inside = x0 <= x <= x1 and y0 <= y <= y1
        nearby = (x0 - margin <= x <= x1 + margin
                  and y0 - margin <= y <= y1 + margin)
        if nearby:
            candidates.append((inside, depth.get(frame.frame_node_name, -1), index, frame))
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c[0], c[1], c[2]))[3]


def release_guard_active(settings, item, location, margin=0.0):
    """Keep a released item free until its pointer leaves the former frame."""
    frame_name = item.released_parent_frame
    if not frame_name or location is None:
        return False
    frame = get_frame(settings, frame_name)
    if frame is not None:
        x0, y0, x1, y1 = _get_frame_bounds(frame)
        x, y = location
        if (x0 - margin <= x <= x1 + margin
                and y0 - margin <= y <= y1 + margin):
            return True
    item.released_parent_frame = ''
    return False


def attach_items_to_frame(tree, settings, targets, frame_name, initial_bounds=None):
    """Attach a complete selection without intermediate auto-fit changes."""
    frame = get_frame(settings, frame_name)
    if frame is None:
        return set()
    from ...properties import suspend_frame_geometry_updates
    changed = set()
    with suspend_frame_geometry_updates():
        for item in targets:
            if item.parent_frame == frame_name or not can_attach_to_frame(settings, item, frame_name):
                continue
            if item.item_type == 'IMAGE' and not item.image_data:
                continue
            if item.parent_frame:
                changed.add(item.parent_frame)
            item.parent_frame = frame_name
            item.released_parent_frame = ''
            changed.add(frame_name)
    for name in changed:
        update_frame_bounds(tree, settings, name, initial_bounds=initial_bounds)
    return changed


def visible_frames_in_draw_order(settings):
    """Use the same frame order for painting and mouse hit testing."""
    frames = [(index, item) for index, item in enumerate(settings.images)
              if item.item_type == 'FRAME' and item.show_in_editor and not item.frame_is_group]
    names = {frame.frame_node_name for _, frame in frames}
    result, seen = [], set()
    def visit(entry):
        index, frame = entry
        if frame.frame_node_name in seen:
            return
        seen.add(frame.frame_node_name)
        result.append(entry)
        children = [child for child in frames if child[1].parent_frame == frame.frame_node_name]
        for child in sorted(children, key=lambda e: (e[1].z_index, e[0])):
            visit(child)
    roots = [entry for entry in frames if entry[1].parent_frame not in names]
    for entry in sorted(roots, key=lambda e: (e[1].z_index, e[0])):
        visit(entry)
    for entry in sorted(frames, key=lambda e: (e[1].z_index, e[0])):
        visit(entry)
    return result


def frame_header_open_spans(settings, frame, x0, x1, y0, y1, frame_depth=None):
    """Horizontal header spans not covered by content painted above this frame."""
    if frame_depth is None:
        frame_depth = {item.frame_node_name: depth
                       for depth, (_, item) in enumerate(visible_frames_in_draw_order(settings))}
    spans = [(x0, x1)]
    for other in settings.images:
        if not other.show_in_editor:
            continue
        if other.item_type == 'FRAME':
            if other.frame_node_name == frame.frame_node_name:
                continue
            if (frame_depth.get(other.frame_node_name, -1)
                    <= frame_depth.get(frame.frame_node_name, -1)):
                continue
        bounds = item_bounds(other)
        if not bounds or bounds[1] >= y1 or bounds[3] <= y0:
            continue
        cut_left, cut_right = bounds[0], bounds[2]
        remaining = []
        for left, right in spans:
            if cut_left > left:
                remaining.append((left, min(right, cut_left)))
            if cut_right < right:
                remaining.append((max(left, cut_right), right))
        spans = [(left, right) for left, right in remaining if right > left]
        if not spans:
            break
    return spans


def auto_parent_images_to_frames(tree, settings, targets=None, allow_unparent=False):
    """Attach moved images to the smallest custom frame containing their center.
    If allow_unparent is False, images already attached to a frame will not be
    accidentally unparented when dragged outside."""
    frames = [item for item in settings.images
              if item.item_type == 'FRAME' and item.show_in_editor and not item.frame_is_group]
    bounds = []
    for frame in frames:
        x0, y0, x1, y1 = _get_frame_bounds(frame)
        bounds.append((frame.frame_width * frame.frame_height,
                       frame.frame_node_name, x0, y0, x1, y1))
    bounds.sort(key=lambda entry: entry[0])

    affected_frames = set()
    for img in (targets if targets is not None else settings.images):
        if img.item_type not in {'IMAGE', 'TEXT', 'SHAPE'} or (img.item_type == 'IMAGE' and not img.image_data):
            continue
        x, y = img.location
        old_parent = img.parent_frame
        found_parent = next((name for _, name, x0, y0, x1, y1 in bounds
                             if x0 <= x <= x1 and y0 <= y <= y1), '')
        if old_parent:
            if allow_unparent and not found_parent:
                img.parent_frame = ''
                affected_frames.add(old_parent)
            elif found_parent and found_parent != old_parent:
                img.parent_frame = found_parent
                affected_frames.add(old_parent)
                affected_frames.add(found_parent)
            else:
                affected_frames.add(old_parent)
        else:
            if found_parent:
                img.parent_frame = found_parent
                affected_frames.add(found_parent)

    return affected_frames


# ---------------------------------------------------------------------------
# Draw callback principal
# ---------------------------------------------------------------------------

def _draw_callback_px(*args):
    """SpaceNodeEditor POST_VIEW canvas callback, above the native dot grid."""
    context = bpy.context

    if not hasattr(context, "scene") or context.scene is None:
        return

    if (not hasattr(context, "space_data")
            or not hasattr(context.space_data, "edit_tree")
            or context.space_data.edit_tree is None
            or context.space_data.edit_tree.bl_idname != 'KanvasNodeTree'):
        return

    try:
        settings = get_settings(context)
    except AttributeError:
        return



    # Calculate view_pixel_size
    try:
        region = context.region
        v2d = region.view2d
        p0 = v2d.region_to_view(0, 0)
        p1 = v2d.region_to_view(1, 1)
        p2 = v2d.region_to_view(region.width, region.height)
        view_pixel_size = abs(p1[0] - p0[0])
        view_bounds = (min(p0[0], p2[0]), min(p0[1], p2[1]),
                       max(p0[0], p2[0]), max(p0[1], p2[1]))
    except Exception:
        return

    draw_board(settings, view_bounds, view_pixel_size, region,
               space=context.space_data, frame_number=context.scene.frame_current)


def draw_board(settings, view_bounds, view_pixel_size, region, space=None, frame_number=0,
               export=False):
    """Everything of the board drawn in view space (POST_VIEW), for the canvas and for
    an exported image (`utils/board_render.py`). With `export`, what belongs to the
    interface stays out: the canvas background, the axes, snap guides, the drop
    highlight, selection outlines and handles, the ghost of an image whose mask is
    being edited and the greying of the editing focus. `region` may be a stand-in
    with `width`, `height` and `view2d`."""



    if not export:
        try:
            draw_canvas_backdrop(view_bounds, view_pixel_size)
        except Exception as exc:
            print(f"Kanvas canvas background: {exc}")

    # The axes form the bottom layer of the Kanvas items.
    if settings.show_debug_grid and not export:
        try:
            draw_axes(view_bounds)
        except Exception:
            pass

    # Frames are Kanvas data, drawn behind the images.
    for _, frame in visible_frames_in_draw_order(settings):
        try:
            draw_kanvas_frame(frame, view_pixel_size,
                              highlight=(not export
                                         and settings.drop_target_frame == frame.frame_node_name),
                              allow_resize=not frame_has_content(settings, frame.frame_node_name))
        except Exception:
            pass

    if (settings.show_snap_viz_x or settings.show_snap_viz_y) and not export:
        try:
            draw_snap_guides(settings, view_bounds=view_bounds)
        except Exception:
            pass

    selected_images = [img for img in settings.images if img.is_selected and img.show_in_editor and img.image_data]
    multi_select = len(selected_images) > 1

    invalidate_texture_cache()

    # Images and shapes share one stack: draw them together, back to front.
    from .gpu_shape import draw_shape_body
    from .gpu_focus import saturation_scale
    faded = None if export else saturation_scale(settings)   # greyed out while editing
    for image_index in layer_draw_indices(settings):
        img_item = settings.images[image_index]
        if img_item.item_type == 'SHAPE':
            draw_shape_body(img_item, view_pixel_size, view_bounds)
            continue
        if not image_intersects_view(img_item, view_bounds):
            continue

        try:
            final_scale = (img_item.scale_xy[0] * img_item.scale_master, img_item.scale_xy[1] * img_item.scale_master)
            if not img_item.is_selected:
                # Sub-pixel images add nothing visible; skip all their GPU work.
                size = img_item.image_data.size
                if max(size[0] * abs(final_scale[0]),
                       size[1] * abs(final_scale[1])) < 0.75 * view_pixel_size:
                    continue
            tex = get_kanvas_texture(img_item.image_data)
            mask_texture = None
            if img_item.mask_enabled:
                try:
                    from .gpu_mask import mask_texture_for_item
                    mask_texture = mask_texture_for_item(img_item)
                except Exception as exc:
                    print(f"Kanvas: Could not build image mask for {img_item.name}: {exc}")
            markup_texture = None
            if img_item.markup_visible and img_item.markup_regions:
                try:
                    from .gpu_markup import markup_texture_for_item
                    markup_texture = markup_texture_for_item(img_item)
                except Exception as exc:
                    print(f"Kanvas: Could not build color markup for {img_item.name}: {exc}")

            value_mode, value_levels = value_view_uniforms(img_item)
            saturation = img_item.saturation
            if faded is not None and img_item.item_id != faded[0]:
                saturation *= faded[1]
            if img_item.mask_editing and not export:
                tex.draw(
                    img_item.location, final_scale, img_item.shear_xy,
                    img_item.rotation, img_item.opacity * 0.22,
                    img_item.color_tint, brightness=img_item.brightness,
                    contrast=img_item.contrast, saturation=saturation,
                    flip_h=img_item.flip_h, flip_v=img_item.flip_v,
                    use_color_correction=img_item.use_color_correction,
                    value_mode=value_mode, value_levels=value_levels,
                )

            tex.draw(
                img_item.location,
                final_scale,
                img_item.shear_xy,
                img_item.rotation,
                img_item.opacity,
                img_item.color_tint,
                brightness=img_item.brightness,
                contrast=img_item.contrast,
                saturation=saturation,
                flip_h=img_item.flip_h,
                flip_v=img_item.flip_v,
                use_color_correction=img_item.use_color_correction,
                mask_texture=mask_texture,
                mask_enabled=img_item.mask_enabled,
                markup_texture=markup_texture,
                markup_enabled=img_item.markup_visible,
                value_mode=value_mode, value_levels=value_levels,
            )

        except Exception:
            pass

    # Comparison cards use the same pass and shader as the images they show.
    for card_index in text_card_draw_indices(settings):
        card = settings.images[card_index]
        if card.text_compare:
            try:
                from .gpu_compare import draw_compare_content
                draw_compare_content(card, settings, view_pixel_size)
            except Exception as exc:
                print(f"Kanvas comparison: {exc}")

    if export:
        # The rest is selection, handles and the drag box: interface, not board.
        draw_checklist_links(settings, view_pixel_size, region)
        draw_arrows(settings, view_pixel_size)
        if space is not None:
            draw_canvas_annotations(space, frame_number)
        return

    # Selection outlines and vertex handles of shapes go above every layer.
    try:
        from .gpu_shape import draw_shape_overlays
        draw_shape_overlays(settings, view_pixel_size, view_bounds)
    except Exception as exc:
        print(f"Kanvas shapes: {exc}")
    try:
        from .gpu_group import draw_group_outlines
        draw_group_outlines(settings, view_pixel_size)
    except Exception as exc:
        print(f"Kanvas groups: {exc}")
    try:
        from .gpu_measure import draw_marks
        draw_marks(settings, view_pixel_size, view_bounds)
    except Exception as exc:
        print(f"Kanvas marks: {exc}")

    draw_checklist_links(settings, view_pixel_size, region)
    draw_arrows(settings, view_pixel_size)

    # Selection outlines and the drag rectangle must sit above every image.
    if selected_images:
        from .gpu_common import get_prefs
        prefs = get_prefs()
        sel_color = prefs.color_selection if prefs else (0.0, 0.8, 1.0, 1.0)
        thickness = prefs.selection_thickness if prefs else 2.0

        # Desenha contorno individual colorido em cada imagem selecionada
        for img_item in selected_images:
            tex = get_cached_texture(img_item.image_data)
            if tex and tex.texture:
                final_scale = (img_item.scale_xy[0] * img_item.scale_master,
                               img_item.scale_xy[1] * img_item.scale_master)
                try:
                    tex.draw_outline(img_item.location, final_scale, img_item.shear_xy, img_item.rotation,
                                     color=sel_color, thickness=thickness)
                except Exception:
                    pass

        if multi_select:
            from .gpu_common import get_collective_bounding_box
            from .gpu_image import draw_collective_outline, draw_collective_gizmos
            data_list = []
            for img in selected_images:
                width, height = img.image_data.size
                if width > 0 and height > 0:
                    data_list.append((img.location, img.scale_xy, img.scale_master,
                                      img.shear_xy, img.rotation, width, height))
            collective_bbox = get_collective_bounding_box(data_list)
            if collective_bbox:
                try:
                    draw_collective_outline(collective_bbox, sel_color, thickness)
                    if settings.show_gizmos:
                        draw_collective_gizmos(collective_bbox, settings.gizmo_size * view_pixel_size)
                except Exception:
                    pass
        else:
            img_item = selected_images[0]
            tex = get_cached_texture(img_item.image_data)
            if tex and tex.texture:
                final_scale = (img_item.scale_xy[0] * img_item.scale_master,
                               img_item.scale_xy[1] * img_item.scale_master)
                try:
                    if settings.show_gizmos:
                        tex.draw_gizmos(img_item.location, final_scale, img_item.shear_xy,
                                        img_item.rotation, settings.gizmo_size * view_pixel_size)
                    if settings.show_hitbox_debug:
                        tex.draw_hitboxes(img_item.location, final_scale, img_item.shear_xy,
                                          img_item.rotation, settings.gizmo_size * view_pixel_size)
                except Exception:
                    pass

    # Native canvas strokes were drawn before POST_VIEW; restore them above
    # Kanvas images. Blender draws its in-progress paint buffer later itself.
    if space is not None:
        draw_canvas_annotations(space, frame_number)

    prune_texture_cache()
    if not export:
        try:
            from ..overlay_3d import notify_board_drawn
            notify_board_drawn(settings)
        except Exception as exc:
            print(f"Kanvas: could not refresh the 3D overlays: {exc}")


def _lock_extra(frame, text_h):
    return text_h * 1.35 if frame.is_locked else 0.0


def _draw_lock_icon(x, y, size):
    """Padlock in region pixels: filled body with a shackle above it."""
    body_h = size * 0.55
    body = [(x + size * 0.1, y), (x + size * 0.9, y),
            (x + size * 0.9, y + body_h), (x + size * 0.1, y + body_h)]
    sx0, sx1 = x + size * 0.28, x + size * 0.72
    sy0, sy1 = y + body_h, y + size * 0.95
    t = max(1.0, size * 0.1)
    shackle = [(sx0, sy0), (sx0 + t, sy0), (sx0 + t, sy1 - t), (sx1 - t, sy1 - t),
               (sx1 - t, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1)]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        shader.uniform_float('color', (1.0, 1.0, 1.0, 0.95))
        batch_for_shader(shader, 'TRIS', {'pos': body},
                         indices=((0, 1, 2), (0, 2, 3))).draw(shader)
        batch_for_shader(shader, 'TRIS', {'pos': shackle}, indices=(
            (0, 1, 2), (0, 2, 7), (7, 2, 3), (7, 3, 6),
            (6, 3, 4), (6, 4, 5))).draw(shader)
    finally:
        gpu.state.blend_set(old_blend)


def _draw_frame_labels():
    """Text labels drawn crisply inside the canvas-space frame header."""
    context = bpy.context
    space = getattr(context, 'space_data', None)
    tree = getattr(space, 'edit_tree', None) if space else None
    if tree is None or tree.bl_idname != 'KanvasNodeTree':
        return
    region = getattr(context, 'region', None)
    scene = getattr(context, 'scene', None)
    if region is None or scene is None:
        return
    settings = get_settings(context)
    draw_board_labels(settings, region, area=context.area)


def draw_board_labels(settings, region, area=None, export=False):
    """Everything of the board drawn in region pixels (POST_PIXEL): frame titles,
    text cards, arrow, shape and color names. With `export`, the interface stays out
    (the shape cursor, edit buttons, handles, the editing focus, badges, the mode
    switch, the recenter button and the drag box)."""
    if not export:
        try:
            from . import gpu_shape_cursor
            if gpu_shape_cursor.is_active():
                gpu_shape_cursor.draw_shape_cursor(region)
        except Exception as exc:
            print(f"Kanvas shape cursor: {exc}")
    # Arrow geometry is behind text in POST_VIEW; its labels follow the same
    # order in POST_PIXEL so card and frame text remain readable.
    draw_arrow_labels(settings, region)
    try:
        from .gpu_shape import draw_shape_labels
        draw_shape_labels(settings, region)
    except Exception as exc:
        print(f"Kanvas shape text: {exc}")
    try:
        from .gpu_group import draw_group_labels
        draw_group_labels(settings, region)
    except Exception as exc:
        print(f"Kanvas group names: {exc}")
    if not export:
        try:
            from .gpu_measure import draw_mark_labels
            draw_mark_labels(settings, region)
        except Exception as exc:
            print(f"Kanvas mark sizes: {exc}")
    ordered_frames = visible_frames_in_draw_order(settings)
    frame_depth = {frame.frame_node_name: depth for depth, (_, frame) in enumerate(ordered_frames)}
    for _, frame in ordered_frames:
        if frame.item_type == 'FRAME' and frame.show_in_editor:
            left, top = frame.location
            x_reg, y_top_reg = region.view2d.view_to_region(left, top, clip=False)
            x_right_reg, _ = region.view2d.view_to_region(left + frame.frame_width, top, clip=False)
            header_height = frame_header_height(frame)
            _, y_hbot_reg = region.view2d.view_to_region(left, top - header_height, clip=False)
            header_screen_h = y_top_reg - y_hbot_reg
            header_screen_w = x_right_reg - x_reg
            if header_screen_h < 6 or header_screen_w < 12:
                continue
            pixel_size = frame.frame_width / header_screen_w
            header_center_y = top - header_height * 0.5
            usable_left = left + 6 * pixel_size
            usable_right = left + frame.frame_width - 6 * pixel_size
            font_size = min(96, max(5, round(frame.frame_font_size / pixel_size)))
            chosen_span = None
            label_text = frame.name
            while font_size >= 5:
                blf.size(0, font_size)
                text_w, text_h = blf.dimensions(0, label_text)
                text_w += _lock_extra(frame, text_h)
                if text_h <= header_screen_h - 1:
                    band_bottom = header_center_y - text_h * pixel_size * 0.5
                    band_top = header_center_y + text_h * pixel_size * 0.5
                    spans = frame_header_open_spans(
                        settings, frame, usable_left, usable_right,
                        band_bottom, band_top, frame_depth)
                    fitting = [span for span in spans
                               if span[1] - span[0] >= (text_w + 8) * pixel_size]
                    if fitting:
                        center_x = left + frame.frame_width * 0.5
                        chosen_span = min(fitting, key=lambda span:
                                          (abs((span[0] + span[1]) * 0.5 - center_x),
                                           -(span[1] - span[0])))
                        break
                font_size -= 1
            if chosen_span is None:
                # Keep a short title at distant zoom instead of dropping it.
                blf.size(0, 5)
                text_w, text_h = blf.dimensions(0, label_text)
                text_w += _lock_extra(frame, text_h)
                if text_h > header_screen_h - 1:
                    continue
                band_bottom = header_center_y - text_h * pixel_size * 0.5
                band_top = header_center_y + text_h * pixel_size * 0.5
                spans = frame_header_open_spans(
                    settings, frame, usable_left, usable_right,
                    band_bottom, band_top, frame_depth)
                if not spans:
                    continue
                chosen_span = max(spans, key=lambda span: span[1] - span[0])
                available_px = (chosen_span[1] - chosen_span[0]) / pixel_size - 8
                if available_px <= 0:
                    continue
                lock_extra = _lock_extra(frame, text_h)
                while label_text and (blf.dimensions(0, label_text + '…')[0]
                                      + lock_extra) > available_px:
                    label_text = label_text[:-1]
                label_text = label_text + '…' if label_text else '…'
                text_w, text_h = blf.dimensions(0, label_text)
                text_w += lock_extra
                if text_w > available_px:
                    continue
            x_mid_reg, _ = region.view2d.view_to_region(
                (chosen_span[0] + chosen_span[1]) * 0.5, header_center_y, clip=False)
            x_text = x_mid_reg - text_w * 0.5
            y_text = y_hbot_reg + (header_screen_h - text_h) * 0.5
            if frame.is_locked:
                lock_size = text_h
                _draw_lock_icon(x_text, y_text, lock_size)
                x_text += lock_size * 1.35
            clip_left, _ = region.view2d.view_to_region(chosen_span[0], header_center_y,
                                                         clip=False)
            clip_right, _ = region.view2d.view_to_region(chosen_span[1], header_center_y,
                                                          clip=False)
            blf.color(0, 1.0, 1.0, 1.0, 0.95)
            blf.enable(0, blf.CLIPPING)
            blf.clipping(0, clip_left, y_hbot_reg + 2,
                         clip_right, y_top_reg - 2)
            shadow_enabled = enable_soft_text_shadow((1.0, 1.0, 1.0))
            try:
                draw_canvas_text(0, label_text, x_text, y_text,
                                 (1.0, 1.0, 1.0, 0.95), font_size)
            finally:
                if shadow_enabled:
                    disable_soft_text_shadow()
                blf.disable(0, blf.CLIPPING)
    card_rects = []
    for text_index in text_card_draw_indices(settings):
        text_item = settings.images[text_index]
        x0, y0, x1, y1 = _region_bounds(text_item, region.view2d)
        if x1 <= 0 or y1 <= 0 or x0 >= region.width or y0 >= region.height:
            continue
        card_rects.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        # Paint each card and its text together so the next card covers both.
        if text_item.text_compare:
            from .gpu_compare import draw_compare_overlay
            try:
                draw_compare_overlay(text_item, region, settings,
                                     (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
            except Exception as exc:
                print(f"Kanvas comparison: {exc}")
            continue
        draw_text_card(text_item, region=region, grip=not export)
        draw_text_label(text_item, region)
        if export:
            continue
        from .gpu_common import get_prefs
        prefs = get_prefs()
        if prefs is None or getattr(prefs, 'show_text_edit_button', True):
            from .gpu_text import draw_text_edit_button
            draw_text_edit_button(text_item, region)
    try:
        from .gpu_markup_labels import draw_markup_labels
        draw_markup_labels(settings, region, card_rects)
    except Exception as exc:
        print(f"Kanvas color names: {exc}")
    if export:
        return  # the rest is handles, focus, badges and buttons: interface
    draw_text_anchor_handles(settings, region)
    # Editing focus: everything drawn so far is dimmed around the edited item; the
    # mode badges and panels below stay bright.
    try:
        from .gpu_focus import draw_focus_dim
        draw_focus_dim(settings, region)
    except Exception as exc:
        print(f"Kanvas editing focus: {exc}")
    try:
        from .gpu_shape import draw_vertex_edit_overlay
        draw_vertex_edit_overlay(settings, area, region)
    except Exception as exc:
        print(f"Kanvas vertex edit overlay: {exc}")
    from .gpu_mode_switch import draw_mode_switch
    draw_mode_switch(settings, area, region)
    from ...operators.ops_focus import recenter_prompt
    prompt = recenter_prompt(settings, area, region)
    if prompt is not None:
        draw_recenter_prompt(prompt)
    # POST_PIXEL runs after the canvas cards, so the active drag box stays
    # visible even when it crosses a checklist or text card. Keep the normal
    # text-card redraw path free of box-selection work.
    if settings.show_box_sel:
        try:
            draw_selection_box(settings, region)
        except Exception:
            pass


def _in_draw_pass(func):
    def wrapper(*args):
        begin_draw_pass()
        try:
            return func(*args)
        finally:
            end_draw_pass()
    wrapper.__name__ = func.__name__
    return wrapper


draw_callback_px = _in_draw_pass(_draw_callback_px)
draw_frame_labels = _in_draw_pass(_draw_frame_labels)


class KanvasDrawHandler:
    _handler = None
    _label_handler = None
    _registry_key = "k_tools_kanvas.draw_handlers"

    @classmethod
    def add_handler(cls):
        namespace = bpy.app.driver_namespace
        registered = namespace.get(cls._registry_key)
        if registered == (cls._handler, cls._label_handler) and cls._handler is not None:
            return
        if registered:
            for handle in registered:
                try:
                    bpy.types.SpaceNodeEditor.draw_handler_remove(handle, 'WINDOW')
                except (RuntimeError, ValueError):
                    pass
        cls._handler = bpy.types.SpaceNodeEditor.draw_handler_add(
            draw_callback_px, (), 'WINDOW', 'POST_VIEW'
        )
        cls._label_handler = bpy.types.SpaceNodeEditor.draw_handler_add(
            draw_frame_labels, (), 'WINDOW', 'POST_PIXEL'
        )
        namespace[cls._registry_key] = (cls._handler, cls._label_handler)

    @classmethod
    def remove_handler(cls):
        namespace = bpy.app.driver_namespace
        if namespace.get(cls._registry_key) == (cls._handler, cls._label_handler):
            namespace.pop(cls._registry_key, None)
        if cls._handler is not None:
            bpy.types.SpaceNodeEditor.draw_handler_remove(cls._handler, 'WINDOW')
            cls._handler = None
        if cls._label_handler is not None:
            bpy.types.SpaceNodeEditor.draw_handler_remove(cls._label_handler, 'WINDOW')
            cls._label_handler = None


def register():
    KanvasDrawHandler.add_handler()


def unregister():
    KanvasDrawHandler.remove_handler()
    clear_texture_cache()
    from .gpu_mask import clear_mask_cache
    clear_mask_cache()
    from .gpu_markup import clear_markup_cache
    clear_markup_cache()
    from .gpu_markup_labels import clear_label_cache
    clear_label_cache()
