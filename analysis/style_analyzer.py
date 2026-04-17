"""
Handwriting style analyzer — pure OpenCV, no external API.

Input:  image path, bytes, or BGR numpy array of handwritten notes.
Output: dict of 11 scores in [0, 100].

Pipeline: grayscale → adaptive threshold → horizontal projection
          → text-line detection → connected components → per-metric scoring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import cv2
import numpy as np


# ── Public API ─────────────────────────────────────────────────────────────────

def analyze_style(image_input: Union[str, Path, bytes, bytearray, np.ndarray]) -> dict:
    """
    Analyze handwriting style from an image.

    Returns dict with keys:
        baseline_straightness, letter_spacing_tightness, word_spacing,
        size_consistency, average_size, slant_angle, slant_consistency,
        pressure_variation, neatness, margin_consistency, line_spacing
    All values are floats in [0, 100].
    """
    img_bgr = _load_image(image_input)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    h, w = gray.shape

    # Adaptive threshold: ink pixels → 255, background → 0
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=25, C=10,
    )

    # Light denoise (remove isolated pixel noise)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kern)

    # Connected components
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    # Filter to letter-like components
    valid_ids = _filter_letter_components(stats, n_labels, h, w)

    # Detect text lines from horizontal projection
    h_proj = binary.sum(axis=1).astype(float)
    lines = _detect_text_lines(h_proj, h)

    # Assign components to lines
    line_comps = _assign_to_lines(valid_ids, stats, lines)

    # Compute slant angles once (shared by two metrics)
    angles = _get_component_angles(valid_ids, labels)

    # ── 11 metrics ─────────────────────────────────────────────────────────────
    baseline_str  = _baseline_straightness(line_comps, stats)
    letter_tight  = _letter_spacing_tightness(line_comps, stats)
    word_sp       = _word_spacing(line_comps, stats)
    size_cons     = _size_consistency(valid_ids, stats)
    avg_sz        = _average_size(valid_ids, stats, h)
    slant_ang     = _slant_angle(angles)
    slant_cons    = _slant_consistency(angles)
    press_var     = _pressure_variation(binary)
    margin_cons   = _margin_consistency(line_comps, stats, w)
    line_sp       = _line_spacing(lines, h)
    neat          = _neatness(baseline_str, size_cons, slant_cons, press_var, margin_cons)

    scores = {
        "baseline_straightness":    baseline_str,
        "letter_spacing_tightness": letter_tight,
        "word_spacing":             word_sp,
        "size_consistency":         size_cons,
        "average_size":             avg_sz,
        "slant_angle":              slant_ang,
        "slant_consistency":        slant_cons,
        "pressure_variation":       press_var,
        "neatness":                 neat,
        "margin_consistency":       margin_cons,
        "line_spacing":             line_sp,
    }
    return {k: float(round(max(0.0, min(100.0, v)), 1)) for k, v in scores.items()}


# ── Image loading ───────────────────────────────────────────────────────────────

def _load_image(image_input) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        return image_input
    if isinstance(image_input, (str, Path)):
        img = cv2.imread(str(image_input))
        if img is None:
            raise ValueError(f"Cannot load image: {image_input}")
        return img
    if isinstance(image_input, (bytes, bytearray)):
        arr = np.frombuffer(image_input, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Cannot decode image bytes")
        return img
    raise TypeError(f"Unsupported image input type: {type(image_input)}")


# ── Component filtering ─────────────────────────────────────────────────────────

def _filter_letter_components(stats: np.ndarray, n_labels: int, h: int, w: int) -> list[int]:
    """Return indices of connected components that plausibly represent letters."""
    min_h   = max(5,  h // 80)
    max_h   = h // 3
    min_area = max(15, min_h * 3)
    valid = []
    for i in range(1, n_labels):
        cx, cy, cw, ch, area = stats[i, :5]
        if area < min_area or area > h * w * 0.04:
            continue
        if ch < min_h or ch > max_h:
            continue
        if cw < 3 or cw > w * 0.25:
            continue
        aspect = cw / max(1, ch)
        if aspect > 6.0 or aspect < 0.05:
            continue
        valid.append(i)
    return valid


# ── Text-line detection ─────────────────────────────────────────────────────────

def _detect_text_lines(h_proj: np.ndarray, h: int) -> list[tuple[int, int, int]]:
    """
    Find text-line y-ranges from the horizontal projection histogram.
    Returns list of (y_start, y_center, y_end) tuples.
    """
    k = max(3, h // 60)
    if k % 2 == 0:
        k += 1
    smoothed = np.convolve(h_proj, np.ones(k) / k, mode="same")

    threshold = max(smoothed.max() * 0.08, 1.0)
    lines: list[tuple[int, int, int]] = []
    in_line = False
    start = 0

    for i in range(h):
        if smoothed[i] > threshold and not in_line:
            in_line = True
            start = i
        elif smoothed[i] <= threshold and in_line:
            in_line = False
            lines.append((start, (start + i) // 2, i))
    if in_line:
        lines.append((start, (start + h) // 2, h))

    # Merge lines separated by fewer than 5 px
    merged: list[tuple[int, int, int]] = []
    for ls, lc, le in lines:
        if merged and ls - merged[-1][2] < 5:
            ps, _, _ = merged.pop()
            merged.append((ps, (ps + le) // 2, le))
        else:
            merged.append((ls, lc, le))

    return merged


# ── Line-component assignment ───────────────────────────────────────────────────

def _assign_to_lines(
    valid_ids: list[int],
    stats: np.ndarray,
    lines: list[tuple[int, int, int]],
) -> dict[int, list[int]]:
    """Map each component to its closest text line. Returns {line_idx: [comp_ids]}."""
    line_comps: dict[int, list[int]] = {i: [] for i in range(len(lines))}
    if not lines:
        return line_comps

    for comp_id in valid_ids:
        cy = int(stats[comp_id, cv2.CC_STAT_TOP] + stats[comp_id, cv2.CC_STAT_HEIGHT] // 2)
        best = 0
        best_dist = float("inf")
        for li, (ls, lc, le) in enumerate(lines):
            dist = 0 if ls <= cy <= le else min(abs(cy - ls), abs(cy - le))
            if dist < best_dist:
                best_dist = dist
                best = li
        line_comps[best].append(comp_id)

    return line_comps


# ── Per-component slant angles ──────────────────────────────────────────────────

def _get_component_angles(valid_ids: list[int], labels: np.ndarray) -> list[float]:
    """
    Estimate slant angle for each component by comparing mean-x of top vs bottom pixels.
    Positive angle = forward (rightward) lean; negative = backward lean.
    """
    angles: list[float] = []
    for comp_id in valid_ids:
        rows, cols = np.where(labels == comp_id)
        if len(rows) < 10:
            continue
        height = int(rows.max() - rows.min())
        if height < 8:
            continue
        quarter = max(2, height // 4)
        min_r = int(rows.min())
        max_r = int(rows.max())
        top_mask = rows < min_r + quarter
        bot_mask = rows > max_r - quarter
        if top_mask.sum() < 2 or bot_mask.sum() < 2:
            continue
        dx = float(cols[top_mask].mean() - cols[bot_mask].mean())
        angle = float(np.degrees(np.arctan2(dx, height)))
        if abs(angle) < 60:
            angles.append(angle)
    return angles


# ── Metric functions ────────────────────────────────────────────────────────────

def _baseline_straightness(
    line_comps: dict[int, list[int]], stats: np.ndarray
) -> float:
    """100 = ruler-straight baselines; 0 = very wavy."""
    residuals_all: list[float] = []
    for comp_ids in line_comps.values():
        if len(comp_ids) < 4:
            continue
        xs     = np.array([stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] // 2  for i in comp_ids], float)
        bottoms = np.array([stats[i, cv2.CC_STAT_TOP]  + stats[i, cv2.CC_STAT_HEIGHT]       for i in comp_ids], float)
        heights = np.array([stats[i, cv2.CC_STAT_HEIGHT] for i in comp_ids], float)
        med_h   = float(np.median(heights))
        if med_h <= 0:
            continue
        coeffs    = np.polyfit(xs, bottoms, 1)
        predicted = np.polyval(coeffs, xs)
        rel       = float(np.abs(bottoms - predicted).mean() / med_h)
        residuals_all.append(rel)

    if not residuals_all:
        return 70.0
    mean_rel = float(np.mean(residuals_all))
    return max(0.0, 100.0 * (1.0 - mean_rel / 0.5))


def _letter_spacing_tightness(
    line_comps: dict[int, list[int]], stats: np.ndarray
) -> float:
    """100 = letters tightly packed; 0 = very loose inter-letter gaps."""
    gaps_rel: list[float] = []
    for comp_ids in line_comps.values():
        if len(comp_ids) < 3:
            continue
        sids   = sorted(comp_ids, key=lambda i: stats[i, cv2.CC_STAT_LEFT])
        med_h  = float(np.median([stats[i, cv2.CC_STAT_HEIGHT] for i in sids]))
        for j in range(len(sids) - 1):
            right = stats[sids[j], cv2.CC_STAT_LEFT] + stats[sids[j], cv2.CC_STAT_WIDTH]
            left  = stats[sids[j + 1], cv2.CC_STAT_LEFT]
            gap   = max(0, left - right)
            gap_r = gap / max(1.0, med_h)
            if gap_r < 2.5:   # inter-letter, not word gap
                gaps_rel.append(gap_r)

    if not gaps_rel:
        return 50.0
    mean_gap = float(np.mean(gaps_rel))
    return max(0.0, 100.0 * (1.0 - mean_gap / 1.0))


def _word_spacing(
    line_comps: dict[int, list[int]], stats: np.ndarray
) -> float:
    """0 = words crammed together; 100 = very wide word gaps."""
    all_gaps: list[float] = []
    for comp_ids in line_comps.values():
        if len(comp_ids) < 3:
            continue
        sids  = sorted(comp_ids, key=lambda i: stats[i, cv2.CC_STAT_LEFT])
        med_h = float(np.median([stats[i, cv2.CC_STAT_HEIGHT] for i in sids]))
        for j in range(len(sids) - 1):
            right = stats[sids[j], cv2.CC_STAT_LEFT] + stats[sids[j], cv2.CC_STAT_WIDTH]
            left  = stats[sids[j + 1], cv2.CC_STAT_LEFT]
            gap   = left - right
            if gap > 0:
                all_gaps.append(gap / max(1.0, med_h))

    if not all_gaps:
        return 50.0
    arr = np.array(all_gaps)
    med = float(np.median(arr))
    # Word gaps are significantly larger than letter gaps
    word_thresh = max(1.5, med * 1.8)
    word_gaps = arr[arr > word_thresh]
    if len(word_gaps) == 0:
        return 25.0
    mean_wg = float(np.mean(word_gaps))
    return min(100.0, 15.0 + mean_wg * 12.0)


def _size_consistency(valid_ids: list[int], stats: np.ndarray) -> float:
    """100 = all letters same height; 0 = very inconsistent sizes."""
    if len(valid_ids) < 3:
        return 70.0
    heights = np.array([stats[i, cv2.CC_STAT_HEIGHT] for i in valid_ids], float)
    mean_h  = float(heights.mean())
    if mean_h == 0:
        return 70.0
    cv = float(heights.std() / mean_h)
    return max(0.0, 100.0 * (1.0 - cv / 0.5))


def _average_size(valid_ids: list[int], stats: np.ndarray, h: int) -> float:
    """0 = tiny letters; 100 = very large relative to page."""
    if not valid_ids:
        return 50.0
    heights = np.array([stats[i, cv2.CC_STAT_HEIGHT] for i in valid_ids], float)
    med_h   = float(np.median(heights))
    frac    = med_h / max(1, h)
    # Typical handwriting: ~3–8 % of page height
    return min(100.0, frac / 0.08 * 100.0)


def _slant_angle(angles: list[float]) -> float:
    """
    50 = upright; < 50 = backward slant (leftward lean); > 50 = forward slant (rightward).
    Maps angle range [−30°, +30°] → [0, 100].
    """
    if not angles:
        return 50.0
    mean_angle = float(np.median(angles))
    return 50.0 + mean_angle * (50.0 / 30.0)


def _slant_consistency(angles: list[float]) -> float:
    """100 = all letters same slant; 0 = random slant per letter."""
    if len(angles) < 3:
        return 70.0
    std_angle = float(np.std(angles))
    return max(0.0, 100.0 * (1.0 - std_angle / 20.0))


def _pressure_variation(binary: np.ndarray) -> float:
    """
    0 = uniform stroke width (even pressure); 100 = highly variable.
    Uses distance-transform-based stroke-width estimation per component.
    """
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    stroke_widths: list[float] = []
    for i in range(1, n_labels):
        if int(stats[i, cv2.CC_STAT_AREA]) < 50:
            continue
        mask = labels == i
        sw   = float(dist[mask].max()) * 2.0
        stroke_widths.append(sw)

    if len(stroke_widths) < 3:
        return 30.0
    sw  = np.array(stroke_widths)
    cv  = float(sw.std() / max(1.0, sw.mean()))
    return min(100.0, cv * 150.0)


def _neatness(
    baseline_str: float,
    size_cons: float,
    slant_cons: float,
    press_var: float,
    margin_cons: float,
) -> float:
    """Weighted composite neatness score."""
    press_neat = 100.0 - press_var
    return (
        baseline_str * 0.30
        + size_cons  * 0.25
        + slant_cons * 0.20
        + press_neat * 0.15
        + margin_cons * 0.10
    )


def _margin_consistency(
    line_comps: dict[int, list[int]], stats: np.ndarray, w: int
) -> float:
    """100 = very consistent left margin; 0 = ragged."""
    left_xs: list[int] = []
    for comp_ids in line_comps.values():
        if not comp_ids:
            continue
        left_xs.append(int(min(stats[i, cv2.CC_STAT_LEFT] for i in comp_ids)))

    if len(left_xs) < 2:
        return 70.0
    rel_std = float(np.std(left_xs)) / max(1, w)
    return max(0.0, 100.0 * (1.0 - rel_std / 0.05))


def _line_spacing(lines: list[tuple[int, int, int]], h: int) -> float:
    """0 = lines very tight; 100 = very widely spaced."""
    if len(lines) < 2:
        return 50.0
    centers  = [lc for _, lc, _ in lines]
    gaps     = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    mean_gap = float(np.mean(gaps))
    line_hs  = [le - ls for ls, _, le in lines]
    mean_lh  = float(np.mean(line_hs)) if line_hs else 1.0
    ratio    = mean_gap / max(1.0, mean_lh)
    # ratio ~1 → near 0, ratio ~3 → ~66, ratio ~4.5 → ~100
    return min(100.0, max(0.0, (ratio - 1.0) * 28.0))
