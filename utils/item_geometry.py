"""Canvas-space bounds shared by layout and hit testing."""

import math


def text_card_draw_indices(settings):
    """Return visible cards in paint order, with the active card on top."""
    indices = sorted(
        (index for index, item in enumerate(settings.images)
         if item.item_type == 'TEXT' and item.show_in_editor),
        key=lambda index: (settings.images[index].z_index, index),
    )
    active = settings.active_image_index
    if active in indices and settings.images[active].is_selected:
        indices.remove(active)
        indices.append(active)
    return indices


def shape_draw_indices(settings):
    """Return visible shapes in paint order, with a single active selection on top."""
    indices = sorted(
        (index for index, item in enumerate(settings.images)
         if item.item_type == 'SHAPE' and item.show_in_editor),
        key=lambda index: (settings.images[index].z_index, index),
    )
    active = settings.active_image_index
    if active in indices and settings.images[active].is_selected:
        indices.remove(active)
        indices.append(active)
    return indices


def image_draw_indices(settings):
    """Return images in paint order, lifting only a single active selection."""
    indices = sorted(
        (index for index, item in enumerate(settings.images)
         if item.item_type == 'IMAGE' and item.show_in_editor and item.image_data),
        key=lambda index: (settings.images[index].z_index, index),
    )
    active = settings.active_image_index
    selected = [index for index in indices if settings.images[index].is_selected]
    if len(selected) == 1 and active == selected[0]:
        indices.remove(active)
        indices.append(active)
    return indices


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
    half_w = abs(image.size[0] * item.scale_xy[0] * item.scale_master) * 0.5
    half_h = abs(image.size[1] * item.scale_xy[1] * item.scale_master) * 0.5
    shear_x, shear_y = item.shear_xy
    angle = math.radians(item.rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    extent_x = abs(cos_a - sin_a * shear_y) * half_w + abs(cos_a * shear_x - sin_a) * half_h
    extent_y = abs(sin_a + cos_a * shear_y) * half_w + abs(sin_a * shear_x + cos_a) * half_h
    x, y = item.location
    return x - extent_x, y - extent_y, x + extent_x, y + extent_y
