"""Canvas-space bounds shared by layout and hit testing, and the stacking order."""

import math

# --- stacking order ------------------------------------------------------------------
# The item list is the stacking order: the top of the list is the front of the canvas.
# The list is a tree (frames and groups hold their children), and siblings are sorted
# by `z_index`, higher in front. Drawing and picking follow the same tree, so a frame
# and everything in it move up and down the stack together. Images and shapes mix
# freely; text cards and arrows are drawn above them, frames behind their content.

_stack_cache = {}


def stack_order(settings):
    """Indices of every item, front to back, depth first through frames and groups."""
    images = settings.images
    signature = tuple((item.z_index, item.parent_frame, item.item_type,
                       item.frame_node_name if item.item_type == 'FRAME' else '')
                      for item in images)
    key = settings.as_pointer()
    cached = _stack_cache.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    frames = {item.frame_node_name: index for index, item in enumerate(images)
              if item.item_type == 'FRAME'}
    children = {}
    for index, item in enumerate(images):
        parent = item.parent_frame
        if parent not in frames or frames[parent] == index:
            parent = ''
        children.setdefault(parent, []).append(index)
    for siblings in children.values():
        siblings.sort(key=lambda index: (-images[index].z_index, index))
    order, visited = [], set()

    def visit(index):
        if index in visited:
            return
        visited.add(index)
        order.append(index)
        item = images[index]
        if item.item_type == 'FRAME':
            for child in children.get(item.frame_node_name, ()):
                visit(child)

    for index in children.get('', ()):
        visit(index)
    order.extend(index for index in range(len(images)) if index not in visited)  # cycles
    if len(_stack_cache) > 64:
        _stack_cache.clear()
    _stack_cache[key] = (signature, order)
    return order


def _back_to_front(settings, wanted):
    images = settings.images
    return [index for index in reversed(stack_order(settings)) if wanted(images[index])]


def siblings_of(settings, item):
    """Items that share `item`'s parent (itself included), front to back."""
    images = settings.images
    frames = {other.frame_node_name for other in images if other.item_type == 'FRAME'}
    parent = item.parent_frame if item.parent_frame in frames else ''
    return [images[index] for index in stack_order(settings)
            if (images[index].parent_frame if images[index].parent_frame in frames else '')
            == parent]


def front_z(settings, parent=''):
    """A layer above every item (new items go to the front)."""
    return max((item.z_index for item in settings.images), default=0) + 1


def text_card_draw_indices(settings):
    """Return visible cards in paint order, with the active card on top."""
    indices = _back_to_front(settings, lambda item: item.item_type == 'TEXT'
                             and item.show_in_editor)
    active = settings.active_image_index
    if active in indices and settings.images[active].is_selected:
        indices.remove(active)
        indices.append(active)
    return indices


def shape_draw_indices(settings):
    """Return visible shapes in paint order (back first)."""
    return _back_to_front(settings, lambda item: item.item_type == 'SHAPE'
                          and item.show_in_editor)


def image_draw_indices(settings):
    """Return visible images in paint order (back first)."""
    return _back_to_front(settings, lambda item: item.item_type == 'IMAGE'
                          and item.show_in_editor and bool(item.image_data))


def layer_draw_indices(settings):
    """Images and shapes together, in paint order (back first): they share one stack."""
    return _back_to_front(settings, lambda item: item.show_in_editor and (
        item.item_type == 'SHAPE' or (item.item_type == 'IMAGE' and bool(item.image_data))))


def item_bounds(item):
    kind = getattr(item, 'item_type', 'IMAGE')
    if kind == 'TEXT':
        x, y = item.location
        half_w = item.text_width * item.text_scale * 0.5
        half_h = item.text_height * item.text_scale * 0.5
        return x - half_w, y - half_h, x + half_w, y + half_h
    if kind == 'SHAPE':
        from .shape_geometry import bounds
        return bounds(item)
    if kind == 'FRAME':
        x, y = item.location
        return x, y - item.frame_height, x + item.frame_width, y
    image = item.image_data
    if image is None or image.size[0] <= 0 or image.size[1] <= 0:
        return None
    from .item_crop import box_size
    box_w, box_h = box_size(item, image.size[0], image.size[1])      # the crop, if any
    half_w = abs(box_w * item.scale_xy[0] * item.scale_master) * 0.5
    half_h = abs(box_h * item.scale_xy[1] * item.scale_master) * 0.5
    shear_x, shear_y = item.shear_xy
    angle = math.radians(item.rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    extent_x = abs(cos_a - sin_a * shear_y) * half_w + abs(cos_a * shear_x - sin_a) * half_h
    extent_y = abs(sin_a + cos_a * shear_y) * half_w + abs(sin_a * shear_x + cos_a) * half_h
    x, y = item.location
    return x - extent_x, y - extent_y, x + extent_x, y + extent_y
