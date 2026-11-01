"""Dominant colors of an image (k-means in NumPy, no extra packages)."""

import numpy as np

SAMPLE_EDGE = 96   # the image is reduced to about this many pixels on its long side


def _reduce(rgb, edge):
    """Nearest-neighbour reduction so k-means works on a few thousand pixels."""
    height, width = rgb.shape[:2]
    scale = min(1.0, edge / max(height, width))
    new_h, new_w = max(1, round(height * scale)), max(1, round(width * scale))
    ys = np.minimum((np.arange(new_h) / scale).astype(int), height - 1)
    xs = np.minimum((np.arange(new_w) / scale).astype(int), width - 1)
    return rgb[ys][:, xs]


def dominant_colors(rgb, count=6, iterations=12, seed=7):
    """The `count` most representative colors of `rgb` (height, width, 3, 0..1).

    Returns a list of (color, share) sorted by how much of the image each covers.
    Clusters that end up almost the same color are merged, so the result can hold
    fewer colors than requested for flat images.
    """
    count = max(1, int(count))
    pixels = _reduce(np.asarray(rgb, dtype=np.float32), SAMPLE_EDGE).reshape(-1, 3)
    if len(pixels) == 0:
        return []
    rng = np.random.default_rng(seed)
    # k-means++ seeding: spread the first centers over the color space.
    centers = [pixels[rng.integers(len(pixels))]]
    for _ in range(1, min(count, len(pixels))):
        distance = np.min([((pixels - c) ** 2).sum(axis=1) for c in centers], axis=0)
        total = distance.sum()
        if total <= 1e-9:
            break
        centers.append(pixels[rng.choice(len(pixels), p=distance / total)])
    centers = np.array(centers, dtype=np.float32)

    for _ in range(iterations):
        distances = ((pixels[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = distances.argmin(axis=1)
        moved = False
        for index in range(len(centers)):
            members = pixels[labels == index]
            if len(members):
                updated = members.mean(axis=0)
                moved = moved or bool(np.abs(updated - centers[index]).max() > 1e-4)
                centers[index] = updated
        if not moved:
            break

    distances = ((pixels[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    labels = distances.argmin(axis=1)
    shares = np.bincount(labels, minlength=len(centers)) / len(pixels)

    merged = []   # (color, share), merging near-identical clusters
    for index in np.argsort(-shares):
        if shares[index] <= 0:
            continue
        color = centers[index]
        for entry in merged:
            if np.abs(entry[0] - color).max() < 0.04:
                total = entry[1] + shares[index]
                entry[0] = (entry[0] * entry[1] + color * shares[index]) / total
                entry[1] = total
                break
        else:
            merged.append([color.copy(), float(shares[index])])
    merged.sort(key=lambda entry: -entry[1])
    return [(tuple(float(v) for v in np.clip(entry[0], 0.0, 1.0)), entry[1])
            for entry in merged[:count]]


def hex_name(color):
    return '#{:02X}{:02X}{:02X}'.format(*(round(max(0.0, min(1.0, v)) * 255) for v in color))


def pixel_color_at(image, uv):
    """Display color of the source pixel at an image UV (0..1, origin bottom-left).

    This is the original pixel, before any Kanvas brightness, contrast or tint.
    Float images get the same approximate sRGB encoding used when extracting a palette.
    """
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError('Image has no pixels')
    x = min(width - 1, max(0, int(uv[0] * width)))
    y = min(height - 1, max(0, int(uv[1] * height)))
    start = (y * width + x) * 4
    rgb = np.clip(np.array(image.pixels[start:start + 3], dtype=np.float32), 0.0, 1.0)
    if image.is_float:
        rgb = rgb ** (1.0 / 2.2)
    return tuple(float(v) for v in rgb)
