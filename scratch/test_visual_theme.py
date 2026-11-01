"""Smoke test for both GPU canvas styles in Blender 5.3."""

import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
import blf
import gpu
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.preferences import KanvasPreferences
from k_tools_kanvas.utils.gpu import gpu_theme
from k_tools_kanvas.utils.gpu.gpu_frame import draw_kanvas_frame
from k_tools_kanvas.utils.gpu.gpu_selection import draw_selection_box
from k_tools_kanvas.utils.gpu.gpu_text import draw_text_card


addon.register()
try:
    theme_property = KanvasPreferences.bl_rna.properties['visual_theme']
    assert theme_property.default == 'CLASSIC'
    assert KanvasPreferences.bl_rna.properties['text_shadow_enabled'].default
    strength_property = KanvasPreferences.bl_rna.properties['text_shadow_strength']
    assert strength_property.default == 0.5
    spread_property = KanvasPreferences.bl_rna.properties['text_shadow_spread']
    assert spread_property.default == 'TIGHT'
    assert {entry.identifier for entry in spread_property.enum_items} == {
        'TIGHT', 'WIDE', 'OUTLINE', 'DIFFUSE'}
    assert KanvasPreferences.bl_rna.properties['text_shadow_diffuse_reach'].default == 1.0
    assert gpu_theme._shadow_alpha(0.0, 0.45) == 0.0
    assert gpu_theme._shadow_alpha(0.5, 0.45) == 0.45
    assert gpu_theme._shadow_alpha(1.0, 0.45) == 1.0
    theme_items = theme_property.enum_items
    assert theme_items['CLASSIC'] and theme_items['STUDIO'] and theme_items['GLASS']

    points = gpu_theme.rounded_points(0, 0, 100, 50, 20)
    assert len(points) == 20
    assert all(0 <= x <= 100 and 0 <= y <= 50 for x, y in points)
    assert gpu_theme.rounded_points(0, 0, 2, 2, 20)[0][1] >= 0
    assert len(gpu_theme.rounded_points(0, 0, 20, 20, 0)) == len(points)

    tree = bpy.data.node_groups.new('Theme smoke', 'KanvasNodeTree')
    card = tree.kanvas_settings.images.add()
    card.item_type = 'TEXT'
    card.location = (20, 180)
    card.text_width = 170
    card.text_height = 90
    frame = tree.kanvas_settings.images.add()
    frame.item_type = 'FRAME'
    frame.location = (10, 200)
    frame.frame_width = 200
    frame.frame_height = 150

    prefs = SimpleNamespace(visual_theme='CLASSIC',
                            color_selection=(0.2, 0.8, 0.9, 1.0),
                            text_shadow_enabled=True,
                            text_shadow_strength=0.5,
                            text_shadow_spread='TIGHT',
                            text_shadow_diffuse_reach=1.0)
    gpu_theme.get_prefs = lambda: prefs
    gpu.init()
    offscreen = gpu.types.GPUOffScreen(256, 256)
    try:
        with offscreen.bind():
            assert gpu_theme.enable_soft_text_shadow((1.0, 1.0, 1.0))
            gpu_theme.disable_soft_text_shadow()
            assert gpu_theme.enable_soft_text_shadow((0.1, 0.1, 0.1))
            gpu_theme.disable_soft_text_shadow()
            prefs.text_shadow_enabled = False
            assert not gpu_theme.enable_soft_text_shadow((1.0, 1.0, 1.0))
            prefs.text_shadow_enabled = True
            prefs.text_shadow_strength = 0.0
            assert not gpu_theme.enable_soft_text_shadow((1.0, 1.0, 1.0))
            prefs.text_shadow_strength = 1.0
            assert gpu_theme.enable_soft_text_shadow((1.0, 1.0, 1.0))
            gpu_theme.disable_soft_text_shadow()
            for spread in ('WIDE', 'OUTLINE'):
                prefs.text_shadow_spread = spread
                assert gpu_theme.enable_soft_text_shadow((1.0, 1.0, 1.0))
                gpu_theme.disable_soft_text_shadow()
            prefs.text_shadow_spread = 'DIFFUSE'
            assert not gpu_theme.enable_soft_text_shadow((1.0, 1.0, 1.0))
            blf.color(0, 1.0, 1.0, 1.0, 1.0)
            gpu_theme.draw_canvas_text(0, 'Small', 20, 20,
                                       (1.0, 1.0, 1.0, 1.0), 18)
            gpu_theme.draw_canvas_text(0, 'Large', 20, 70,
                                       (1.0, 1.0, 1.0, 1.0), 64)
            prefs.text_shadow_diffuse_reach = 2.0
            gpu_theme.draw_canvas_text(0, 'Large', 20, 140,
                                       (1.0, 1.0, 1.0, 1.0), 64)
            prefs.text_shadow_spread = 'TIGHT'
            gpu.matrix.push_projection()
            gpu.matrix.load_projection_matrix(Matrix((
                (2 / 256, 0, 0, -1),
                (0, 2 / 256, 0, -1),
                (0, 0, 1, 0),
                (0, 0, 0, 1),
            )))
            for style in ('CLASSIC', 'STUDIO', 'GLASS'):
                prefs.visual_theme = style
                assert gpu_theme.studio_enabled() == (style != 'CLASSIC')
                assert gpu_theme.glass_enabled() == (style == 'GLASS')
                draw_kanvas_frame(frame, 1.0)
                draw_text_card(card)
                if style != 'CLASSIC':
                    tiny_view = SimpleNamespace(view_to_region=lambda x, y, clip=False:
                                                (round(x * 0.01), round(y * 0.01)))
                    draw_text_card(card, region=SimpleNamespace(view2d=tiny_view))
                draw_selection_box(SimpleNamespace(show_box_sel=True,
                    box_sel_start=(25, 30), box_sel_end=(150, 120)))
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            # The inset radius becomes zero while the outer border stays round.
            gpu_theme.draw_rounded_border(shader, (10, 10, 30, 30), 1.0,
                                          2.0, (1, 1, 1, 1), antialias=True)
            gpu_theme.draw_rounded_fill(shader, (40, 10, 60, 30), 0.0,
                                        (1, 1, 1, 1), antialias=True)
            gpu_theme.draw_rounded_border(shader, (10, 10, 10, 30), 1.0,
                                          2.0, (1, 1, 1, 1), antialias=True)
            gpu.matrix.pop_projection()
    finally:
        offscreen.free()
    print('VISUAL THEME PASS')
finally:
    addon.unregister()
