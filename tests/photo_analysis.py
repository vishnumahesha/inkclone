#!/usr/bin/env python3
"""
tests/photo_analysis.py — Phase 2: real photo degradation analysis.

Measures 6 quality dimensions for each real template photo (IMG_3806-3809),
maps each measurement to the nearest Phase 1 degradation level, identifies
the primary bottleneck, and writes tests/photo_analysis.json.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PHOTO_PATHS = [
    ROOT / "profiles" / "IMG_38062.png",
    ROOT / "profiles" / "IMG_38072.png",
    ROOT / "profiles" / "IMG_38082.png",
    ROOT / "profiles" / "IMG_38092.png",
]

# Phase 1 level definitions (mirrors degradation_test.py)
LEVELS = {
    "A_resolution":    [2550, 2000, 1600, 1200, 800, 400],
    "B_rotation":      [0, 0.5, 1, 2, 4, 8],
    "C_lighting":      [1.0, 0.85, 0.7, 0.55, 0.4, 0.25],
    "D_noise":         [0, 5, 10, 20, 40, 80],
    "E_jpeg":          [100, 90, 80, 70, 60, 50],
    "F_ink_lightness": [0.0, 0.1, 0.3, 0.5, 0.7, 0.9],
}

# Phase 1 scores at each level (from degradation_results.json)
SCORES = {
    "A_resolution":    [238, 238, 238, 238, 238, 238],
    "B_rotation":      [238, 238, 238, 238, 237, 238],
    "C_lighting":      [238, 238, 238, 238, 238, 238],
    "D_noise":         [238, 238, 238, 238, 238, 238],
    "E_jpeg":          [238, 238, 238, 238, 238, 238],
    "F_ink_lightness": [238, 238, 238, 238,   0,   0],
}


def _nearest_level(value: float, levels: list) -> int:
    """Return index of nearest level value."""
    return int(np.argmin([abs(v - value) for v in levels]))


# ── Measurement functions ──────────────────────────────────────────────────────

def measure_resolution(img: np.ndarray) -> dict:
    h, w = img.shape[:2]
    # Effective width relative to 2550-px synthetic
    return {"width_px": w, "height_px": h,
            "effective_width": w,
            "level_idx": _nearest_level(w, LEVELS["A_resolution"])}


def measure_rotation(gray: np.ndarray) -> dict:
    """
    Detect dominant skew angle via Hough line detection on Canny edges.
    Returns angle in degrees (positive = clockwise tilt).
    """
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=150)
    if lines is None or len(lines) == 0:
        return {"angle_deg": 0.0, "n_lines": 0, "level_idx": 0}

    angles = []
    for line in lines:
        rho, theta = line[0]
        # Convert to degrees from vertical
        angle = np.degrees(theta) - 90
        if abs(angle) < 15:
            angles.append(angle)

    if not angles:
        return {"angle_deg": 0.0, "n_lines": len(lines), "level_idx": 0}

    angle_deg = float(np.median(angles))
    return {
        "angle_deg": round(angle_deg, 2),
        "n_lines": len(lines),
        "level_idx": _nearest_level(abs(angle_deg), LEVELS["B_rotation"]),
    }


def measure_lighting(gray: np.ndarray) -> dict:
    """
    Measure brightness uniformity via quadrant means.
    Returns per-quadrant means and overall mean (normalised 0–1).
    """
    h, w = gray.shape
    q = {
        "TL": gray[:h//2, :w//2],
        "TR": gray[:h//2, w//2:],
        "BL": gray[h//2:, :w//2],
        "BR": gray[h//2:, w//2:],
    }
    means = {k: float(v.mean()) / 255.0 for k, v in q.items()}
    overall = float(gray.mean()) / 255.0
    # Map to C_lighting factor (overall brightness relative to ideal white=1.0)
    factor = overall
    return {
        "quadrant_means": means,
        "overall_brightness": round(overall, 3),
        "brightness_factor": round(factor, 3),
        "level_idx": _nearest_level(factor, LEVELS["C_lighting"]),
    }


def measure_noise(gray: np.ndarray) -> dict:
    """
    Estimate noise std from smooth (non-edge) regions using the median
    absolute deviation of the Laplacian in background patches.
    """
    # Identify background pixels (bright, not ink)
    bg_mask = gray > 180
    if bg_mask.sum() < 100:
        return {"noise_std": 0.0, "level_idx": 0}
    lap = cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F)
    bg_lap = lap[bg_mask]
    noise_std = float(np.std(bg_lap)) / np.sqrt(2)  # Laplacian amplifies by sqrt(2)
    return {
        "noise_std": round(noise_std, 2),
        "level_idx": _nearest_level(noise_std, LEVELS["D_noise"]),
    }


def measure_jpeg(img_path: Path) -> dict:
    """
    Estimate JPEG compression quality by checking for DCT block artifacts
    (8×8 blocking) on a luminance channel.
    PNG is lossless → quality≈100; actual JPEG is decoded, so we detect artifacts.
    """
    if img_path.suffix.lower() in (".png",):
        # PNG: lossless, no JPEG artifacts
        return {"jpeg_quality_estimate": 100, "is_png": True, "level_idx": 0}

    # For JPEG: estimate quality from blocking artifact strength
    img = cv2.imread(str(img_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    # Measure 8-px boundary vs interior contrast
    block = 8
    h_crop = (h // block) * block
    w_crop = (w // block) * block
    g = gray[:h_crop, :w_crop]
    boundary_diff = 0.0
    interior_diff = 0.0
    for r in range(0, h_crop - block, block):
        boundary_diff += abs(float(g[r + block - 1, :].mean()) -
                             float(g[r + block, :].mean()))
        interior_diff += abs(float(g[r + 3, :].mean()) -
                             float(g[r + 4, :].mean()))
    n_blocks = h_crop // block
    ratio = boundary_diff / max(interior_diff, 1e-6)
    # High ratio → strong blocking → low quality
    if ratio < 1.5:
        quality_est = 95
    elif ratio < 2.5:
        quality_est = 80
    elif ratio < 4.0:
        quality_est = 70
    else:
        quality_est = 60
    return {
        "jpeg_quality_estimate": quality_est,
        "blocking_ratio": round(ratio, 2),
        "level_idx": _nearest_level(quality_est, LEVELS["E_jpeg"]),
    }


def measure_ink_lightness(img_bgr: np.ndarray) -> dict:
    """
    Measure ink darkness using the RED CHANNEL (matches extraction threshold).
    Ink pixels: gray < 100.  Reports median red-channel value of ink region.
    Lightness fraction = median_R / 255  (0=black ink, 1=white/invisible).
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    red  = img_bgr[:, :, 2]  # BGR: red = index 2
    ink_mask = gray < 100
    n_ink = int(ink_mask.sum())
    if n_ink < 10:
        # No clear ink found — assume worst case
        return {"ink_pixel_count": n_ink, "ink_median_red": 255,
                "ink_lightness_fraction": 1.0, "level_idx": 5}
    ink_red_median = float(np.median(red[ink_mask]))
    lightness_fraction = ink_red_median / 255.0
    pct_below_threshold = float((red[ink_mask] < 160).mean())
    return {
        "ink_pixel_count":       n_ink,
        "ink_median_red":        round(ink_red_median, 1),
        "ink_lightness_fraction": round(lightness_fraction, 3),
        "pct_captured_by_threshold": round(pct_below_threshold, 3),
        "level_idx": _nearest_level(lightness_fraction, LEVELS["F_ink_lightness"]),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def analyze_photo(img_path: Path, page_num: int) -> dict:
    img = cv2.imread(str(img_path))
    if img is None:
        return {"error": f"Cannot load {img_path}"}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    res  = measure_resolution(img)
    rot  = measure_rotation(gray)
    lit  = measure_lighting(gray)
    noi  = measure_noise(gray)
    jpg  = measure_jpeg(img_path)
    ink  = measure_ink_lightness(img)

    dims = {
        "A_resolution":    res,
        "B_rotation":      rot,
        "C_lighting":      lit,
        "D_noise":         noi,
        "E_jpeg":          jpg,
        "F_ink_lightness": ink,
    }

    # Risk score per dimension.
    # Primary key: phase-1 score gap (238 - score_at_level); if all equal,
    # use level_idx as tiebreaker (further from 0 = more degraded).
    risk = {}
    for dim_key, meas in dims.items():
        lv = meas["level_idx"]
        score_at_lv = SCORES[dim_key][lv]
        score_gap = 238 - score_at_lv
        risk[dim_key] = (score_gap, lv)  # tuple: (score_gap, level_idx)

    sorted_risk = sorted(risk.items(), key=lambda x: (-x[1][0], -x[1][1]))
    primary   = sorted_risk[0][0] if sorted_risk else None
    secondary = sorted_risk[1][0] if len(sorted_risk) > 1 else None

    return {
        "photo": img_path.name,
        "page":  page_num,
        "measurements": dims,
        "risk_scores": {k: v[1] for k, v in risk.items()},   # store level_idx
        "primary_bottleneck":   primary,
        "secondary_bottleneck": secondary,
    }


def run():
    results = []
    for i, path in enumerate(PHOTO_PATHS, start=1):
        page_num = i
        print(f"\nAnalyzing {path.name} (page {page_num}) ...")
        r = analyze_photo(path, page_num)
        results.append(r)

        m = r["measurements"]
        print(f"  Resolution : {m['A_resolution']['width_px']}×{m['A_resolution']['height_px']} px  → level {m['A_resolution']['level_idx']}")
        print(f"  Rotation   : {m['B_rotation']['angle_deg']:+.1f}°  ({m['B_rotation']['n_lines']} Hough lines)  → level {m['B_rotation']['level_idx']}")
        print(f"  Lighting   : factor {m['C_lighting']['brightness_factor']:.2f}  → level {m['C_lighting']['level_idx']}")
        print(f"  Noise      : std {m['D_noise']['noise_std']:.1f}  → level {m['D_noise']['level_idx']}")
        print(f"  JPEG       : quality ~{m['E_jpeg']['jpeg_quality_estimate']}  → level {m['E_jpeg']['level_idx']}")
        print(f"  Ink        : lightness {m['F_ink_lightness']['ink_lightness_fraction']:.3f}  → level {m['F_ink_lightness']['level_idx']}")
        print(f"  PRIMARY    : {r['primary_bottleneck']}")
        print(f"  SECONDARY  : {r['secondary_bottleneck']}")

    out_path = ROOT / "tests" / "photo_analysis.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")

    # Aggregate bottleneck ranking
    from collections import Counter
    primaries = Counter(r["primary_bottleneck"] for r in results)
    secondaries = Counter(r["secondary_bottleneck"] for r in results)
    print("\n=== AGGREGATE BOTTLENECK RANKING ===")
    print("Primary:  ", dict(primaries))
    print("Secondary:", dict(secondaries))

    return results


if __name__ == "__main__":
    run()
