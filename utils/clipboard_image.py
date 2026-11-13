"""Read local image files or image pixels from the system clipboard."""

import ctypes
import os
import struct
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass


IMAGE_EXTENSIONS = frozenset({
    '.png', '.jpg', '.jpeg', '.bmp', '.tga', '.tif', '.tiff', '.webp', '.exr',
})
_MAX_PIXEL_BYTES = 512 * 1024 * 1024
_CF_DIB = 8
_CF_UNICODETEXT = 13
_CF_HDROP = 15
_CF_DIBV5 = 17


@dataclass(frozen=True)
class ClipboardImage:
    paths: tuple[str, ...] = ()
    pixels: bytes = b''
    extension: str = ''


def local_image_paths(text):
    """Accept copied local paths, including quoted paths on separate lines."""
    paths = []
    for line in text.splitlines():
        path = line.strip().strip('"').strip("'")
        if (path and not path.lower().startswith(('http://', 'https://'))
                and os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS
                and os.path.isfile(path)):
            paths.append(os.path.abspath(path))
    return tuple(dict.fromkeys(paths))


def dib_to_bmp(dib):
    """Add a BMP file header to Windows clipboard DIB pixel data."""
    if len(dib) < 12:
        raise ValueError('Clipboard bitmap has an incomplete header')
    header_size = struct.unpack_from('<I', dib)[0]
    if header_size == 12:
        if len(dib) < 12:
            raise ValueError('Clipboard bitmap has an incomplete header')
        bpp = struct.unpack_from('<H', dib, 10)[0]
        palette_size = (1 << bpp) * 3 if bpp <= 8 else 0
    elif header_size >= 40 and len(dib) >= header_size:
        bpp = struct.unpack_from('<H', dib, 14)[0]
        compression = struct.unpack_from('<I', dib, 16)[0]
        colors_used = struct.unpack_from('<I', dib, 32)[0]
        palette_colors = colors_used if colors_used else (1 << bpp if bpp <= 8 else 0)
        palette_size = palette_colors * 4
        if header_size == 40 and compression in {3, 6}:
            palette_size += 16 if compression == 6 else 12
    else:
        raise ValueError('Clipboard bitmap has an unsupported header')
    pixel_offset = 14 + header_size + palette_size
    if pixel_offset > len(dib) + 14:
        raise ValueError('Clipboard bitmap has an incomplete color table')
    return struct.pack('<2sIHHI', b'BM', len(dib) + 14, 0, 0, pixel_offset) + dib


def _win32_clipboard():
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = ()
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = (wintypes.UINT,)
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.IsClipboardFormatAvailable.argtypes = (wintypes.UINT,)
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalSize.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalSize.restype = ctypes.c_size_t
    shell32.DragQueryFileW.argtypes = (
        ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT)
    shell32.DragQueryFileW.restype = wintypes.UINT
    return user32, kernel32, shell32


def _global_bytes(kernel32, handle):
    size = kernel32.GlobalSize(handle)
    if not 0 < size <= _MAX_PIXEL_BYTES:
        return b''
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return b''
    try:
        return ctypes.string_at(pointer, size)
    finally:
        kernel32.GlobalUnlock(handle)


def _windows_clipboard_image():
    user32, kernel32, shell32 = _win32_clipboard()
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        raise RuntimeError('Clipboard is busy; try pasting again')
    try:
        if user32.IsClipboardFormatAvailable(_CF_HDROP):
            handle = user32.GetClipboardData(_CF_HDROP)
            if handle:
                count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
                paths = []
                for index in range(count):
                    length = shell32.DragQueryFileW(handle, index, None, 0)
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    shell32.DragQueryFileW(handle, index, buffer, length + 1)
                    paths.append(buffer.value)
                image_paths = tuple(path for path in paths
                                    if os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS
                                    and os.path.isfile(path))
                if image_paths:
                    return ClipboardImage(paths=image_paths)

        png_format = user32.RegisterClipboardFormatW('PNG')
        if png_format and user32.IsClipboardFormatAvailable(png_format):
            handle = user32.GetClipboardData(png_format)
            if handle:
                pixels = _global_bytes(kernel32, handle)
                if pixels.startswith(b'\x89PNG\r\n\x1a\n'):
                    return ClipboardImage(pixels=pixels, extension='.png')

        for format_id in (_CF_DIBV5, _CF_DIB):
            if user32.IsClipboardFormatAvailable(format_id):
                handle = user32.GetClipboardData(format_id)
                if handle:
                    dib = _global_bytes(kernel32, handle)
                    if dib:
                        try:
                            return ClipboardImage(pixels=dib_to_bmp(dib),
                                                  extension='.bmp')
                        except ValueError:
                            pass

        if user32.IsClipboardFormatAvailable(_CF_UNICODETEXT):
            handle = user32.GetClipboardData(_CF_UNICODETEXT)
            if handle:
                pointer = kernel32.GlobalLock(handle)
                if pointer:
                    try:
                        paths = local_image_paths(ctypes.wstring_at(pointer))
                        if paths:
                            return ClipboardImage(paths=paths)
                    finally:
                        kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    return ClipboardImage()


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def png_bytes(picture):
    """A (height, width, 4) uint8/uint16 array as PNG bytes."""
    import tempfile
    from .board_render import write_png
    handle, path = tempfile.mkstemp(suffix='.png', prefix='kanvas_')
    os.close(handle)
    try:
        write_png(path, picture)
        with open(path, 'rb') as stream:
            return stream.read()
    finally:
        _remove(path)


def bmp_dib(picture):
    """Bottom-up 32-bit BGRA DIB (BITMAPV5HEADER) of an RGBA picture, top row first."""
    import numpy as np
    if picture.dtype != np.uint8:
        picture = (picture >> 8).astype(np.uint8)
    height, width = picture.shape[:2]
    pixels = np.ascontiguousarray(picture[::-1][..., [2, 1, 0, 3]]).tobytes()
    header = struct.pack('<IiiHHIIiiII', 124, width, height, 1, 32, 3,
                         len(pixels), 2835, 2835, 0, 0)
    masks = struct.pack('<IIII', 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    color_space = struct.pack('<I', 0x73524742) + b'\0' * 36   # 'sRGB', no endpoints
    gamma = b'\0' * 12
    intent = struct.pack('<IIII', 4, 0, 0, 0)                  # LCS_GM_IMAGES
    return header + masks + color_space + gamma + intent + pixels


def _set_windows_clipboard(png, dib):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = ()
    user32.EmptyClipboard.argtypes = ()
    user32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)

    def block(data):
        handle = kernel32.GlobalAlloc(0x0002, len(data))     # GMEM_MOVEABLE
        if not handle:
            raise RuntimeError('Out of memory for the clipboard')
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        return handle

    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        raise RuntimeError('Clipboard is busy; try again')
    try:
        user32.EmptyClipboard()
        for format_id, data in ((user32.RegisterClipboardFormatW('PNG'), png),
                                (_CF_DIBV5, dib)):
            handle = block(data)
            if not user32.SetClipboardData(format_id, handle):
                kernel32.GlobalFree(handle)   # the system owns it only on success
                raise RuntimeError('Could not place the picture on the clipboard')
    finally:
        user32.CloseClipboard()


def _run_clipboard_tool(command, data=None):
    import subprocess
    try:
        subprocess.run(command, input=data, check=True, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise RuntimeError(f'"{command[0]}" is not installed') from None
    except (subprocess.SubprocessError, OSError) as exc:
        raise RuntimeError(f'"{command[0]}" failed: {exc}') from None


def copy_picture(picture):
    """Put an RGBA picture (uint8/uint16 array, top row first) on the system clipboard
    as an image. Windows writes the pixels directly; macOS and Linux go through a file
    in the system temp folder and the system tool. Raises RuntimeError when it cannot."""
    import shutil
    import tempfile
    png = png_bytes(picture)
    if sys.platform == 'win32':
        _set_windows_clipboard(png, bmp_dib(picture))
    elif sys.platform == 'darwin':
        handle, path = tempfile.mkstemp(suffix='.png', prefix='kanvas_')
        try:
            with os.fdopen(handle, 'wb') as stream:
                stream.write(png)
            _run_clipboard_tool(['osascript', '-e',
                                 f'set the clipboard to (read (POSIX file "{path}") '
                                 'as «class PNGf»)'])
        finally:
            _remove(path)
    elif shutil.which('wl-copy'):
        _run_clipboard_tool(['wl-copy', '--type', 'image/png'], png)
    elif shutil.which('xclip'):
        _run_clipboard_tool(['xclip', '-selection', 'clipboard', '-t', 'image/png'], png)
    else:
        raise RuntimeError('Install "wl-copy" (Wayland) or "xclip" (X11) to copy images')


def read_image_clipboard(text_fallback=''):
    """Prefer copied files, then pixels, then copied local paths."""
    if sys.platform == 'win32':
        result = _windows_clipboard_image()
        if result.paths or result.pixels:
            return result
    return ClipboardImage(paths=local_image_paths(text_fallback))
