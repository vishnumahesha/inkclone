#!/usr/bin/env python3
"""
extract_pipeline.py — Robust extraction pipeline for InkClone v4 template scans.

Handles CamScanner photos with perspective distortion, watermarks covering
corner markers, and inconsistent scan sizes by normalizing to 2550×3300.

Pipeline stages:
  1. Corner detection (bullseye matching + fallbacks)
  2. Perspective warp to 2550×3300
  3. Grid detection (Hough lines + projection profile fallback)
  4. Per-cell extraction with adaptive threshold + component filtering
  5. RGBA glyph conversion (128px height, black ink on transparent)
  6. Quality gate (ink coverage, aspect ratio checks)
  7. Test render
  8. Save to profile

Usage:
    python extract_pipeline.py [--profile vishnu_v4] [--debug]
"""

import sys
import json
import argparse
import shutil
from pathlib import Path
from datetime import datetime, timezone

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from template_layout import PAGE_LAYOUTS, COLS, ROWS, CELLS_PER_PAGE, char_to_stem

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_W, TARGET_H = 2550, 3300

SCAN_FILES = [
    ROOT / "template_v4_scan_page1.png",
    ROOT / "template_v4_scan_page2.png",
    ROOT / "template_v4_scan_page3.png",
]

# page1.png → page 3 (3/3), page2.png → page 2 (2/3), page3.png → page 1 (1/3)
_KNOWN_ORDER = {0: 3, 1: 2, 2: 1}

DEBUG = False


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1: Corner Detection
# ═══════════════════════════════════════════════════════════════════════════════

def _make_bullseye_template(size=60):
    """Generate a synthetic bullseye target (concentric circles)."""
    tpl = np.ones((size, size), dtype=np.uint8) * 255
    cx, cy = size // 2, size // 2
    # Outer ring
    cv2.circle(tpl, (cx, cy), size // 2 - 2, 0, -1)
    cv2.circle(tpl, (cx, cy), int(size * 0.32), 255, -1)
    # Inner dot
    cv2.circle(tpl, (cx, cy), int(size * 0.15), 0, -1)
    return tpl


def _find_bullseyes(gray, threshold=0.45):
    """Find bullseye corner markers using template matching at multiple scales."""
    best_matches = []

    for tpl_size in [40, 50, 60, 70, 80]:
        tpl = _make_bullseye_template(tpl_size)
        result = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        locs = np.where(result >= threshold)

        for pt_y, pt_x in zip(*locs):
            score = result[pt_y, pt_x]
            cx = pt_x + tpl_size // 2
            cy = pt_y + tpl_size // 2
            best_matches.append((cx, cy, float(score)))

    if not best_matches:
        return []

    # Non-maximum suppression: merge nearby detections
    best_matches.sort(key=lambda m: -m[2])
    kept = []
    for cx, cy, score in best_matches:
        too_close = False
        for kx, ky, _ in kept:
            if abs(cx - kx) < 80 and abs(cy - ky) < 80:
                too_close = True
                break
        if not too_close:
            kept.append((cx, cy, score))

    return kept


def _classify_corners(matches, img_w, img_h):
    """Assign detected points to TL, TR, BL, BR quadrants."""
    mid_x, mid_y = img_w / 2, img_h / 2
    corners = {}

    for cx, cy, score in matches:
        if cx < mid_x and cy < mid_y:
            key = 'TL'
        elif cx >= mid_x and cy < mid_y:
            key = 'TR'
        elif cx < mid_x and cy >= mid_y:
            key = 'BL'
        else:
            key = 'BR'

        if key not in corners or score > corners[key][2]:
            corners[key] = (cx, cy, score)

    return corners


def _infer_4th_corner(corners):
    """Given 3 corners, infer the missing 4th using rectangle geometry."""
    all_keys = {'TL', 'TR', 'BL', 'BR'}
    found = set(corners.keys())
    missing = all_keys - found

    if len(missing) != 1:
        return corners

    miss = missing.pop()
    pts = {k: np.array([v[0], v[1]], dtype=np.float32) for k, v in corners.items()}

    if miss == 'TL':
        inferred = pts['TR'] + pts['BL'] - pts['BR']
    elif miss == 'TR':
        inferred = pts['TL'] + pts['BR'] - pts['BL']
    elif miss == 'BL':
        inferred = pts['TL'] + pts['BR'] - pts['TR']
    else:  # BR
        inferred = pts['TR'] + pts['BL'] - pts['TL']

    corners[miss] = (float(inferred[0]), float(inferred[1]), 0.0)
    return corners


def _contour_fallback(gray):
    """Fallback: find page rectangle using contour detection."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 30, 100)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape

    # Find largest quadrilateral
    best = None
    best_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < w * h * 0.3:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4 and area > best_area:
            best = approx
            best_area = area

    if best is not None:
        pts = best.reshape(4, 2)
        # Sort: TL, TR, BR, BL
        s = pts.sum(axis=1)
        d = np.diff(pts, axis=1).flatten()
        tl = pts[np.argmin(s)]
        br = pts[np.argmax(s)]
        tr = pts[np.argmin(d)]
        bl = pts[np.argmax(d)]
        return {
            'TL': (float(tl[0]), float(tl[1]), 0.0),
            'TR': (float(tr[0]), float(tr[1]), 0.0),
            'BL': (float(bl[0]), float(bl[1]), 0.0),
            'BR': (float(br[0]), float(br[1]), 0.0),
        }

    # Ultimate fallback: use image edges with small margin
    margin_x = int(w * 0.02)
    margin_y = int(h * 0.02)
    return {
        'TL': (float(margin_x), float(margin_y), 0.0),
        'TR': (float(w - margin_x), float(margin_y), 0.0),
        'BL': (float(margin_x), float(h - margin_y), 0.0),
        'BR': (float(w - margin_x), float(h - margin_y), 0.0),
    }


def detect_corners(gray):
    """Stage 1: Detect 4 corner points with cascading fallbacks."""
    h, w = gray.shape
    matches = _find_bullseyes(gray)
    corners = _classify_corners(matches, w, h)

    n_found = len(corners)
    if n_found >= 3:
        if n_found == 3:
            corners = _infer_4th_corner(corners)
            if DEBUG:
                print(f"    Bullseye: 3 found, inferred 4th")
        else:
            if DEBUG:
                print(f"    Bullseye: all 4 found")
        return corners

    if n_found == 2:
        # Try to infer from diagonal pair
        keys = list(corners.keys())
        diag_pairs = [({'TL', 'BR'}, {'TR', 'BL'})]
        if set(keys) in [{'TL', 'BR'}, {'TR', 'BL'}]:
            corners = _infer_4th_corner(corners)
            if len(corners) == 3:
                corners = _infer_4th_corner(corners)
            if len(corners) == 4:
                if DEBUG:
                    print(f"    Bullseye: 2 diagonal found, inferred rest")
                return corners

    # Fallback to contour detection
    if DEBUG:
        print(f"    Bullseye: only {n_found} found, using contour fallback")
    return _contour_fallback(gray)


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2: Perspective Warp
# ═══════════════════════════════════════════════════════════════════════════════

def perspective_warp(img, corners):
    """Stage 2: Warp image to TARGET_W×TARGET_H using detected corners."""
    src_pts = np.array([
        [corners['TL'][0], corners['TL'][1]],
        [corners['TR'][0], corners['TR'][1]],
        [corners['BR'][0], corners['BR'][1]],
        [corners['BL'][0], corners['BL'][1]],
    ], dtype=np.float32)

    dst_pts = np.array([
        [0, 0],
        [TARGET_W, 0],
        [TARGET_W, TARGET_H],
        [0, TARGET_H],
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(img, M, (TARGET_W, TARGET_H),
                                  flags=cv2.INTER_LANCZOS4,
                                  borderMode=cv2.BORDER_REPLICATE)
    return warped


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 3: Grid Detection
# ═══════════════════════════════════════════════════════════════════════════════

def _hough_grid_lines(gray):
    """Detect grid lines using Hough transform on warped image."""
    # Enhance grid lines
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 50, 150)

    # Detect lines
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                             minLineLength=TARGET_W // 4, maxLineGap=20)

    v_lines = []  # x-coordinates of vertical lines
    h_lines = []  # y-coordinates of horizontal lines

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)

            if angle > 80:  # Vertical
                x_mid = (x1 + x2) / 2
                v_lines.append(x_mid)
            elif angle < 10:  # Horizontal
                y_mid = (y1 + y2) / 2
                h_lines.append(y_mid)

    return v_lines, h_lines


def _cluster_lines(values, expected_count, min_spacing=30):
    """Cluster detected line positions and pick the best set."""
    if not values:
        return []

    values = sorted(values)
    clusters = []
    cluster = [values[0]]

    for v in values[1:]:
        if v - cluster[-1] < min_spacing:
            cluster.append(v)
        else:
            clusters.append(int(np.median(cluster)))
            cluster = [v]
    clusters.append(int(np.median(cluster)))

    return clusters


def _projection_profile_fallback(gray):
    """Fallback grid detection using projection profiles."""
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)

    # Detect horizontal lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (TARGET_W // 3, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    h_proj = h_lines.sum(axis=1) // 255

    h_peaks = []
    in_peak = False
    peak_start = 0
    for i, v in enumerate(h_proj):
        if v > TARGET_W * 0.2 and not in_peak:
            in_peak = True
            peak_start = i
        elif v <= TARGET_W * 0.2 and in_peak:
            in_peak = False
            h_peaks.append((peak_start + i) // 2)
    if in_peak:
        h_peaks.append((peak_start + len(h_proj) - 1) // 2)

    # Detect vertical lines
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, TARGET_H // 4))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
    v_proj = v_lines.sum(axis=0) // 255

    v_peaks = []
    in_peak = False
    for i, v in enumerate(v_proj):
        if v > TARGET_H * 0.15 and not in_peak:
            in_peak = True
            peak_start = i
        elif v <= TARGET_H * 0.15 and in_peak:
            in_peak = False
            v_peaks.append((peak_start + i) // 2)
    if in_peak:
        v_peaks.append((peak_start + len(v_proj) - 1) // 2)

    return v_peaks, h_peaks


def detect_grid(gray):
    """Stage 3: Detect 8×13 grid on the warped 2550×3300 image.

    Returns (x_positions, y_positions) — lists of column and row boundaries.
    x_positions has 9 values (8 columns), y_positions has 14 values (13 rows).
    """
    v_lines, h_lines = _hough_grid_lines(gray)
    v_clusters = _cluster_lines(v_lines, 9, min_spacing=50)
    h_clusters = _cluster_lines(h_lines, 14, min_spacing=50)

    # If Hough didn't find enough, try projection profiles
    if len(v_clusters) < 5 or len(h_clusters) < 8:
        if DEBUG:
            print(f"    Hough: {len(v_clusters)}V/{len(h_clusters)}H — using projection fallback")
        v_proj, h_proj = _projection_profile_fallback(gray)
        if len(v_proj) > len(v_clusters):
            v_clusters = v_proj
        if len(h_proj) > len(h_clusters):
            h_clusters = h_proj

    # If still not enough, use computed positions based on target dimensions
    if len(v_clusters) < 5 or len(h_clusters) < 8:
        if DEBUG:
            print(f"    Fallback: computed grid from known layout")
        return _computed_grid()

    # Validate and refine
    v_clusters = sorted(v_clusters)
    h_clusters = sorted(h_clusters)

    if DEBUG:
        print(f"    Grid detected: {len(v_clusters)}V × {len(h_clusters)}H lines")

    return v_clusters, h_clusters


def _computed_grid():
    """Compute grid positions from known template proportions on 2550×3300."""
    # Template margins (from PDF generation): left ~6%, header ~14%
    x_left = int(TARGET_W * 0.062)
    usable_w = int(TARGET_W * 0.876)
    cell_w = usable_w // COLS

    y_top = int(TARGET_H * 0.14)
    usable_h = int(TARGET_H * 0.84)
    cell_h = usable_h // ROWS

    v_lines = [x_left + i * cell_w for i in range(COLS + 1)]
    h_lines = [y_top + i * cell_h for i in range(ROWS + 1)]
    return v_lines, h_lines


def grid_to_cells(v_lines, h_lines):
    """Convert grid lines to cell bounding boxes.

    Returns list of (x0, y0, x1, y1) for each of the ROWS*COLS cells,
    indexed row-major (cell 0 = top-left, cell 7 = top-right, etc.)
    """
    # Ensure we have enough grid lines; pad with computed if needed
    v_computed, h_computed = _computed_grid()

    if len(v_lines) < COLS + 1:
        v_lines = v_computed
    if len(h_lines) < ROWS + 1:
        h_lines = h_computed

    # If we have more lines than expected, pick the best COLS+1 / ROWS+1
    if len(v_lines) > COLS + 1:
        # Keep lines that form the most uniform spacing
        v_lines = _pick_uniform_lines(v_lines, COLS + 1)
    if len(h_lines) > ROWS + 1:
        h_lines = _pick_uniform_lines(h_lines, ROWS + 1)

    v_lines = sorted(v_lines)
    h_lines = sorted(h_lines)

    cells = []
    for row in range(ROWS):
        for col in range(COLS):
            x0 = v_lines[col]
            x1 = v_lines[col + 1] if col + 1 < len(v_lines) else v_lines[-1]
            y0 = h_lines[row]
            y1 = h_lines[row + 1] if row + 1 < len(h_lines) else h_lines[-1]
            cells.append((int(x0), int(y0), int(x1), int(y1)))

    return cells


def _pick_uniform_lines(lines, n):
    """From a list of line positions, pick n that form the most uniform spacing."""
    lines = sorted(lines)
    if len(lines) <= n:
        return lines

    # Use dynamic programming to find n lines with minimum spacing variance
    # Simplified: just use first and last, interpolate, snap to nearest detected
    first, last = lines[0], lines[-1]
    ideal = np.linspace(first, last, n)
    picked = []
    used = set()
    for target in ideal:
        best_idx = min(range(len(lines)), key=lambda i: abs(lines[i] - target))
        if best_idx not in used:
            picked.append(lines[best_idx])
            used.add(best_idx)
        else:
            picked.append(int(target))
    return sorted(picked)


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 4: Per-Cell Extraction
# ═══════════════════════════════════════════════════════════════════════════════

def _remove_grid_lines(binary):
    """Remove horizontal and vertical grid lines via morphological operations.

    This is the same proven approach from the glyph cleaning script:
    detect long horizontal/vertical structures and subtract them.
    """
    h, w = binary.shape
    cleaned = binary.copy()

    # Remove horizontal lines: detect structures wider than half the cell
    h_kernel_len = max(w // 2, 30)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    # Dilate slightly to catch thin line edges
    h_lines = cv2.dilate(h_lines, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)),
                          iterations=1)
    cleaned = cv2.subtract(cleaned, h_lines)

    # Remove vertical lines: detect structures taller than half the cell
    v_kernel_len = max(h // 2, 30)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_len))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
    v_lines = cv2.dilate(v_lines, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)),
                          iterations=1)
    cleaned = cv2.subtract(cleaned, v_lines)

    # Re-close small gaps caused by line removal
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, close_kernel)

    return cleaned


def extract_cell_ink(cell_gray, cell_idx):
    """Extract handwriting ink from a single cell crop.

    Uses adaptive threshold + morphological line removal + connected component
    filtering to separate handwriting from grid remnants and printed labels.
    """
    h, w = cell_gray.shape
    if h < 20 or w < 20:
        return None

    # Inset from grid lines to avoid edge artifacts
    inset = 4
    cell_gray = cell_gray[inset:h - inset, inset:w - inset]
    h, w = cell_gray.shape

    # Fixed threshold at 140 — proven stable for v4 scans.
    # Ink is dark (<100), guide lines are light gray (>150 after scanning).
    # Adaptive threshold picks up too much CamScanner compression noise.
    median_val = np.median(cell_gray)
    thresh_val = min(140, int(median_val - 45))
    _, binary = cv2.threshold(cell_gray, thresh_val, 255, cv2.THRESH_BINARY_INV)

    # Morphological line removal — proven approach from cleaning script
    binary = _remove_grid_lines(binary)

    # Remove small noise
    noise_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, noise_kernel)

    # Connected component analysis for label removal
    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    keep_mask = np.zeros_like(binary)
    label_zone_h = int(h * 0.18)  # Top 18% is label area

    # Separate label-zone components from handwriting-zone components
    hw_components = []  # (label_idx, area) for components below label zone
    label_components = []  # components entirely in label zone

    for i in range(1, n_labels):
        x, y, cw, ch, area = stats[i]

        # Skip tiny noise
        if cw < 6 or ch < 6:
            continue
        if area < 25:
            continue

        # Check if entirely in label zone
        if y + ch < label_zone_h:
            label_components.append(i)
            continue

        # Skip components that span nearly the full width/height (grid remnants)
        if cw > w * 0.90 and ch < 8:
            continue
        if ch > h * 0.90 and cw < 8:
            continue

        hw_components.append((i, area))

    # Keep handwriting components
    for i, area in hw_components:
        keep_mask[labels == i] = 255

    # Use gap detection: if there's a clear vertical gap between label and
    # handwriting zones, only keep stuff below the gap
    if np.count_nonzero(keep_mask) > 0:
        row_ink = np.any(keep_mask > 0, axis=1)
        ink_rows = np.where(row_ink)[0]
        if len(ink_rows) > 1:
            # Look for largest gap in first 40% of cell height
            gap_search = int(h * 0.40)
            diffs = np.diff(ink_rows)
            gap_candidates = [(diffs[j], ink_rows[j], ink_rows[j + 1])
                              for j in range(len(diffs))
                              if ink_rows[j] < gap_search and diffs[j] > 8]
            if gap_candidates:
                biggest_gap = max(gap_candidates, key=lambda x: x[0])
                gap_bottom = biggest_gap[2]
                # Zero out everything above the gap
                keep_mask[:gap_bottom, :] = 0

    # Check if we have meaningful ink
    ink_pixels = np.count_nonzero(keep_mask)
    if ink_pixels < 40:
        return None

    return keep_mask


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 5: RGBA Conversion
# ═══════════════════════════════════════════════════════════════════════════════

def ink_to_rgba(ink_mask):
    """Stage 5: Convert binary ink mask to RGBA glyph at 128px height."""
    rows = np.any(ink_mask > 0, axis=1)
    cols = np.any(ink_mask > 0, axis=0)

    if not rows.any() or not cols.any():
        return None

    rmin, rmax = int(np.where(rows)[0][0]), int(np.where(rows)[0][-1])
    cmin, cmax = int(np.where(cols)[0][0]), int(np.where(cols)[0][-1])

    if (rmax - rmin) < 8 or (cmax - cmin) < 4:
        return None

    # Pad bounding box
    pad = 4
    rmin = max(0, rmin - pad)
    rmax = min(ink_mask.shape[0] - 1, rmax + pad)
    cmin = max(0, cmin - pad)
    cmax = min(ink_mask.shape[1] - 1, cmax + pad)

    cropped = ink_mask[rmin:rmax + 1, cmin:cmax + 1]
    ch, cw = cropped.shape

    # Resize to 128px height
    target_h = 128
    scale = target_h / max(ch, 1)
    target_w = max(1, int(round(cw * scale)))
    resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

    # Create RGBA: black ink at alpha 240, transparent background
    ink_pixels = resized > 128
    arr = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    arr[ink_pixels, 3] = 240  # alpha only, RGB stays 0 (black)

    return Image.fromarray(arr, "RGBA")


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 6: Quality Gate
# ═══════════════════════════════════════════════════════════════════════════════

def quality_check(glyph_img, char):
    """Stage 6: Flag glyphs with suspicious metrics.

    Returns (passed, flags) where flags is a list of warning strings.
    """
    arr = np.array(glyph_img)
    alpha = arr[:, :, 3]
    h, w = alpha.shape

    ink_pixels = np.count_nonzero(alpha > 0)
    total_pixels = h * w
    ink_coverage = ink_pixels / max(total_pixels, 1)

    flags = []
    passed = True

    if ink_coverage < 0.03:
        flags.append(f"low_ink({ink_coverage:.1%})")
        passed = False
    elif ink_coverage > 0.80:
        flags.append(f"high_ink({ink_coverage:.1%})")
        passed = False

    aspect = w / max(h, 1)
    if aspect > 4.0:
        flags.append(f"wide({aspect:.1f}:1)")
        passed = False
    elif aspect < 0.15:
        flags.append(f"tall({aspect:.2f}:1)")
        passed = False

    return passed, flags


# ═══════════════════════════════════════════════════════════════════════════════
# Full Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def process_page(img_path, page_dots):
    """Run the full pipeline on one scan page."""
    print(f"\n[{img_path.name}] page_dots={page_dots}")

    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read {img_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    print(f"  Input: {w}×{h}")

    # Stage 1: Corner detection
    corners = detect_corners(gray)
    corner_strs = {k: f"({int(v[0])},{int(v[1])})" for k, v in corners.items()}
    print(f"  Corners: {corner_strs}")

    # Stage 2: Perspective warp
    warped = perspective_warp(img, corners)
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    print(f"  Warped: {TARGET_W}×{TARGET_H}")

    # Stage 3: Grid detection
    v_lines, h_lines = detect_grid(warped_gray)
    cells = grid_to_cells(v_lines, h_lines)
    print(f"  Grid: {len(v_lines)}V × {len(h_lines)}H → {len(cells)} cells")

    # Get layout for this page
    layout = PAGE_LAYOUTS.get(page_dots, PAGE_LAYOUTS[1])

    # Stage 4-6: Extract each cell
    extracted = []
    empty = 0
    flagged = 0
    failed = 0

    for cell_idx, (x0, y0, x1, y1) in enumerate(cells):
        if cell_idx >= len(layout):
            break

        char = layout[cell_idx]
        if char is None:
            continue

        cell_gray = warped_gray[y0:y1, x0:x1]
        ink = extract_cell_ink(cell_gray, cell_idx)

        if ink is None:
            empty += 1
            continue

        glyph = ink_to_rgba(ink)
        if glyph is None:
            failed += 1
            continue

        passed, flags = quality_check(glyph, char)
        if not passed:
            flagged += 1
            if DEBUG:
                stem = char_to_stem(char)
                print(f"    FLAGGED {stem}: {', '.join(flags)}")

        # Keep all glyphs (even flagged ones — better than nothing)
        extracted.append((char, glyph, passed, flags))

    good = sum(1 for _, _, p, _ in extracted if p)
    print(f"  Result: {len(extracted)} extracted, {good} good, {flagged} flagged, {empty} empty, {failed} failed")

    return extracted


def run_pipeline(profile_name="vishnu_v4", do_render=True):
    """Main pipeline: process all pages and save profile."""
    print("=" * 60)
    print(f"InkClone Extraction Pipeline v2")
    print(f"Target: {TARGET_W}×{TARGET_H}, Grid: {COLS}×{ROWS}")
    print("=" * 60)

    profile_dir = ROOT / "profiles" / profile_name
    glyphs_dir = profile_dir / "glyphs"

    # Don't wipe existing — we'll overwrite individual files
    glyphs_dir.mkdir(parents=True, exist_ok=True)

    bank = {}  # char → list of (glyph, passed, flags)

    for file_idx, scan_path in enumerate(SCAN_FILES):
        if not scan_path.exists():
            print(f"  SKIP: {scan_path.name} not found")
            continue

        page_dots = _KNOWN_ORDER[file_idx]
        results = process_page(scan_path, page_dots)

        for char, glyph, passed, flags in results:
            bank.setdefault(char, []).append((glyph, passed, flags))

    # Stage 8: Save glyphs
    print(f"\n{'=' * 60}")
    print(f"Saving glyphs to {glyphs_dir}")

    saved = {}
    total_saved = 0
    total_flagged = 0

    for char, variants in bank.items():
        stem = char_to_stem(char)
        for v_idx, (glyph, passed, flags) in enumerate(variants):
            fname = f"{stem}_{v_idx}.png"
            glyph.save(str(glyphs_dir / fname))
            saved.setdefault(char, []).append(f"glyphs/{fname}")
            total_saved += 1
            if not passed:
                total_flagged += 1

    # Summary
    lc = sum(1 for c in saved if len(c) == 1 and c.islower())
    uc = sum(1 for c in saved if len(c) == 1 and c.isupper())
    dg = sum(1 for c in saved if len(c) == 1 and c.isdigit())
    bi = sum(1 for c in saved if len(c) > 1)

    print(f"\nQuality Gate Summary:")
    print(f"  Total glyphs: {total_saved}")
    print(f"  Passed: {total_saved - total_flagged}")
    print(f"  Flagged: {total_flagged}")
    print(f"  Characters: {lc}/26 lower, {uc}/26 upper, {dg}/10 digits, {bi} bigrams")

    # Write profile.json
    profile = {
        "profile_id": profile_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_method": "extract_pipeline_v2",
        "template_version": "v4",
        "total_variants": total_saved,
        "quality_gate": {
            "passed": total_saved - total_flagged,
            "flagged": total_flagged,
        },
        "character_coverage": {
            "lowercase_pct": round(lc / 26 * 100, 1),
            "uppercase_pct": round(uc / 26 * 100, 1),
            "digits_pct": round(dg / 10 * 100, 1),
            "bigrams": bi,
            "total_variants": total_saved,
        },
        "per_character": {
            char: {"variants": len(paths), "files": paths}
            for char, paths in saved.items()
        },
        "usable": True,
    }

    with open(profile_dir / "profile.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    print(f"\nProfile written to {profile_dir / 'profile.json'}")

    # Stage 7: Test render
    if do_render:
        try:
            from render_engine import HandwritingRenderer
            from glyph_loader import load_profile_glyphs

            print(f"\nTest render...")
            glyphs = load_profile_glyphs(str(profile_dir))
            renderer = HandwritingRenderer(glyphs)
            test_text = "The quick brown fox jumps over the lazy dog. 0123456789"
            result = renderer.render(test_text)
            out_path = ROOT / "test_pipeline_output.png"
            result.save(str(out_path))
            print(f"  Saved test render: {out_path}")
        except Exception as e:
            print(f"  Test render failed: {e}")

    return profile_dir, saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InkClone v4 extraction pipeline")
    parser.add_argument("--profile", default="vishnu_v4")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()

    DEBUG = args.debug
    profile_dir, saved = run_pipeline(args.profile, do_render=not args.no_render)
    print(f"\n✅ Pipeline complete. Profile at {profile_dir}")
