"""Copying a picture to the system clipboard: PNG and bitmap round trip (Windows)."""

import struct
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from k_tools_kanvas.utils import clipboard_image as ci

picture = np.zeros((3, 4, 4), dtype=np.uint8)
picture[0, 0] = (255, 0, 0, 255)       # top left: red
picture[2, 3] = (0, 0, 255, 128)       # bottom right: half-clear blue

png = ci.png_bytes(picture)
assert png.startswith(b'\x89PNG\r\n\x1a\n')
width, height = struct.unpack('>II', png[16:24])
assert (width, height) == (4, 3)

dib = ci.bmp_dib(picture)
assert struct.unpack_from('<I', dib)[0] == 124
assert struct.unpack_from('<ii', dib, 4) == (4, 3)
pixels = dib[124:]
assert len(pixels) == 4 * 3 * 4
assert pixels[-16:-12] == bytes((0, 0, 255, 255))      # bottom-up: top row is last, B G R A

if sys.platform == 'win32':
    ci.copy_picture(picture)
    result = ci.read_image_clipboard()
    assert result.extension == '.png' and result.pixels.startswith(b'\x89PNG')
    body = result.pixels
    assert body == png
    # The bitmap alone must also survive when the PNG format is missing.
    assert ci.dib_to_bmp(dib)[:2] == b'BM'

print('test_clipboard_copy: OK')
