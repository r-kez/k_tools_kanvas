"""Copy Style / Paste Style: only appearance moves, only between items of the same kind."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.operators import ops_style

addon.register()
try:
    tree = bpy.data.node_groups.new('Style', 'KanvasNodeTree')
    settings = tree.kanvas_settings

    def add(kind, name, **props):
        item = settings.images.add()
        item.item_type, item.name, item.item_id = kind, name, name
        if kind == 'IMAGE':
            item.image_data = bpy.data.images.new(name, 4, 4)
        for key, value in props.items():
            setattr(item, key, value)
        return item

    source = add('TEXT', 'source', text_color=(0.9, 0.2, 0.1), text_background=(0.1, 0.1, 0.3),
                 text_opacity=0.6, text_font_size=30, location=(10, 20), text_width=500)
    source.text_lines.add().value = 'source text'
    target = add('TEXT', 'target', location=(300, 400), text_width=240)
    target.text_lines.add().value = 'target text'
    other_text = add('TEXT', 'unselected')
    picture = add('IMAGE', 'picture', brightness=1.7, opacity=0.4)
    frame = add('FRAME', 'frame', frame_color=(0.2, 0.8, 0.4), frame_opacity=0.7)

    assert ops_style.style_kind() is None
    assert ops_style.copy_style(source) and ops_style.style_kind() == 'TEXT'

    target.is_selected = True
    picture.is_selected = True
    frame.is_selected = True
    changed = [ops_style.apply_style(item) for item in (target, picture, frame)]
    assert changed == [True, False, False], 'only an item of the same kind is touched'
    assert tuple(round(c, 3) for c in target.text_color) == (0.9, 0.2, 0.1)
    assert abs(target.text_opacity - 0.6) < 1e-6 and target.text_font_size == 30
    assert tuple(target.location) == (300, 400) and target.text_width == 240, 'position and size stay'
    assert target.text_lines[0].value == 'target text', 'content stays'
    assert abs(picture.brightness - 1.7) < 1e-5 and frame.frame_opacity > 0.69, 'other kinds are untouched'
    print('TEXT STYLE OK')

    # Images carry their display adjustments; frames their color.
    picture.value_gray, picture.value_levels, picture.color_tint = True, 3, (0.8, 0.9, 1.0)
    other_image = add('IMAGE', 'other image')
    assert ops_style.copy_style(picture) and ops_style.apply_style(other_image)
    assert (other_image.brightness, other_image.value_levels) == (picture.brightness, 3)
    assert other_image.value_gray and abs(other_image.opacity - 0.4) < 1e-6
    assert ops_style.copy_style(frame) and ops_style.apply_style(add('FRAME', 'second frame'))
    print('IMAGE AND FRAME STYLE OK')

    assert ops_style.copy_style(add('IMAGE', 'arrowless')) is True
    class Unsupported:
        item_type = 'ARROW'
    assert ops_style.copy_style(Unsupported()) is False
    ops_style.clear_style()
    assert ops_style.style_kind() is None and not ops_style.apply_style(target)

    assert hasattr(bpy.ops.kanvas, 'copy_style') and hasattr(bpy.ops.kanvas, 'paste_style')
    print('COPY PASTE STYLE OK')
finally:
    addon.unregister()
