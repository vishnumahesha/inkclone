"""
InkClone Template Segmenter
Crops cells at known grid positions and extracts glyph images.
"""

import os
import sys
import numpy as np
import cv2
from PIL import Image

from preprocess import correct_perspective, normalize_background, binarize, create_test_image

# ── Template Configuration ────────────────────────────────────────────────────
# All measurements in points (PDF) converted to inches, then to px at 300 DPI.
# Page: 8.5 × 11 inches at 300 DPI = 2550 × 3300 px
# Margins: 0.5 inch = 150 px at 300 DPI
# Cell: 34pt wide × 42pt tall  →  at 300 DPI: 34/72*300 ≈ 141.7 → 142 px wide, 42/72*300 ≈ 175 px tall
# Gaps: H_GAP=4pt → 16.7px, V_GAP=14pt → 58.3px
# Title area: ~20pt → 83px below top margin

DPI = 300
PT_PER_INCH = 72.0

def _pt2px(pt):
    return int(round(pt / PT_PER_INCH * DPI))

MARGIN_PX = _pt2px(36)          # 0.5 inch margin
CELL_W_PX = _pt2px(34)
CELL_H_PX = _pt2px(42)
H_GAP_PX  = _pt2px(4)
V_GAP_PX  = _pt2px(14)
TITLE_H_PX = _pt2px(20)         # space for page title

# Top of grid start (from top of page in pixels, y increases downward)
GRID_TOP_PX = MARGIN_PX + TITLE_H_PX

TEMPLATE_CONFIG = {
    'dpi': DPI,
    'page_w_px': 2550,
    'page_h_px': 3300,
    'margin_px': MARGIN_PX,
    'cell_w_px': CELL_W_PX,
    'cell_h_px': CELL_H_PX,
    'h_gap_px': H_GAP_PX,
    'v_gap_px': V_GAP_PX,
    'grid_top_px': GRID_TOP_PX,
    'pages': {
        0: {'cols': 8},   # Lowercase
        1: {'cols': 9},   # Uppercase + Digits
        2: {'cols': 8},   # Punctuation
    }
}


# ── Cell Map ──────────────────────────────────────────────────────────────────
def _build_page0_chars():
    """Lowercase: a-z, 4 variants each, 8 cols."""
    chars = []
    letters = 'abcdefghijklmnopqrstuvwxyz'
    for i in range(0, 26, 2):
        pair = letters[i:i+2]
        for ch in pair:
            chars.extend([ch] * 4)
    return chars  # 104 chars


def _build_page1_chars():
    """Uppercase A-Z (3 variants) + digits 0-9 (2 variants), 9 cols."""
    chars = []
    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    for i in range(0, 24, 3):
        for ch in letters[i:i+3]:
            chars.extend([ch] * 3)
    # Row 8: Y,Y,Y,Z,Z,Z + 3 empty
    chars.extend(['Y'] * 3 + ['Z'] * 3 + [''] * 3)
    # Digits
    digit_seq = []
    for d in '0123456789':
        digit_seq.extend([d] * 2)
    while len(digit_seq) < 27:
        digit_seq.append('')
    chars.extend(digit_seq[:27])
    return chars


def _build_page2_chars():
    """Punctuation: 2 variants each, 8 cols."""
    punct = ['.', ',', '!', '?', "'", '"', '-', ':', ';', '(', ')', '/', '@', '&', '#', '+', '=', '*']
    chars = []
    for ch in punct:
        chars.extend([ch] * 2)
    while len(chars) % 8 != 0:
        chars.append('')
    return chars


def build_cell_map():
    """
    Build mapping (page_index, row, col) → character.

    Returns:
        dict: {(page, row, col): char_or_empty_string}
    """
    cell_map = {}
    pages_chars = [
        _build_page0_chars(),
        _build_page1_chars(),
        _build_page2_chars(),
    ]
    page_cols = [8, 9, 8]

    for page_idx, (chars, cols) in enumerate(zip(pages_chars, page_cols)):
        for i, ch in enumerate(chars):
            row = i // cols
            col = i % cols
            cell_map[(page_idx, row, col)] = ch

    return cell_map


# ── Cell Position Computation ─────────────────────────────────────────────────
def compute_cell_positions(page_index, dpi=300):
    """
    Compute cell bounding boxes for a given page.

    Returns list of dicts:
        {'char': str, 'variant': int, 'x': int, 'y': int, 'w': int, 'h': int}
    where (x, y) is top-left in image coordinates (y=0 at top).
    """
    cell_map = build_cell_map()
    cols = TEMPLATE_CONFIG['pages'][page_index]['cols']

    # Find all cells on this page
    page_cells = {(r, c): ch for (p, r, c), ch in cell_map.items() if p == page_index}

    # Count variant index: for same char, sort by (row, col) and assign 0,1,2,...
    from collections import defaultdict
    char_seen = defaultdict(int)

    results = []
    for (row, col), char in sorted(page_cells.items()):
        x = MARGIN_PX + col * (CELL_W_PX + H_GAP_PX)
        y = GRID_TOP_PX + row * (CELL_H_PX + V_GAP_PX)

        variant = char_seen[char]
        char_seen[char] += 1

        results.append({
            'char': char,
            'variant': variant,
            'x': x,
            'y': y,
            'w': CELL_W_PX,
            'h': CELL_H_PX,
        })

    return results


# ── Glyph Extraction ──────────────────────────────────────────────────────────
INK_THRESHOLD = 128       # pixel value below this = ink (in binarized image where ink=255, background=0)
MIN_INK_FRACTION = 0.01   # at least 1% of cell must be ink
TARGET_HEIGHT = 128       # normalize glyph height to this many pixels


def extract_glyph_from_cell(image, cell, padding=5):
    """
    Extract a glyph from a cell region of a binarized image.

    Args:
        image: numpy array, grayscale binarized (ink=255, background=0)
               OR BGR image (will be binarized internally)
        cell: dict with keys x, y, w, h, char, variant
        padding: pixels to add around tight bounding box

    Returns:
        (PIL.Image RGBA, metadata_dict) or (None, None) if no ink found.

    Metadata keys:
        char, variant, original_width, original_height,
        baseline_offset, left_bearing, right_bearing, ink_density
    """
    x, y, w, h = cell['x'], cell['y'], cell['w'], cell['h']
    char = cell.get('char', '')
    variant = cell.get('variant', 0)

    # Crop cell from image
    ih, iw = image.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(iw, x + w)
    y2 = min(ih, y + h)

    if x2 <= x1 or y2 <= y1:
        return None, None

    crop = image[y1:y2, x1:x2]

    # Ensure grayscale
    if len(crop.shape) == 3:
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        # Binarize if not already binary
        _, crop_bin = cv2.threshold(crop_gray, 127, 255, cv2.THRESH_BINARY)
    else:
        crop_bin = crop.copy()
        if np.max(crop_bin) <= 1:
            crop_bin = (crop_bin * 255).astype(np.uint8)

    # Check for ink presence
    ink_pixels = int(np.sum(crop_bin > 127))
    total_pixels = crop_bin.size
    ink_density = ink_pixels / total_pixels if total_pixels > 0 else 0.0

    if ink_density < MIN_INK_FRACTION:
        return None, None

    # Find tight bounding box of ink
    ink_mask = crop_bin > 127
    rows = np.any(ink_mask, axis=1)
    cols = np.any(ink_mask, axis=0)
    row_min, row_max = np.where(rows)[0][[0, -1]]
    col_min, col_max = np.where(cols)[0][[0, -1]]

    orig_h, orig_w = crop_bin.shape
    original_width  = int(col_max - col_min + 1)
    original_height = int(row_max - row_min + 1)

    # Bearings
    left_bearing  = int(col_min)
    right_bearing = int(orig_w - col_max - 1)

    # Baseline offset: percentage of cell height (baseline at 60% from top)
    baseline_row = int(orig_h * 0.60)
    baseline_offset = int(baseline_row - row_min)

    # Tight crop with padding
    r1 = max(0, row_min - padding)
    r2 = min(orig_h, row_max + padding + 1)
    c1 = max(0, col_min - padding)
    c2 = min(orig_w, col_max + padding + 1)
    tight = crop_bin[r1:r2, c1:c2]

    # Normalize height to TARGET_HEIGHT preserving aspect ratio
    th, tw = tight.shape
    if th == 0 or tw == 0:
        return None, None

    scale = TARGET_HEIGHT / th
    new_w = max(1, int(tw * scale))
    resized = cv2.resize(tight, (new_w, TARGET_HEIGHT), interpolation=cv2.INTER_AREA)

    # Build RGBA image: RGB = grayscale value, A = opacity from ink darkness
    # ink pixels (bright=255 in binarized) → alpha=255, background → alpha=0
    rgba = np.zeros((TARGET_HEIGHT, new_w, 4), dtype=np.uint8)
    rgba[:, :, 0] = resized   # R
    rgba[:, :, 1] = resized   # G
    rgba[:, :, 2] = resized   # B
    rgba[:, :, 3] = resized   # A (ink is 255 → fully opaque)

    pil_img = Image.fromarray(rgba, mode='RGBA')

    metadata = {
        'char': char,
        'variant': variant,
        'original_width': original_width,
        'original_height': original_height,
        'baseline_offset': baseline_offset,
        'left_bearing': left_bearing,
        'right_bearing': right_bearing,
        'ink_density': round(ink_density, 4),
    }

    return pil_img, metadata


# ── Page Segmentation ─────────────────────────────────────────────────────────
def segment_template_page(image, page_index):
    """
    Segment one page image into glyphs.

    Args:
        image: numpy array (BGR or grayscale), already corrected/normalized
        page_index: 0=lowercase, 1=uppercase+digits, 2=punctuation

    Returns:
        dict: {char: [(PIL.Image RGBA, metadata_dict), ...]}
    """
    # Normalize and binarize
    normalized = normalize_background(image)
    binary = binarize(normalized)

    cells = compute_cell_positions(page_index)
    results = {}

    for cell in cells:
        char = cell['char']
        if not char:
            continue

        glyph_img, meta = extract_glyph_from_cell(binary, cell)
        if glyph_img is None:
            continue

        if char not in results:
            results[char] = []
        results[char].append((glyph_img, meta))

    return results


def segment_full_template(image_paths):
    """
    Process all template pages with preprocessing.

    Args:
        image_paths: list of paths (page0, page1, page2) — or fewer

    Returns:
        dict: {char: [(PIL.Image RGBA, metadata_dict), ...]}
    """
    all_glyphs = {}

    for page_index, img_path in enumerate(image_paths):
        if not os.path.exists(img_path):
            print(f"  Skipping missing page: {img_path}")
            continue

        img = cv2.imread(img_path)
        if img is None:
            print(f"  Cannot read: {img_path}")
            continue

        # Perspective correction
        img = correct_perspective(img)

        page_glyphs = segment_template_page(img, page_index)
        for char, variants in page_glyphs.items():
            if char not in all_glyphs:
                all_glyphs[char] = []
            all_glyphs[char].extend(variants)

    return all_glyphs


# ── Synthetic Test ────────────────────────────────────────────────────────────
def _create_synthetic_page(page_index, draw_every_nth=3):
    """
    Create a synthetic page image with circles drawn in every Nth cell.
    Returns numpy array BGR at OUTPUT_W × OUTPUT_H.
    """
    from preprocess import OUTPUT_W, OUTPUT_H
    img = np.ones((OUTPUT_H, OUTPUT_W, 3), dtype=np.uint8) * 255  # white background

    cells = compute_cell_positions(page_index)
    for i, cell in enumerate(cells):
        if not cell['char']:
            continue
        if i % draw_every_nth == 0:
            cx = cell['x'] + cell['w'] // 2
            cy = cell['y'] + cell['h'] // 2
            radius = min(cell['w'], cell['h']) // 3
            cv2.circle(img, (cx, cy), radius, (20, 20, 20), -1)

    return img


if __name__ == '__main__':
    print("=" * 60)
    print("segment.py — running self-tests")
    print("=" * 60)

    os.makedirs('test_images', exist_ok=True)
    os.makedirs('output', exist_ok=True)

    # ── Test 1: build_cell_map ──────────────────────────────────────
    print("\n[1] Testing build_cell_map()...")
    cell_map = build_cell_map()
    total_cells = len(cell_map)
    print(f"    Total cells in map: {total_cells}")
    # Page 0: 13 rows × 8 cols = 104
    page0 = [(r, c) for (p, r, c) in cell_map if p == 0]
    print(f"    Page 0 cells: {len(page0)} (expect 104)")
    assert len(page0) == 104, f"Expected 104, got {len(page0)}"
    # Page 1: rows 0-11 × 9 cols = 108
    page1 = [(r, c) for (p, r, c) in cell_map if p == 1]
    print(f"    Page 1 cells: {len(page1)} (expect 108)")
    assert len(page1) == 108, f"Expected 108, got {len(page1)}"
    print("    PASS")

    # ── Test 2: compute_cell_positions ──────────────────────────────
    print("\n[2] Testing compute_cell_positions()...")
    positions = compute_cell_positions(0)
    # Only non-empty char cells from page 0 = 104 total but 4 empty at end? Let's check
    nonempty = [c for c in positions if c['char']]
    print(f"    Page 0 non-empty cells: {len(nonempty)} (expect 104)")
    # Page 0 has a-z each 4 times = 104 cells all non-empty
    assert len(nonempty) >= 100, f"Expected ~104, got {len(nonempty)}"

    # Check first cell position
    first = positions[0]
    print(f"    First cell: char={first['char']!r} x={first['x']} y={first['y']} w={first['w']} h={first['h']}")
    assert first['x'] == MARGIN_PX
    assert first['y'] == GRID_TOP_PX
    print("    PASS")

    # ── Test 3: Synthetic page + segment ───────────────────────────
    print("\n[3] Testing synthetic page segmentation (page 0)...")
    synth_page = _create_synthetic_page(0, draw_every_nth=3)
    synth_path = 'test_images/synthetic_page0.png'
    cv2.imwrite(synth_path, synth_page)
    print(f"    Saved synthetic page to {synth_path}")

    glyphs = segment_template_page(synth_page, 0)
    glyph_count = sum(len(v) for v in glyphs.values())
    unique_chars = len(glyphs)
    print(f"    Extracted {glyph_count} glyphs for {unique_chars} unique chars")
    assert glyph_count > 0, "No glyphs extracted from synthetic page"

    # ── Test 4: extract_glyph_from_cell directly ───────────────────
    print("\n[4] Testing extract_glyph_from_cell() directly...")
    # Build a tiny binary image with a circle in one cell
    dummy_bin = np.zeros((CELL_H_PX, CELL_W_PX), dtype=np.uint8)
    cx, cy = CELL_W_PX // 2, CELL_H_PX // 2
    cv2.circle(dummy_bin, (cx, cy), min(cx, cy) // 2, 255, -1)

    # Create a full page-sized image and paste the cell
    dummy_page = np.zeros((3300, 2550), dtype=np.uint8)
    first_cell = compute_cell_positions(0)[0]
    x1 = first_cell['x']
    y1 = first_cell['y']
    x2 = x1 + CELL_W_PX
    y2 = y1 + CELL_H_PX
    dummy_page[y1:y2, x1:x2] = dummy_bin

    cell_info = {**first_cell, 'char': 'a', 'variant': 0}
    glyph_img, meta = extract_glyph_from_cell(dummy_page, cell_info)
    assert glyph_img is not None, "Failed to extract glyph from cell with ink"
    assert glyph_img.mode == 'RGBA', f"Expected RGBA, got {glyph_img.mode}"
    assert glyph_img.size[1] == TARGET_HEIGHT, f"Expected height {TARGET_HEIGHT}, got {glyph_img.size[1]}"
    print(f"    Glyph size: {glyph_img.size}  meta: {meta}")

    # Save sample glyphs
    glyph_img.save('output/sample_glyph.png')
    print("    Saved output/sample_glyph.png")
    print("    PASS")

    # ── Test 5: Empty cell returns None ────────────────────────────
    print("\n[5] Testing empty cell returns None...")
    blank_page = np.zeros((3300, 2550), dtype=np.uint8)  # all black = ink? No: ink=255
    # Actually a blank page = 0 everywhere = no ink
    blank_cell = {**first_cell, 'char': 'a', 'variant': 0}
    result_img, result_meta = extract_glyph_from_cell(blank_page, blank_cell)
    assert result_img is None, "Expected None for empty cell"
    print("    PASS")

    print("\n" + "=" * 60)
    print("ALL segment.py tests PASSED")
    print("=" * 60)
