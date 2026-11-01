"""Visual and timing probe for a broad Blender text shadow."""

import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import blf
import bpy
import gpu
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from k_tools_kanvas.utils.gpu import gpu_theme


WIDTH, HEIGHT = 960, 300


def diffuse(text, x, y, size, rings):
    blf.size(0, size)
    blf.color(0, 1, 1, 1, 0)
    blf.enable(0, blf.SHADOW)
    try:
        taps = [(0, 0, 0.12)]
        for radius, alpha in rings:
            taps.extend((round(math.cos(i * math.tau / 8) * radius),
                         round(math.sin(i * math.tau / 8) * radius), alpha)
                        for i in range(8))
        for ox, oy, alpha in taps:
            blf.shadow(0, 5, 0, 0, 0, alpha)
            blf.shadow_offset(0, ox, oy)
            blf.position(0, x, y, 0)
            blf.draw(0, text)
    finally:
        blf.disable(0, blf.SHADOW)
    blf.color(0, 1, 1, 1, 1)
    blf.position(0, x, y, 0)
    blf.draw(0, text)


def normal(text, x, y, size):
    blf.size(0, size)
    blf.color(0, 1, 1, 1, 1)
    blf.shadow(0, 3, 0, 0, 0, 0.45)
    blf.shadow_offset(0, 0, -1)
    blf.enable(0, blf.SHADOW)
    blf.position(0, x, y, 0)
    blf.draw(0, text)
    blf.disable(0, blf.SHADOW)


gpu.init()
offscreen = gpu.types.GPUOffScreen(WIDTH, HEIGHT)
try:
    with offscreen.bind():
        gpu.matrix.push_projection()
        gpu.matrix.load_projection_matrix(Matrix((
            (2 / WIDTH, 0, 0, -1), (0, 2 / HEIGHT, 0, -1),
            (0, 0, 1, 0), (0, 0, 0, 1),
        )))
        framebuffer = gpu.state.active_framebuffer_get()
        gpu.state.blend_set('ALPHA')
        framebuffer.clear(color=(1, 1, 1, 1))
        normal('a', 70, 55, 185)
        prefs = SimpleNamespace(text_shadow_enabled=True,
                                text_shadow_strength=0.5,
                                text_shadow_spread='DIFFUSE')
        gpu_theme.get_prefs = lambda: prefs
        blf.size(0, 185)
        blf.color(0, 1, 1, 1, 1)
        gpu_theme.draw_canvas_text(0, 'a', 390, 55,
                                   (1, 1, 1, 1), 185)
        diffuse('a', 710, 55, 185, [(8, 0.075)])
        if '--preview' in sys.argv:
            pixels = np.asarray(framebuffer.read_color(
                0, 0, WIDTH, HEIGHT, 4, 0, 'UBYTE')).reshape(HEIGHT, WIDTH, 4)
            image = bpy.data.images.new('Shadow probe', width=WIDTH, height=HEIGHT)
            image.pixels.foreach_set((pixels.astype(np.float32) / 255).ravel())
            path = Path(__file__).parent / 'shadow_probe.png'
            image.filepath_raw = str(path)
            image.file_format = 'PNG'
            image.save()
            print('SHADOW PREVIEW', path)

        def measure(draw, size=18):
            samples = []
            for _ in range(10):
                framebuffer.clear(color=(1, 1, 1, 1))
                started = time.perf_counter()
                for line in range(20):
                    draw('Heading demo', 30, 20 + line * 13, size)
                framebuffer.read_color(0, 0, 1, 1, 4, 0, 'UBYTE')
                samples.append((time.perf_counter() - started) * 1000)
            return round(sorted(samples)[len(samples) // 2], 3)

        print('SHADOW BENCH normal_ms', measure(normal))
        print('SHADOW BENCH normal_large_ms', measure(normal, 64))
        print('SHADOW BENCH diffuse_17_ms', measure(
            lambda text, x, y, size: diffuse(text, x, y, size,
                                             [(3, 0.07), (6, 0.035)])))
        print('SHADOW BENCH diffuse_9_ms', measure(
            lambda text, x, y, size: diffuse(text, x, y, size,
                                             [(5, 0.075)])))
        def optimized(text, x, y, size):
            blf.size(0, size)
            blf.color(0, 1, 1, 1, 1)
            gpu_theme.draw_canvas_text(0, text, x, y,
                                       (1, 1, 1, 1), size)

        print('SHADOW BENCH optimized_small_ms', measure(optimized))
        print('SHADOW BENCH optimized_large_ms', measure(optimized, 64))
        gpu.matrix.pop_projection()
finally:
    offscreen.free()
