import math


def image_intersects_view(item, view_bounds):
    """Test the transformed image rectangle against the visible view-space AABB."""
    image = item.image_data
    width, height = image.size
    if width <= 0 or height <= 0:
        return False

    half_w = abs(width * item.scale_xy[0] * item.scale_master) * 0.5
    half_h = abs(height * item.scale_xy[1] * item.scale_master) * 0.5
    shear_x, shear_y = item.shear_xy
    angle = math.radians(item.rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)

    # The draw shader applies shear, then rotation. Each transformed axis is
    # linear, so its largest extent occurs at a corner of the source rectangle.
    extent_x = abs(cos_a - sin_a * shear_y) * half_w + abs(cos_a * shear_x - sin_a) * half_h
    extent_y = abs(sin_a + cos_a * shear_y) * half_w + abs(sin_a * shear_x + cos_a) * half_h
    center_x, center_y = item.location
    min_x, min_y, max_x, max_y = view_bounds

    return (center_x + extent_x >= min_x and center_x - extent_x <= max_x
            and center_y + extent_y >= min_y and center_y - extent_y <= max_y)
