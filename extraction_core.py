"""
extraction_core.py — Single shared extraction implementation for InkClone.

Used by both the web endpoint (web/app.py) and standalone test scripts.
All dimensions imported from template_config.py (single source of truth).

Pipeline:
1. Resize to 2550×3300 (INTER_CUBIC) — NO perspective warp, NO corner detection
2. Sharpen with fixed kernel
3. For each cell in the grid:
   a. Calculate cell boundaries from template_config margins + grid
   b. Inset by 8% to avoid cell border lines
   c. Skip top 15% label zone
   d. Color-aware ink detection (reject blue by B-R > 30)
   e. Morphological open 2×2 to remove noise
   f. Remove long horizontal/vertical lines (grid remnants)
   g. Remove tiny connected components (<12px area)
   h. Fallback with adaptive threshold on red channel if too few ink pixels
   i. Autocrop to ink bounding box with 4px padding
   j. Oversized glyph re-cleaning with 4×4 kernel
   k. Convert to RGBA PNG (black ink on transparent)
4. Save glyphs + profile.json
"""

import cv2
import json
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image

import template_config as tc


# ── Character → filename stem mapping ────────────────────────────────────────
# Must match glyph_loader._parse_glyph_stem() expectations
_CHAR_TO_STEM = {
    ".": "period", ",": "comma", "!": "exclaim", "?": "question",
    "'": "apostrophe", '"': "quote", "-": "hyphen", ":": "colon",
    ";": "semicolon", "(": "lparen", ")": "rparen", "/": "slash",
    "@": "atsign", "&": "ampersand", "#": "hash", "$": "dollar",
}


def safe_filename(label: str) -> str:
    """Convert a display character/label to a filesystem-safe stem name."""
    if label in _CHAR_TO_STEM:
        return _CHAR_TO_STEM[label]
    if len(label) == 1 and label.isupper():
        return f"upper_{label}"
    if len(label) == 1 and label.isdigit():
        return f"digit_{label}"
    # lowercase letters and bigrams pass through as-is
    return label


def resize_and_sharpen(image_bgr: np.ndarray) -> np.ndarray:
    """Resize to WARP_W×WARP_H and sharpen. No perspective warp."""
    warped = cv2.resize(image_bgr, (tc.WARP_W, tc.WARP_H),
                        interpolation=cv2.INTER_CUBIC)
    kernel = np.array([[-0.5, -1, -0.5],
                       [-1,    7, -1],
                       [-0.5, -1, -0.5]])
    warped = cv2.filter2D(warped, -1, kernel)
    return warped


def extract_ink_mask(cell_bgr: np.ndarray, dark_thresh: int = 180) -> np.ndarray:
    """
    Color-aware ink detection. Returns binary mask (255=ink, 0=background).
    Rejects blue guide lines by checking B-R > 30.
    """
    b, g, r = cv2.split(cell_bgr)
    gray = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY)

    # Dark pixels
    dark_mask = gray < dark_thresh

    # Blue rejection: blue lines have high B relative to R
    blue_excess = b.astype(np.int16) - r.astype(np.int16)
    is_blue = blue_excess > 30

    # Ink = dark AND not blue
    ink_mask = (dark_mask & ~is_blue).astype(np.uint8) * 255
    return ink_mask


def extract_cell_region(warped_bgr: np.ndarray, row: int, col: int,
                        page: int) -> np.ndarray | None:
    """Extract a single cell BGR region from the warped image.
    Returns the inset cell region (with label zone blanked), or None if invalid."""
    cell_w, cell_h = tc.cell_dims(page)
    ml, mt = tc.MARGIN_LEFT, tc.MARGIN_TOP
    inset = tc.CELL_INSET

    x0 = ml + col * cell_w
    y0 = mt + row * cell_h
    x1 = x0 + cell_w
    y1 = y0 + cell_h

    # Inset to avoid cell border lines
    ix0 = int(x0 + inset * cell_w)
    iy0 = int(y0 + inset * cell_h)
    ix1 = int(x1 - inset * cell_w)
    iy1 = int(y1 - inset * cell_h)

    # Skip top 15% label zone
    label_h = int((iy1 - iy0) * 0.15)
    iy0_ink = iy0 + label_h

    cell = warped_bgr[iy0_ink:iy1, ix0:ix1]
    if cell.size == 0:
        return None
    return cell.copy()


def process_cell(cell_bgr: np.ndarray) -> Image.Image | None:
    """
    Extract ink from a cell BGR region, clean, autocrop, return RGBA PIL Image.
    Returns None if no ink found.
    """
    h_cell, w_cell = cell_bgr.shape[:2]
    pad = tc.AUTOCROP_PADDING
    min_ink = tc.MIN_INK_PIXELS

    # ── Min-channel binarization (primary) ───────────────────────────────
    # Black ink: min(R,G,B) ≈ 0-80. Blue lines: min(R,G,B) ≈ 130+
    min_ch = np.min(cell_bgr, axis=2)
    _, binarized = cv2.threshold(min_ch, 100, 255, cv2.THRESH_BINARY_INV)

    # Morphological open 2×2 to remove isolated noise
    binarized = cv2.morphologyEx(binarized, cv2.MORPH_OPEN,
                                 np.ones((2, 2), np.uint8))

    # Remove horizontal/vertical lines spanning ≥60% of cell
    hk = cv2.getStructuringElement(cv2.MORPH_RECT,
                                   (max(1, int(w_cell * 0.60)), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT,
                                   (1, max(1, int(h_cell * 0.60))))
    h_lines = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, hk)
    v_lines = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, vk)
    binarized = cv2.subtract(binarized, cv2.add(h_lines, v_lines))

    # Remove tiny connected components (area < 12 px)
    n_cc, lbl, stats, _ = cv2.connectedComponentsWithStats(binarized, 8)
    for i in range(1, n_cc):
        if stats[i, cv2.CC_STAT_AREA] < 12:
            binarized[lbl == i] = 0

    ink_coords = np.argwhere(binarized > 0)

    # ── Fallback: adaptive threshold on red channel ──────────────────────
    if len(ink_coords) < min_ink:
        red = cell_bgr[:, :, 2]
        binarized_ad = cv2.adaptiveThreshold(
            red, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 15, 8)
        binarized_ad = cv2.morphologyEx(binarized_ad, cv2.MORPH_OPEN,
                                        np.ones((2, 2), np.uint8))
        n2, lbl2, st2, _ = cv2.connectedComponentsWithStats(binarized_ad, 8)
        for j in range(1, n2):
            if st2[j, cv2.CC_STAT_AREA] < 12:
                binarized_ad[lbl2 == j] = 0
        ink_coords2 = np.argwhere(binarized_ad > 0)
        if len(ink_coords2) > len(ink_coords):
            binarized = binarized_ad
            ink_coords = ink_coords2

    if len(ink_coords) < min_ink:
        return None

    # ── Autocrop to ink bounding box + padding ───────────────────────────
    y_min, x_min = ink_coords.min(axis=0)
    y_max, x_max = ink_coords.max(axis=0)
    y_min = max(0, y_min - pad)
    x_min = max(0, x_min - pad)
    y_max = min(binarized.shape[0] - 1, y_max + pad)
    x_max = min(binarized.shape[1] - 1, x_max + pad)
    crop = binarized[y_min:y_max + 1, x_min:x_max + 1]

    if crop.size == 0 or crop.shape[0] < 3 or crop.shape[1] < 3:
        return None

    # ── Oversized glyph re-cleaning ──────────────────────────────────────
    crop_h, crop_w = crop.shape
    if crop_w > w_cell * 0.85 or crop_h > h_cell * 0.85:
        # Too large — likely grid line contamination; try stronger cleaning
        crop = cv2.morphologyEx(crop, cv2.MORPH_OPEN,
                                np.ones((4, 4), np.uint8))
        ink_coords = np.argwhere(crop > 0)
        if len(ink_coords) < min_ink:
            return None
        y_min2, x_min2 = ink_coords.min(axis=0)
        y_max2, x_max2 = ink_coords.max(axis=0)
        y_min2 = max(0, y_min2 - pad)
        x_min2 = max(0, x_min2 - pad)
        y_max2 = min(crop.shape[0] - 1, y_max2 + pad)
        x_max2 = min(crop.shape[1] - 1, x_max2 + pad)
        crop = crop[y_min2:y_max2 + 1, x_min2:x_max2 + 1]

    if crop.size == 0 or crop.shape[0] < 3 or crop.shape[1] < 3:
        return None

    # ── Build RGBA PNG ───────────────────────────────────────────────────
    alpha = crop.copy()
    rgba = np.zeros((*crop.shape, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha   # black ink (R=G=B=0) on transparent
    return Image.fromarray(rgba, 'RGBA')


def extract_page(image_bgr: np.ndarray, page_num: int) -> list:
    """
    Extract all glyphs from one page image.
    Returns list of (display_char, variant_idx, PIL.Image_RGBA) tuples.
    """
    # Resize and sharpen
    warped = resize_and_sharpen(image_bgr)

    cols, rows = tc.PAGE_GRIDS[page_num]
    page_map = tc.PAGE_MAPS[page_num]()

    results = []
    for idx, cell_info in enumerate(page_map):
        col = idx % cols
        row = idx // cols
        if row >= rows:
            break

        label = cell_info['label']
        variant = cell_info['variant']
        if label is None:
            continue  # empty cell

        # Get display character from label
        display_char = tc.label_to_display(label)

        cell_bgr = extract_cell_region(warped, row, col, page_num)
        if cell_bgr is None:
            continue

        glyph = process_cell(cell_bgr)
        if glyph is not None:
            results.append((display_char, variant, glyph))

    return results


def extract_all_pages(page_images: dict, profile_name: str,
                      profiles_dir: str | Path) -> dict:
    """
    Extract glyphs from all pages, save profile.

    Args:
        page_images: {page_num: cv2_bgr_image} dict (pages 1-4)
        profile_name: name for the profile directory
        profiles_dir: parent directory for profiles

    Returns:
        dict with keys: profile, total_glyphs, unique_characters,
        per_character, style_metrics, etc.
    """
    profiles_dir = Path(profiles_dir)
    profile_dir = profiles_dir / profile_name
    glyphs_dir = profile_dir / 'glyphs'
    glyphs_dir.mkdir(parents=True, exist_ok=True)

    # ── Extract from all pages ───────────────────────────────────────────
    bank: dict[str, list] = {}  # {display_char: [PIL.Image, ...]}

    for pg_num in sorted(page_images.keys()):
        img = page_images[pg_num]
        if img is None:
            continue
        page_results = extract_page(img, pg_num)
        for display_char, variant, glyph_img in page_results:
            bank.setdefault(display_char, []).append(glyph_img)

    # ── Save glyphs and build profile.json ───────────────────────────────
    saved_chars: dict[str, list] = {}
    stats = {'good': 0, 'empty': 0, 'contaminated': 0, 'oversized': 0}
    all_widths, all_heights, all_densities = [], [], []

    for char, images in sorted(bank.items()):
        stem = safe_filename(char)
        variants_saved = []

        for i, img in enumerate(images):
            if img is None:
                stats['empty'] += 1
                continue
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            arr = np.array(img)
            alpha = arr[:, :, 3]
            h, w = arr.shape[:2]
            ink_px = int((alpha > 10).sum())
            ink_ratio = ink_px / max(1, h * w)

            # Quality gate
            if ink_px < tc.MIN_INK_PIXELS:
                stats['empty'] += 1
                continue
            if ink_ratio > 0.85:
                stats['contaminated'] += 1
                continue
            ar = w / max(1, h)
            if ar > 4.0 or ar < 0.08:
                stats['oversized'] += 1
                continue

            filename = f"{stem}_{i}.png"
            img.save(str(glyphs_dir / filename), 'PNG')

            conf = min(1.0, ink_px / max(1, h * w) * 10)
            variants_saved.append({
                'path': f'glyphs/{filename}',
                'confidence': round(conf, 3),
                'ink_px': ink_px,
            })
            stats['good'] += 1

            # Collect metrics
            all_widths.append(w)
            all_heights.append(h)
            dens = float(ink_px) / max(1, h * w)
            all_densities.append(dens)

        if variants_saved:
            saved_chars[char] = variants_saved

    # ── Build per_character dict ─────────────────────────────────────────
    per_character = {}
    for char, variants in saved_chars.items():
        widths, heights, confs = [], [], []
        rel_paths = [v['path'] for v in variants]
        for v in variants:
            confs.append(v['confidence'])
            try:
                img2 = Image.open(glyphs_dir / Path(v['path']).name).convert('RGBA')
                w2, h2 = img2.size
                widths.append(w2)
                heights.append(h2)
            except Exception:
                pass

        max_conf = max(confs) if confs else 0.2
        per_character[char] = {
            'variants': rel_paths,
            'avg_width': round(float(np.mean(widths)), 2) if widths else 0.0,
            'avg_height': round(float(np.mean(heights)), 2) if heights else 0.0,
            'confidence': round(max_conf, 3),
            'is_weak': max_conf < 0.5,
            'extraction_method': 'template_cell',
        }

    # ── Coverage stats ───────────────────────────────────────────────────
    LOWERCASE = set('abcdefghijklmnopqrstuvwxyz')
    UPPERCASE = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    DIGITS = set('0123456789')
    PUNCTUATION = set('.,!?\'"−-:;()/@&#$')

    chars = set(saved_chars.keys())
    lc = chars & LOWERCASE
    uc = chars & UPPERCASE
    dg = chars & DIGITS
    pu = chars & PUNCTUATION
    standard = LOWERCASE | UPPERCASE | DIGITS | PUNCTUATION
    missing = sorted(standard - chars)

    profile = {
        'profile_id': profile_name,
        'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source_method': 'template',
        'character_coverage': {
            'lowercase_pct': round(len(lc) / 26 * 100, 1),
            'uppercase_pct': round(len(uc) / 26 * 100, 1),
            'digits_pct': round(len(dg) / 10 * 100, 1),
            'punctuation_pct': round(len(pu) / max(1, len(PUNCTUATION)) * 100, 1),
            'total_characters': len(saved_chars),
            'total_variants': stats['good'],
        },
        'per_character': per_character,
        'style_metrics': {
            'avg_glyph_width': round(float(np.mean(all_widths)), 2) if all_widths else 0.0,
            'avg_glyph_height': round(float(np.mean(all_heights)), 2) if all_heights else 0.0,
            'ink_density': round(float(np.mean(all_densities)), 4) if all_densities else 0.0,
        },
        'missing_characters': missing,
        'usable': len(lc) >= 20,
    }

    (profile_dir / 'profile.json').write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding='utf-8')

    return {
        'success': True,
        'profile': profile_name,
        'total_glyphs': stats['good'],
        'unique_characters': len(saved_chars),
        'coverage': {
            'lowercase': f"{len(lc)}/26",
            'uppercase': f"{len(uc)}/26",
            'digits': f"{len(dg)}/10",
        },
        'stats': stats,
        'warnings': [],
    }
