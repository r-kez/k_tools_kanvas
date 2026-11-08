"""A gradient's color ramp (a hidden texture) is saved with the board and comes back
when the file is opened again; removing the shape lets Blender drop the texture."""
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import shape_gradient as sg

addon.register()
try:
    tree = bpy.data.node_groups.new('Saved gradient', 'KanvasNodeTree')
    tree.use_fake_user = True
    item = tree.kanvas_settings.images.add()
    item.item_type, item.item_id, item.name = 'SHAPE', 'shape', 'Shape'
    item.shape_fill_type = 'RADIAL'
    ramp = item.shape_gradient_texture.color_ramp
    ramp.interpolation = 'EASE'
    ramp.elements.new(0.5).color = (1.0, 0.0, 0.0, 1.0)
    wanted = sg.gradient_record(item)
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        path = str(Path(folder) / 'gradient.blend')
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        tree = bpy.data.node_groups['Saved gradient']
        item = tree.kanvas_settings.images[0]
        assert item.shape_gradient_texture is not None, 'the ramp was not saved'
        got = sg.gradient_record(item)
        assert got['ramp'] == wanted['ramp'] and got['type'] == 'RADIAL'
        assert all(abs(a - b) < 1e-6 for x, y in zip(got['stops'], wanted['stops'])
                   for a, b in zip(x, y)), (got, wanted)
        name = item.shape_gradient_texture.name
        tree.kanvas_settings.images.remove(0)
        assert bpy.data.textures[name].users == 0, 'nothing keeps an unused ramp'
        bpy.ops.wm.read_homefile(use_empty=True)
    print('test_gradient_save: OK')
finally:
    addon.unregister()
