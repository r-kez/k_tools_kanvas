"""Editing an overlay in the 3D View: what is under the pointer, the rotation of the drawn
quad, scaling around the middle, the frame key, the shortcuts and the operators behind them."""

import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils import overlay_3d as o

addon.register()
rect = (100.0, 100.0, 300.0, 200.0)             # 200 x 100, middle (200, 150)


def close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# rotating points
assert close(o.rotate_point((300.0, 150.0), (200.0, 150.0), math.pi / 2), (200.0, 250.0))
assert close(o.rotate_point((5.0, 7.0), (1.0, 1.0), 0.0), (5.0, 7.0))
assert close(o.rect_center(rect), (200.0, 150.0))

# what is under the pointer: inside the rectangle, turned with it
assert o.contains(rect, (200, 150)) and not o.contains(rect, (50, 50))
quarter = math.pi / 2
assert o.contains(rect, (240, 150), quarter)       # the turned overlay is 100 wide, 200 tall
assert not o.contains(rect, (260, 150), quarter)
assert not o.contains(rect, (290, 150), quarter)   # inside the unturned rectangle only

# the drawn quad: turned around the middle, same UV order as draw_quad
points, uvs = o.rotated_quad(rect, (0.0, 0.0, 1.0, 1.0), 0.0)
assert close(points[0], (100, 100)) and close(points[2], (300, 200))
assert uvs == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
points, _ = o.rotated_quad(rect, (0.0, 0.0, 1.0, 1.0), quarter)
assert close(points[0], (250.0, 50.0)) and close(points[2], (150.0, 250.0)), points
mirrored = o.rotated_quad(rect, (1.0, 0.0, 0.0, 1.0), 0.3)[1]
assert mirrored[0] == (1.0, 0.0) and mirrored[1] == (0.0, 0.0)

# scaling around the middle: the overlay grows from where it is, not from its anchor
area = (1000.0, 500.0)
for anchor in ('CENTER', 'TOP_RIGHT', 'BOTTOM_LEFT'):
    start = o.overlay_rect(*area, 2.0, 0.4, anchor, (20.0, -10.0))
    offset = o.scaled_keep_center(area, 2.0, 0.4, 0.8, anchor, (20.0, -10.0), start)
    grown = o.overlay_rect(*area, 2.0, 0.8, anchor, offset)
    assert close(o.rect_center(grown), o.rect_center(start), 1e-6), anchor
    assert abs((grown[2] - grown[0]) - 2 * (start[2] - start[0])) < 1e-6

# the frame key: the modifiers of the Move shortcut (Alt by default)
class Event:
    def __init__(self, alt=False, ctrl=False, shift=False):
        self.alt, self.ctrl, self.shift = alt, ctrl, shift

assert o.hint_held(Event(alt=True)) and not o.hint_held(Event(ctrl=True))
assert not o.hint_held(Event())
assert o.hint_modifiers() == (False, False, True)

# the shortcuts are registered and listed for the preferences
from k_tools_kanvas import keymap
keymap.rebuild()
bpy.context.window_manager.keyconfigs.update()
listed = {label for label, *_ in keymap.iter_ui_bindings(bpy.context.window_manager)}
assert {'Overlay: Move (drag)', 'Overlay: Rotate (drag)', 'Overlay: Scale (drag)',
        'Overlay: Reset', 'Overlay: Opacity up (wheel)',
        'Overlay: Opacity down (wheel)'} <= listed, listed
from k_tools_kanvas import preferences
assert 'overlay_edit_key' not in preferences.KanvasPreferences.__annotations__

# properties and the one-shot operator exist; nothing runs without a 3D View
scene = bpy.context.scene
entry = scene.kanvas_references.add()
entry.kind = 'OVERLAY'
assert entry.rotation == 0.0 and hasattr(bpy.ops.kanvas, 'overlay_edit_key') and hasattr(bpy.ops.kanvas, 'overlay_edit')
entry.rotation = 1.0
assert abs(entry.rotation - 1.0) < 1e-6
assert not bpy.ops.kanvas.overlay_edit_key.poll()      # no 3D View area here
o.reset_overlay(entry)
assert tuple(entry.offset) == (0.0, 0.0) and entry.rotation == 0.0 and entry.size == o.RESET_SIZE

addon.unregister()
print('test_overlay_edit: OK')
