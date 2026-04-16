"""
Realism engine for InkClone — composable post-processing layers that make
handwriting look more authentic.

Each layer takes an RGBA PIL Image and an `amount` float in [0, 1].
The returned image is the same size and mode.

`apply_realism(img, preset)` stacks all layers using the chosen PRESET.
"""

import numpy as np
from PIL import Image

PRESETS = {
    "perfect": dict(
        page_fatigue=0.0,
        baseline_wander=0.0,
        margin_drift=0.0,
        pressure_variation=0.0,
        pen_fading=0.0,
        line_end_cramming=0.0,
    ),
    "natural": dict(
        page_fatigue=0.15,
        baseline_wander=0.2,
        margin_drift=0.1,
        pressure_variation=0.2,
        pen_fading=0.1,
        line_end_cramming=0.1,
    ),
    "rushed": dict(
        page_fatigue=0.4,
        baseline_wander=0.45,
        margin_drift=0.3,
        pressure_variation=0.35,
        pen_fading=0.25,
        line_end_cramming=0.4,
    ),
    "messy": dict(
        page_fatigue=0.8,
        baseline_wander=0.75,
        margin_drift=0.6,
        pressure_variation=0.6,
        pen_fading=0.5,
        line_end_cramming=0.7,
    ),
}


def page_fatigue(img: Image.Image, amount: float) -> Image.Image:
    """Writing gets progressively messier toward the bottom of the page."""
    if amount <= 0:
        return img
    arr = np.array(img)
    h, w = arr.shape[:2]
    rng = np.random.default_rng(7)

    noise_len = max(h // 4, 4)
    h_noise = rng.uniform(-1, 1, noise_len)
    h_noise = np.interp(np.arange(h), np.linspace(0, h, noise_len), h_noise)

    y_pos = np.arange(h)
    amplitude = amount * w * 0.012 * (y_pos / h) ** 0.7
    col_shifts = (h_noise * amplitude).astype(int)

    src_x = np.arange(w)[np.newaxis, :] - col_shifts[:, np.newaxis]
    valid = (src_x >= 0) & (src_x < w)
    src_x = np.clip(src_x, 0, w - 1)
    row_idx = np.arange(h)[:, np.newaxis]
    result = arr[row_idx, src_x, :]
    result[~valid] = 0
    return Image.fromarray(result.astype(np.uint8), 'RGBA')


def baseline_wander(img: Image.Image, amount: float) -> Image.Image:
    """Lines of text drift up and down slightly across the page."""
    if amount <= 0:
        return img
    arr = np.array(img)
    h, w = arr.shape[:2]

    amplitude = amount * h * 0.012
    freq = 2 * np.pi * 1.5 / h
    offsets = (amplitude * np.sin(freq * np.arange(h))).astype(int)

    src_y = np.clip(np.arange(h) - offsets, 0, h - 1).astype(int)
    return Image.fromarray(arr[src_y], 'RGBA')


def margin_drift(img: Image.Image, amount: float) -> Image.Image:
    """Left margin creeps rightward as the writer tires."""
    if amount <= 0:
        return img
    arr = np.array(img)
    h, w = arr.shape[:2]

    max_shift = int(amount * w * 0.04)
    shifts = (np.arange(h) / h * max_shift).astype(int)

    src_x = np.arange(w)[np.newaxis, :] - shifts[:, np.newaxis]
    valid = (src_x >= 0) & (src_x < w)
    src_x = np.clip(src_x, 0, w - 1)
    row_idx = np.arange(h)[:, np.newaxis]
    result = arr[row_idx, src_x, :]
    result[~valid] = 0
    return Image.fromarray(result.astype(np.uint8), 'RGBA')


def pressure_variation(img: Image.Image, amount: float) -> Image.Image:
    """Pen pressure varies, making strokes lighter or darker in patches."""
    if amount <= 0:
        return img
    arr = np.array(img).astype(float)
    h, w = arr.shape[:2]
    rng = np.random.default_rng(13)

    nh, nw = max(h // 25, 2), max(w // 25, 2)
    noise_lo = rng.uniform(1 - amount * 0.3, 1.0, (nh, nw))
    noise_img = Image.fromarray((noise_lo * 255).clip(0, 255).astype(np.uint8), 'L')
    noise_img = noise_img.resize((w, h), Image.BILINEAR)
    noise = np.array(noise_img, dtype=float) / 255.0

    arr[:, :, 3] = np.clip(arr[:, :, 3] * noise, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')


def pen_fading(img: Image.Image, amount: float) -> Image.Image:
    """Ink gradually lightens toward the bottom, as if the pen is running dry."""
    if amount <= 0:
        return img
    arr = np.array(img).astype(float)
    h, w = arr.shape[:2]

    gradient = np.linspace(1.0, 1.0 - amount * 0.5, h)[:, np.newaxis]
    arr[:, :, 3] = np.clip(arr[:, :, 3] * gradient, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')


def line_end_cramming(img: Image.Image, amount: float) -> Image.Image:
    """Text compresses near the right margin, as the writer squeezes words in."""
    if amount <= 0:
        return img
    arr = np.array(img)
    h, w = arr.shape[:2]

    x = np.arange(w, dtype=float)
    t = x / w
    src_x = (x + amount * w * 0.06 * t ** 2).astype(int)
    valid = (src_x >= 0) & (src_x < w)
    src_x = np.clip(src_x, 0, w - 1)

    row_idx = np.arange(h)[:, np.newaxis]
    result = arr[row_idx, src_x[np.newaxis, :], :]
    result[:, ~valid, :] = 0
    return Image.fromarray(result.astype(np.uint8), 'RGBA')


def apply_realism(img: Image.Image, preset: str = "natural") -> Image.Image:
    """Apply a named realism preset to the rendered handwriting RGBA image."""
    params = PRESETS.get(preset, PRESETS["natural"])
    img = page_fatigue(img, params["page_fatigue"])
    img = baseline_wander(img, params["baseline_wander"])
    img = margin_drift(img, params["margin_drift"])
    img = pressure_variation(img, params["pressure_variation"])
    img = pen_fading(img, params["pen_fading"])
    img = line_end_cramming(img, params["line_end_cramming"])
    return img
