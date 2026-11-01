"""Blender 5.3 smoke test for the optional Kanvas background and grid."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
import gpu
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.preferences import KanvasPreferences
from k_tools_kanvas.utils.gpu import gpu_grid


addon.register()
try:
    props = KanvasPreferences.bl_rna.properties
    assert props['canvas_background_enabled'].default is False
    assert props['canvas_grid_enabled'].default is False
    assert gpu_grid.native_node_grid_levels(0.5)[0] == (20.0, 1.0)
    assert gpu_grid.native_node_grid_levels(3.125)[0] == (100.0, 1.0)
    for pixel_size in (0.5, 1.0, 2.0, 3.124, 3.126, 8.0):
        (fine_step, fine_weight), (coarse_step, coarse_weight) = (
            gpu_grid.native_node_grid_levels(pixel_size))
        assert coarse_step == fine_step * 5.0
        assert abs(fine_weight + coarse_weight - 1.0) < 1e-9
        assert 0.0 <= fine_weight <= 1.0
        assert 0.0 <= coarse_weight <= 1.0
    before = gpu_grid.native_node_grid_levels(3.124)[1][1]
    after = gpu_grid.native_node_grid_levels(3.126)[0][1]
    assert before > 0.999 and after > 0.999
    assert gpu_grid._grid_coordinates(-50, 50, 20) == [-40, -20, 0, 20, 40]

    prefs = SimpleNamespace(
        canvas_background_enabled=False,
        canvas_background_color=(0.1, 0.2, 0.3),
        canvas_grid_enabled=False,
        canvas_grid_color=(0.5, 0.6, 0.7, 0.5),
    )
    gpu_grid.get_prefs = lambda: prefs
    gpu.init()
    offscreen = gpu.types.GPUOffScreen(256, 256)
    try:
        with offscreen.bind():
            gpu.matrix.push_projection()
            gpu.matrix.load_projection_matrix(Matrix((
                (2 / 256, 0, 0, -1),
                (0, 2 / 256, 0, -1),
                (0, 0, 1, 0),
                (0, 0, 0, 1),
            )))
            for solid, grid in ((False, False), (True, False),
                                (False, True), (True, True)):
                prefs.canvas_background_enabled = solid
                prefs.canvas_grid_enabled = grid
                for pixel_size in (0.5, 1.0, 2.0, 4.0):
                    gpu_grid.draw_canvas_backdrop((0, 0, 256, 256), pixel_size)
            gpu.matrix.pop_projection()
    finally:
        offscreen.free()
    print('CANVAS BACKDROP PASS')
finally:
    addon.unregister()
