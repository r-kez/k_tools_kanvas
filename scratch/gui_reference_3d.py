"""Send to 3D View as an image file (Live off), on a real GPU: a masked image becomes a
reference image empty of the
cropped size at the 3D cursor, facing its view, in the Kanvas References collection,
listed in the scene; a blueprint set gets Front and Right; Update Reference follows a
new mask in the same image; an unsaved file packs the picture, a saved one writes it
to the assets folder; removing deletes the empty and its image; an empty deleted in
the 3D View drops out of the list; Show in Kanvas selects the image on its board.

    blender --factory-startup -P scratch/gui_reference_3d.py
Prints GUIREF RESULT OK or FAIL. Needs a window (not -b).
"""

import math
import os
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def run():
    import numpy as np
    from k_tools_kanvas.utils import reference_3d as ref
    addon.register()
    window = bpy.context.window_manager.windows[0]
    areas = sorted(window.screen.areas, key=lambda a: a.width * a.height, reverse=True)
    area = areas[0]
    area.type = 'NODE_EDITOR'
    area.ui_type = 'KanvasNodeTree'
    tree = bpy.data.node_groups.new('GUI refs', 'KanvasNodeTree')
    space = area.spaces.active
    space.node_tree = tree
    region = next(r for r in area.regions if r.type == 'WINDOW')
    settings = tree.kanvas_settings
    scene = bpy.context.scene
    scene.cursor.location = (1.0, 2.0, 3.0)

    def add_image(item_id, width, height, color):
        image = bpy.data.images.new(item_id, width, height, alpha=True)
        pixels = np.zeros((height, width, 4), dtype=np.float32)
        pixels[:] = color
        image.pixels.foreach_set(pixels.ravel())
        item = settings.images.add()
        item.item_type, item.item_id, item.name = 'IMAGE', item_id, item_id.title()
        item.image_data = image
        item.rotation = 20.0
        return item_id

    def by_id(item_id):
        return next(i for i in settings.images if i.item_id == item_id)

    def override():
        return bpy.context.temp_override(window=window, area=area, region=region,
                                         space_data=space)

    add_image('front', 400, 200, (1, 0, 0, 1))
    add_image('side', 300, 300, (0, 0, 1, 1))
    front = by_id('front')
    polygon = front.mask_polygons.add()
    for uv in ((0.1, 0.2), (0.4, 0.2), (0.4, 0.6), (0.1, 0.6)):
        polygon.vertices.add().uv = uv
    polygon.sequence = 1
    front.mask_enabled = True
    front.is_selected = True
    settings.active_image_index = 0

    # --- One masked image -------------------------------------------------------------
    with override():
        result = bpy.ops.kanvas.add_3d_reference('EXEC_DEFAULT', live=False, size=2.0, opacity=0.5)
    check(result == {'FINISHED'}, f'add {result}')
    check(len(scene.kanvas_references) == 1, f'listed {len(scene.kanvas_references)}')
    obj = scene.kanvas_references[0].object
    check(obj is not None and obj.empty_display_type == 'IMAGE', 'an image empty')
    check(obj.name in bpy.data.collections[ref.COLLECTION_NAME].objects, 'in the collection')
    check(tuple(obj.data.size) == (120, 80), f'cropped picture {tuple(obj.data.size)}')
    check(obj.data.packed_file is not None, 'packed in an unsaved file')
    check(tuple(round(v, 4) for v in obj.location) == (1.0, 2.0, 3.0), f'at the cursor {obj.location[:]}')
    check(abs(obj.rotation_euler.x - math.radians(90)) < 1e-5 and abs(obj.rotation_euler.z) < 1e-5,
          f'faces front {obj.rotation_euler[:]}')
    check(abs(obj.empty_display_size - 2.0) < 1e-6 and obj.use_empty_image_alpha
          and abs(obj.color[3] - 0.5) < 1e-6, 'size and opacity')
    check(not obj.show_empty_image_only_axis_aligned and obj.show_empty_image_perspective,
          'as Blender: shown from every angle, perspective too')
    pixel = np.array(obj.data.pixels[:]).reshape(80, 120, 4)[40, 60]
    check(pixel[0] > 0.8 and pixel[2] < 0.1 and pixel[3] > 0.99, f'red picture {pixel}')

    # --- Update after a new mask: same image, new size ---------------------------------
    front = by_id('front')
    for vertex, uv in zip(front.mask_polygons[0].vertices,
                          ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0))):
        vertex.uv = uv
    front.mask_revision += 1
    image = obj.data
    scene.kanvas_reference_index = 0
    result = bpy.ops.kanvas.update_3d_reference()
    check(result == {'FINISHED'}, f'update {result}')
    check(obj.data == image and tuple(image.size) == (200, 200), f'updated size {tuple(image.size)}')

    # --- A blueprint set of two -------------------------------------------------------
    by_id('side').is_selected = True
    with override():
        result = bpy.ops.kanvas.add_3d_reference('EXEC_DEFAULT', live=False)
    check(result == {'FINISHED'} and len(scene.kanvas_references) == 3,
          f'blueprint {result} {len(scene.kanvas_references)}')
    views = [entry.view for entry in scene.kanvas_references[1:]]
    check(views == ['FRONT', 'RIGHT'], f'views {views}')
    right = scene.kanvas_references[2].object
    check(abs(right.rotation_euler.z - math.radians(90)) < 1e-5, f'faces right {right.rotation_euler[:]}')
    check(tuple(right.data.size) == (300, 300), f'side picture {tuple(right.data.size)}')

    # --- Show in Kanvas -----------------------------------------------------------------
    for item in settings.images:
        item.is_selected = False
    scene.kanvas_reference_index = 2
    check(bpy.context.view_layer.objects.active == right, 'clicking the row selects the empty')
    result = bpy.ops.kanvas.show_reference_in_kanvas()
    check(result == {'FINISHED'} and by_id('side').is_selected and not by_id('front').is_selected,
          f'show in kanvas {result}')

    # --- Deleted in the 3D View, removed from the list -----------------------------------
    for collection in list(right.users_collection):
        collection.objects.unlink(right)
    check(ref.is_deleted(scene.kanvas_references[2]), 'unlinked counts as deleted')
    ref.prune(scene)
    check(len(scene.kanvas_references) == 2, f'pruned {len(scene.kanvas_references)}')

    # --- Remove ---------------------------------------------------------------------------
    scene.kanvas_reference_index = 1
    removed = scene.kanvas_references[1].object.name
    image_name = scene.kanvas_references[1].object.data.name
    result = bpy.ops.kanvas.remove_3d_reference()
    check(result == {'FINISHED'} and removed not in bpy.data.objects
          and image_name not in bpy.data.images, f'remove {result}')

    # --- Orphan: the image left the board -----------------------------------------------
    settings.images.remove(next(i for i, item in enumerate(settings.images)
                                if item.item_id == 'front'))
    scene.kanvas_reference_index = 0
    check(not bpy.ops.kanvas.update_3d_reference.poll(), 'no update without the image')

    # --- Saved file: written to the assets folder ----------------------------------------
    folder = tempfile.mkdtemp()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, 'refs.blend'))
    settings = bpy.data.node_groups['GUI refs'].kanvas_settings
    for item in settings.images:
        item.is_selected = item.item_id == 'side'
    with override():
        result = bpy.ops.kanvas.add_3d_reference('EXEC_DEFAULT', live=False)
    obj = bpy.context.scene.kanvas_references[-1].object
    written = os.path.join(folder, 'assets', 'kanvas', 'references')
    check(result == {'FINISHED'} and obj.data.packed_file is None
          and obj.data.filepath.startswith('//'), f'saved file {obj.data.filepath}')
    check(os.path.isdir(written) and len(os.listdir(written)) == 1, f'written to {written}')
    print('GUIREF done')


def tick():
    try:
        run()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        errors.append(repr(exc))
    print('GUIREF RESULT', 'OK' if not errors else 'FAIL')
    for error in errors:
        print('  ', error)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(tick, first_interval=1.0)
