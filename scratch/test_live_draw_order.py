"""Live references draw back to front for the view, so a nearer picture covers a farther one
from either side: by distance of their middle, Background first, In Front last."""
import sys
from pathlib import Path
from types import SimpleNamespace

from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon

addon.register()
try:
    from k_tools_kanvas.utils.live_reference_3d import draw_order

    def entry(name, x, y, z, depth='DEFAULT'):
        obj = SimpleNamespace(matrix_world=Matrix.Translation(Vector((x, y, z))),
                              empty_image_depth=depth)
        return SimpleNamespace(name=name, object=obj)

    def view_from(eye):
        # Looking at the origin from `eye`, Z up.
        eye = Vector(eye)
        forward = (-eye).normalized()
        right = forward.cross(Vector((0, 0, 1))).normalized()
        up = right.cross(forward)
        rotation = Matrix((right, up, -forward)).to_4x4()
        return rotation @ Matrix.Translation(-eye)

    near_a, far_b = entry('near', 0, -2, 0), entry('far', 0, 3, 0)
    entries = [near_a, far_b]
    front = SimpleNamespace(view_matrix=view_from((0, -10, 0)))
    assert [e.name for e in draw_order(entries, front)] == ['far', 'near']
    # Seen from the other side the order flips, whatever the list order is.
    behind = SimpleNamespace(view_matrix=view_from((0, 10, 0)))
    assert [e.name for e in draw_order(entries, behind)] == ['near', 'far']
    assert [e.name for e in draw_order(entries[::-1], behind)] == ['near', 'far']
    # Background first and In Front last, whatever the distance.
    background, in_front = entry('back', 0, -5, 0, 'BACK'), entry('top', 0, 5, 0, 'FRONT')
    ordered = [e.name for e in draw_order([in_front, near_a, background, far_b], front)]
    assert ordered == ['back', 'far', 'near', 'top'], ordered
    print('test_live_draw_order: OK')
finally:
    addon.unregister()
