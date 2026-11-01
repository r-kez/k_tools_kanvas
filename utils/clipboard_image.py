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


def read_image_clipboard(text_fallback=''):
    """Prefer copied files, then pixels, then copied local paths."""
    if sys.platform == 'win32':
        result = _windows_clipboard_image()
        if result.paths or result.pixels:
            return result
    return ClipboardImage(paths=local_image_paths(text_fallback))
