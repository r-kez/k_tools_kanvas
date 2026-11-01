"""Reader for the pre-SQLite PureRef 1.10/1.11 scene layout.

The record layout was documented by FyorDev/PureRef-format (MIT). This
reader uses bounded cursor operations and only returns supported items.
"""

from dataclasses import dataclass
import math
import struct


_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


@dataclass(frozen=True)
class LegacyImage:
    item_id: int
    image_id: int
    name: str
    payload: bytes
    source_size: tuple[int, int]
    center: tuple[float, float]
    scale: tuple[float, float]
    rotation: float
    z: float


@dataclass(frozen=True)
class LegacyText:
    item_id: int
    content: str
    center: tuple[float, float]
    z: float
    opacity: float
    color: tuple[float, float, float]
    background: tuple[float, float, float]
    background_opacity: float


class _Cursor:
    def __init__(self, raw, offset=0):
        self.raw = raw
        self.pos = offset

    def take(self, count):
        end = self.pos + count
        if count < 0 or end > len(self.raw):
            raise ValueError('Truncated PureRef 1.x record')
        value = self.raw[self.pos:end]
        self.pos = end
        return value

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def peek(self, fmt, offset=0):
        size = struct.calcsize(fmt)
        if self.pos + offset + size > len(self.raw):
            raise ValueError('Truncated PureRef 1.x record')
        return struct.unpack_from(fmt, self.raw, self.pos + offset)[0]

    def string(self):
        length = self.unpack('>I')
        if length > len(self.raw) - self.pos or length % 2:
            raise ValueError('Invalid PureRef 1.x string')
        return self.take(length).decode('utf-16-be', 'replace')

    def matrix(self):
        raw = self.take(48)
        return (struct.unpack_from('>d', raw, 0)[0],
                struct.unpack_from('>d', raw, 8)[0],
                struct.unpack_from('>d', raw, 24)[0],
                struct.unpack_from('>d', raw, 32)[0])

    def jump(self, position):
        if position < self.pos or position > len(self.raw):
            raise ValueError('Invalid PureRef 1.x record end')
        self.pos = position


def _png(cursor):
    start = cursor.pos
    if cursor.take(8) != _PNG_MAGIC:
        raise ValueError('Invalid PureRef 1.x PNG image')
    dimensions = None
    while True:
        size = cursor.unpack('>I')
        kind = cursor.take(4)
        if size > len(cursor.raw) - cursor.pos - 4:
            raise ValueError('Truncated PureRef 1.x PNG image')
        data = cursor.take(size)
        cursor.take(4)  # CRC is checked by Blender's image decoder.
        if kind == b'IHDR' and len(data) >= 8:
            dimensions = struct.unpack_from('>II', data)
        if kind == b'IEND':
            break
    if not dimensions or min(dimensions) < 1:
        raise ValueError('Invalid PureRef 1.x PNG dimensions')
    return start, cursor.raw[start:cursor.pos], dimensions


def _color(cursor):
    color_space = cursor.unpack('>B')
    opacity = cursor.unpack('>H') / 65535.0
    channels = tuple(cursor.unpack('>H') / 65535.0 for _ in range(3))
    if color_space == 2:
        import colorsys
        channels = colorsys.hsv_to_rgb(channels[0] * 65535 / 35900,
                                       channels[1], channels[2])
    return opacity, channels


def _text(cursor):
    end = cursor.peek('>Q')
    kind = cursor.peek('>I', 8)
    if kind != 32:
        raise ValueError('Invalid PureRef 1.x text record')
    cursor.take(12 + kind)
    content = cursor.string()
    cursor.matrix()
    x, y = cursor.unpack('>d'), cursor.unpack('>d')
    cursor.take(8)
    item_id = cursor.unpack('>I')
    z = cursor.unpack('>d')
    opacity, color = _color(cursor)
    cursor.take(2)
    background_opacity, background = _color(cursor)
    children = cursor.peek('>I', 2)
    cursor.jump(end)
    return LegacyText(item_id, content, (x, -y), z, opacity, color,
                      background, background_opacity), children


def _image(cursor):
    end = cursor.peek('>Q')
    kind = cursor.peek('>I', 8)
    if kind != 34:
        raise ValueError('Invalid PureRef 1.x image record')
    cursor.take(12 + kind)
    # Some legacy records start with an extra zero-valued field.
    brute_force = cursor.peek('>I') == 0
    if brute_force:
        cursor.take(4)
    source = '' if cursor.peek('>i') == -1 else cursor.string()
    if not source:
        cursor.take(4)
    name = ''
    if not brute_force:
        if cursor.peek('>i') == -1:
            cursor.take(4)
        else:
            name = cursor.string()
    cursor.take(8)
    matrix = cursor.matrix()
    x, y = cursor.unpack('>d'), cursor.unpack('>d')
    cursor.take(8)
    item_id = cursor.unpack('>I')
    z = cursor.unpack('>d')
    cursor.matrix()  # Transform before any crop.
    cursor.take(24)  # Crop translation and scale.
    point_count = cursor.unpack('>I')
    if point_count > 4096:
        raise ValueError('PureRef 1.x crop has too many points')
    points = []
    for _ in range(point_count):
        cursor.take(4)
        points.append((cursor.unpack('>d'), cursor.unpack('>d')))
    children = cursor.peek('>I', 21)
    cursor.jump(end)
    return (item_id, name or source, matrix, x, y, z, points), children


def read_legacy(raw):
    """Return image/text records and unsupported details from a 1.x file."""
    if len(raw) < 224:
        raise ValueError('Truncated PureRef 1.x header')
    cursor = _Cursor(raw, 224)
    blobs = []
    while cursor.pos + 12 <= len(raw):
        kind = cursor.peek('>I', 8)
        record_end = cursor.peek('>Q')
        if kind in (32, 34) and cursor.pos < record_end <= len(raw):
            break
        if raw.startswith(_PNG_MAGIC, cursor.pos):
            blobs.append(_png(cursor))
        else:
            blobs.append((cursor.pos, cursor.unpack('>I'), None))
    image_records = []
    texts = []
    skipped = []
    while cursor.pos + 12 <= len(raw) and cursor.peek('>I', 8) in (32, 34):
        if cursor.peek('>I', 8) == 34:
            record, children = _image(cursor)
            image_records.append(record)
        else:
            record, children = _text(cursor)
            texts.append(record)
        if children > 4096:
            raise ValueError('PureRef 1.x item has too many child notes')
        for _ in range(children):
            note, _ = _text(cursor)
            texts.append(note)
    cursor.string()  # Folder used when the scene was last saved.
    references = {}
    for _ in image_records:
        item_id = cursor.unpack('>I')
        start, _ = cursor.unpack('>Q'), cursor.unpack('>Q')
        references[item_id] = start
    by_address = {address: (data, size) for address, data, size in blobs}
    images = []
    for item_id, name, matrix, x, y, z, points in image_records:
        address = references.get(item_id)
        blob = by_address.get(address)
        if blob is None:
            skipped.append(f'image item {item_id} without embedded pixels')
            continue
        payload, size = blob
        image_id = address
        if size is None:
            if payload == 0xFFFFFFFF:
                skipped.append(f'image item {item_id} linked to an external file')
                continue
            original_address = references.get(payload)
            image_id = original_address
            payload, size = by_address.get(original_address, (None, None))
        if size is None:
            skipped.append(f'image item {item_id} with unresolved duplicate')
            continue
        width, height = size
        a, b, c, d = matrix
        if not all(math.isfinite(value) for value in (*matrix, x, y, z)):
            skipped.append(f'image item {item_id} with invalid transform')
            continue
        scale_x = math.hypot(a, b)
        scale_y = (a * d - b * c) / max(scale_x, 1e-8)
        if scale_x <= 1e-8 or abs(scale_y) <= 1e-8:
            skipped.append(f'image item {item_id} with zero scale')
            continue
        if abs(a * c + b * d) > 1e-5 * scale_x * abs(scale_y):
            skipped.append(f'image item {item_id} with unsupported skew')
            continue
        if points:
            xs, ys = [point[0] for point in points], [point[1] for point in points]
            if (abs(max(xs) - min(xs) - width) > 1.0
                    or abs(max(ys) - min(ys) - height) > 1.0):
                skipped.append(f'image item {item_id}: crop ignored')
        images.append(LegacyImage(item_id, image_id, name or f'PureRef Image {item_id}',
                                  payload, size, (x, -y), (scale_x, scale_y),
                                  -math.degrees(math.atan2(b, a)), z))
    return images, texts, skipped
