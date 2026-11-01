"""Read the image layout from PureRef 2.x scenes without modifying the source."""

from dataclasses import dataclass
import math
from pathlib import Path
import sqlite3
import struct


_SQLITE_MAGIC = b'SQLite format 3\0'
_MAX_FILE_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class PureRefImage:
    item_id: int
    image_id: int
    name: str
    payload: bytes
    extension: str
    source_size: tuple[int, int]
    center: tuple[float, float]
    scale: tuple[float, float]
    rotation: float
    opacity: float
    locked: bool
    z_index: int


@dataclass(frozen=True)
class PureRefText:
    item_id: int
    content: str
    center: tuple[float, float]
    opacity: float
    color: tuple[float, float, float]
    background: tuple[float, float, float]
    background_opacity: float
    z_index: int


@dataclass(frozen=True)
class PureRefScene:
    version: str
    images: tuple[PureRefImage, ...]
    skipped: tuple[str, ...]
    texts: tuple[PureRefText, ...] = ()


def _original_bytes(value):
    """PureRef stores Qt binary structures as UTF-8 encoded Latin-1 text."""
    if isinstance(value, bytes):
        return value.decode('utf-8').encode('latin-1')
    return value.encode('latin-1')


def _qt_matrix(value):
    raw = _original_bytes(value)
    if len(raw) != 77 or raw[:5] != b'\x00\x00\x00P\x00':
        raise ValueError('Unsupported PureRef transform encoding')
    matrix = struct.unpack('>9d', raw[5:])
    if (not all(math.isfinite(number) for number in matrix)
            or abs(matrix[2]) > 1e-8 or abs(matrix[5]) > 1e-8
            or abs(matrix[8] - 1.0) > 1e-8):
        raise ValueError('Unsupported PureRef perspective transform')
    return matrix


def _display_transform(item_matrix, image_matrix, width, height):
    a, b, _, c, d, _, x, y, _ = item_matrix
    ia, ib, _, ic, id_, _, ix, iy, _ = image_matrix
    local_x = ia * width * 0.5 + ic * height * 0.5 + ix
    local_y = ib * width * 0.5 + id_ * height * 0.5 + iy
    center = (a * local_x + c * local_y + x,
              -(b * local_x + d * local_y + y))
    aa, bb = a * ia + c * ib, b * ia + d * ib
    cc, dd = a * ic + c * id_, b * ic + d * id_
    scale_x = math.hypot(aa, bb)
    if scale_x <= 1e-8:
        raise ValueError('PureRef image has zero width')
    scale_y = (aa * dd - bb * cc) / scale_x
    if abs(scale_y) <= 1e-8:
        raise ValueError('PureRef image has zero height')
    if abs(aa * cc + bb * dd) > 1e-5 * scale_x * abs(scale_y):
        raise ValueError('PureRef image uses unsupported skew')
    return center, (scale_x, scale_y), -math.degrees(math.atan2(bb, aa))


def _scene_database(raw):
    offset = raw.rfind(_SQLITE_MAGIC)
    if offset < 0 or offset + 100 > len(raw):
        raise ValueError('No PureRef 2.x scene database found')
    page_size = int.from_bytes(raw[offset + 16:offset + 18], 'big')
    if page_size == 1:
        page_size = 65536
    page_count = int.from_bytes(raw[offset + 28:offset + 32], 'big')
    backup_size = len(raw) - offset
    if (page_size < 512 or page_size > 65536 or page_size & (page_size - 1)
            or page_count * page_size != offset
            or backup_size <= 0 or backup_size > offset):
        raise ValueError('Invalid PureRef 2.x scene database layout')
    # PureRef replaces the beginning of its SQLite database with scene
    # metadata/preview bytes and appends the overwritten bytes at the end.
    return raw[offset:] + raw[backup_size:offset]


def read_pureref(path):
    """Return supported 2.x image items and explicit counts of skipped items."""
    source = Path(path)
    if source.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError('PureRef scene exceeds the 512 MB import limit')
    raw = source.read_bytes()
    if len(raw) < 12:
        raise ValueError('PureRef scene is empty or incomplete')
    version_bytes = int.from_bytes(raw[:4], 'big')
    if version_bytes < 2 or version_bytes > 32 or version_bytes % 2:
        raise ValueError('Unrecognized PureRef scene header')
    version = raw[4:4 + version_bytes].decode('utf-16-be')
    if version.startswith('1.10') or version.startswith('1.11'):
        from .pureref_legacy import read_legacy
        legacy_images, legacy_texts, skipped = read_legacy(raw)
        ranked = sorted(([(record.z, 'image', record) for record in legacy_images]
                         + [(record.z, 'text', record) for record in legacy_texts]),
                        key=lambda entry: entry[0])
        images, texts = [], []
        for z_index, (_, kind, record) in enumerate(ranked):
            if kind == 'image':
                images.append(PureRefImage(
                    record.item_id, record.image_id, record.name, record.payload,
                    'png', record.source_size, record.center, record.scale,
                    record.rotation, 1.0, False, z_index))
            else:
                texts.append(PureRefText(
                    record.item_id, record.content, record.center,
                    record.opacity, record.color, record.background,
                    record.background_opacity, z_index))
        return PureRefScene(version, tuple(images), tuple(skipped), tuple(texts))
    if not version.startswith('2.'):
        raise ValueError(f'Unsupported PureRef {version} scene version')

    connection = sqlite3.connect(':memory:')
    try:
        connection.deserialize(_scene_database(raw))
        connection.text_factory = bytes
        if connection.execute('PRAGMA quick_check').fetchone()[0] != b'ok':
            raise ValueError('PureRef scene database failed its integrity check')
        version_row = connection.execute(
            'SELECT application_version FROM metadata LIMIT 1'
        ).fetchone()
        if version_row and version_row[0]:
            version = version_row[0].decode('utf-8', 'replace')
        counts = {}
        for table in ('items_notes', 'items_groups', 'items_drawings'):
            counts[table] = connection.execute(
                f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        skipped = [f'{count} {label}' for table, label in (
            ('items_notes', 'notes'), ('items_groups', 'groups'),
            ('items_drawings', 'drawings')) if (count := counts[table])]

        images = []
        query = '''
            SELECT i.id, i.name, i.transform, i.z, i.opacity, i.locked,
                   ii.image, ii.image_transform, ii.flags,
                   im.data, im.format, im.width, im.height
            FROM items AS i
            JOIN items_images AS ii ON ii.id = i.id
            LEFT JOIN images AS im ON im.id = ii.image
            ORDER BY i.z, i.id
        '''
        for row in connection.execute(query):
            (item_id, name, item_transform, z, opacity, locked, image_id,
             image_transform, flags, payload, fmt, width, height) = row
            if payload is None or not width or not height or width < 0 or height < 0:
                skipped.append(f'image item {item_id} without embedded pixels')
                continue
            extension = fmt.decode('utf-8').lower()
            if extension not in {'png', 'jpg', 'jpeg'}:
                skipped.append(f'image item {item_id} in unsupported {extension} format')
                continue
            if not (payload.startswith(b'\x89PNG\r\n\x1a\n')
                    or payload.startswith(b'\xff\xd8\xff')):
                skipped.append(f'image item {item_id} with invalid image bytes')
                continue
            try:
                center, scale, rotation = _display_transform(
                    _qt_matrix(item_transform), _qt_matrix(image_transform),
                    width, height)
            except ValueError as exc:
                skipped.append(f'image item {item_id}: {exc}')
                continue
            if flags != 1:
                skipped.append(f'image item {item_id}: crop or playback details ignored')
            images.append(PureRefImage(
                item_id=item_id, image_id=image_id,
                name=(name.decode('utf-8') if name else f'PureRef Image {item_id}'),
                payload=payload, extension=extension,
                source_size=(width, height), center=center, scale=scale,
                rotation=rotation, opacity=max(0.0, min(1.0, opacity)),
                locked=bool(locked), z_index=len(images)))
        return PureRefScene(version, tuple(images), tuple(skipped))
    finally:
        connection.close()
