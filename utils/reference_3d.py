"""Kanvas images in the 3D View as reference image empties (overlays are in
`overlay_3d`).

The picture comes from `item_picture` (the image as edited on the board, upright, cropped
to its mask). It is written as a PNG and loaded as a Blender image: into the assets
folder next to the saved .blend (so the file stays small), or packed into an unsaved
file. A generated image that only lived in memory would be flagged as unsaved on every
save and quit.

Each reference is listed in `scene.kanvas_references` with the board and item it came
from and how its picture was made, so Update Reference can make it again.
"""

import math
import os
import tempfile

COLLECTION_NAME = 'Kanvas References'
DEFAULTS_VERSION = 1
REFERENCE_FOLDER = 'references'

# Rotation (Euler XYZ, degrees) that turns an image empty, which faces +Z, toward the
# viewer of each view, upright on screen.
VIEW_ROTATIONS = {
    'FRONT': (90.0, 0.0, 0.0),
    'BACK': (90.0, 0.0, 180.0),
    'RIGHT': (90.0, 0.0, 90.0),
    'LEFT': (90.0, 0.0, -90.0),
    'TOP': (0.0, 0.0, 0.0),
    'BOTTOM': (180.0, 0.0, 0.0),
}
VIEW_ITEMS = (
    ('FRONT', 'Front', 'Facing the front view (Numpad 1)'),
    ('BACK', 'Back', 'Facing the back view (Ctrl Numpad 1)'),
    ('RIGHT', 'Right', 'Facing the right view (Numpad 3)'),
    ('LEFT', 'Left', 'Facing the left view (Ctrl Numpad 3)'),
    ('TOP', 'Top', 'Facing the top view (Numpad 7)'),
    ('BOTTOM', 'Bottom', 'Facing the bottom view (Ctrl Numpad 7)'),
    ('VIEW', 'Current View', 'Facing the current angle of the 3D View'),
)
# Views given in turn to the images of a blueprint set.
BLUEPRINT_ORDER = ('FRONT', 'RIGHT', 'TOP', 'BACK', 'LEFT', 'BOTTOM')
DEPTH_ITEMS = (
    ('DEFAULT', 'Reference', 'Drawn in the scene, hidden behind objects in front of it'),
    ('BACK', 'Background', 'Drawn behind everything'),
    ('FRONT', 'In Front', 'Drawn over everything'),
)


def board_item(tree, item_id):
    """The board item a reference came from, None when it is gone."""
    if tree is None or not item_id:
        return None
    return next((item for item in tree.kanvas_settings.images if item.item_id == item_id), None)


def view_rotation(view, context=None):
    """Euler rotation (radians) for a view; 'VIEW' reads the 3D View of the window."""
    from mathutils import Euler
    if view == 'VIEW':
        region_3d = _region_3d(context)
        if region_3d is not None:
            return region_3d.view_rotation.to_euler()
        view = 'FRONT'
    return Euler([math.radians(angle) for angle in VIEW_ROTATIONS[view]], 'XYZ')


def _region_3d(context):
    """The 3D View the user looks at: the one in context, else the largest in the
    window."""
    if context is None:
        return None
    space = getattr(context, 'space_data', None)
    if space is not None and space.type == 'VIEW_3D' and space.region_3d is not None:
        return space.region_3d
    window = getattr(context, 'window', None)
    screen = window.screen if window else getattr(context, 'screen', None)
    if screen is None:
        return None
    areas = [area for area in screen.areas if area.type == 'VIEW_3D']
    if not areas:
        return None
    area = max(areas, key=lambda a: a.width * a.height)
    return area.spaces.active.region_3d


# --- The picture as a Blender image ------------------------------------------------------

def _folder():
    """Where reference pictures are written: the assets folder of a saved file, None for
    an unsaved one (the picture is packed)."""
    import bpy
    if not bpy.data.filepath:
        return None
    from .gpu.gpu_common import get_prefs
    prefs = get_prefs()
    relative = getattr(prefs, 'assets_folder', '//assets/kanvas') if prefs else '//assets/kanvas'
    return os.path.join(bpy.path.abspath(relative), REFERENCE_FOLDER)


def _file_name(item):
    import bpy
    base = bpy.path.clean_name(item.name or (item.image_data.name if item.image_data else 'image'))
    return f'{base}_{item.item_id[:8]}.png'


def store_picture(picture, item, image=None):
    """Write `picture` and return the Blender image showing it: `image` refreshed in
    place (an Update), or a new one."""
    import bpy
    from .board_render import write_png
    folder = _folder()
    packed = folder is None
    if packed:
        folder = tempfile.mkdtemp(prefix='kanvas_ref_')
    else:
        os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, _file_name(item))
    write_png(path, picture)
    if image is None:
        image = bpy.data.images.load(path, check_existing=False)
        image.name = f'Kanvas Ref {item.name}'
    else:
        if image.packed_file is not None:
            image.unpack(method='REMOVE')
        image.filepath = path
        image.reload()
    if packed:
        image.pack()
    else:
        try:
            image.filepath = bpy.path.relpath(path)
        except ValueError:      # another drive than the .blend: keep the absolute path
            pass
    image['kanvas_reference'] = True
    return image


def make_picture(tree, entry):
    """The picture of an entry's item, made with the entry's options. Raises ValueError
    with a message for the user."""
    from .item_picture import MAX_SIDE, picture_size, render_item
    item = board_item(tree, entry.item_id)
    if item is None:
        raise ValueError('The image is no longer on its Kanvas board')
    size = picture_size(item, 1.0, entry.crop_to_mask, entry.keep_stretch)
    if size is None:
        raise ValueError('The mask hides the whole image')
    scale = min(1.0, MAX_SIDE / max(size))
    return item, render_item(tree.kanvas_settings, item, scale, entry.crop_to_mask,
                             entry.include_markup, entry.keep_stretch)


# --- The empty ---------------------------------------------------------------------------

def reference_collection(scene):
    """The scene's Kanvas References collection, made and linked when missing."""
    import bpy
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION_NAME)
    if collection.name not in scene.collection.children:
        scene.collection.children.link(collection)
    return collection


def apply_display(obj, size, depth, opacity, axis_aligned, perspective, view):
    obj.empty_display_type = 'IMAGE'
    obj.empty_display_size = size
    obj.empty_image_offset = (-0.5, -0.5)
    obj.empty_image_depth = depth
    obj.empty_image_side = 'DOUBLE_SIDED'
    obj.use_empty_image_alpha = opacity < 1.0
    obj.color[3] = opacity
    obj.show_empty_image_orthographic = True
    obj.show_empty_image_perspective = perspective
    # Only the axis views have an axis: a reference at an angle would never show.
    obj.show_empty_image_only_axis_aligned = axis_aligned and view != 'VIEW'


def create_empty(context, image, name, view, location, size, depth, opacity,
                 axis_aligned, perspective):
    import bpy
    obj = bpy.data.objects.new(name, None)
    apply_display(obj, size, depth, opacity, axis_aligned, perspective, view)
    obj.data = image
    obj.location = location
    obj.rotation_euler = view_rotation(view, context)
    reference_collection(context.scene).objects.link(obj)
    return obj


def migrate_references():
    """References made before they showed from every angle have Only Axis Aligned on,
    which hides them as soon as the 3D View orbits (perspective included). Turn it off
    once; a choice made afterwards is kept. Returns how many were changed."""
    import bpy
    changed = 0
    for scene in bpy.data.scenes:
        for entry in getattr(scene, 'kanvas_references', ()):
            if entry.defaults_version >= DEFAULTS_VERSION:
                continue
            entry.defaults_version = DEFAULTS_VERSION
            obj = entry.object
            if entry.kind == 'EMPTY' and obj is not None and obj.show_empty_image_only_axis_aligned:
                obj.show_empty_image_only_axis_aligned = False
                changed += 1
    return changed


def is_deleted(entry):
    """An empty deleted in the 3D View is unlinked from every collection but still
    exists, kept alive by the entry's pointer."""
    obj = entry.object
    return entry.kind == 'EMPTY' and (obj is None or not obj.users_collection)


def prune(scene):
    """Forget the entries whose empty was deleted. Not from a draw function."""
    references = scene.kanvas_references
    for index in reversed(range(len(references))):
        if is_deleted(references[index]):
            references.remove(index)
    scene.kanvas_reference_index = min(scene.kanvas_reference_index, len(references) - 1)
