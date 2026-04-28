"""
run_synthetic_extraction.py — Extract synthetic_test profile from filled test pages.

Since the synthetic test pages are already at exact 2550×3300 with correct margins,
we skip corner detection / perspective warp and extract cells directly using
template_config geometry.

Usage:
    python3 tests/run_synthetic_extraction.py

Output:
    profiles/synthetic_test/glyphs/*.png
    profiles/synthetic_test/profile.json
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

import cv2, json, shutil
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image

import template_config as tc
import _extract_standalone as ex

# ── Config ────────────────────────────────────────────────────────────────────
SYNTHETIC_DIR = Path(__file__).parent / 'synthetic'
PROFILES_DIR  = Path(__file__).parent.parent / 'profiles'
PROFILE_ID    = 'synthetic_test_v2'
PROFILE_DIR   = PROFILES_DIR / PROFILE_ID
GLYPHS_DIR    = PROFILE_DIR / 'glyphs'

TEST_PAGES = [
    (SYNTHETIC_DIR / 'test_page1.png', 1),
    (SYNTHETIC_DIR / 'test_page2.png', 2),
    (SYNTHETIC_DIR / 'test_page3.png', 3),
    (SYNTHETIC_DIR / 'test_page4.png', 4),
]

def normalize_label(raw: str, page: int) -> str:
    """
    Profile keys are the literal display characters from _page_cells():
    lowercase letters ('a','b',...), uppercase ('A','B',...), digits ('0','1',...),
    punctuation ('.', ',', ...), bigrams ('th','he',...).
    No conversion needed — just pass through.
    """
    return raw


# ── Core cell extraction (no warp — image is already at 2550×3300) ────────────
def extract_cell_direct(img_bgr: np.ndarray, col: int, row: int, page: int):
    """
    Extract glyph from a cell in a 2550×3300 image that's already correctly
    laid out. Returns RGBA PIL.Image or None.
    """
    cell_w, cell_h = tc.cell_dims(page)
    ml, mt = tc.MARGIN_LEFT, tc.MARGIN_TOP
    inset   = tc.CELL_INSET
    pad     = tc.AUTOCROP_PADDING
    min_ink = tc.MIN_INK_PIXELS

    x0 = ml + col * cell_w
    y0 = mt + row * cell_h
    x1 = x0 + cell_w
    y1 = y0 + cell_h

    # Inner area (trim cell borders)
    ix0 = int(x0 + inset * cell_w)
    iy0 = int(y0 + inset * cell_h)
    ix1 = int(x1 - inset * cell_w)
    iy1 = int(y1 - inset * cell_h)

    # Trim label zone (top 15% — avoids printed cell label)
    label_h = int((iy1 - iy0) * 0.15)
    iy0_ink = iy0 + label_h

    cell = img_bgr[iy0_ink:iy1, ix0:ix1]
    if cell.size == 0:
        return None

    h_cell, w_cell = cell.shape[:2]

    # ── Min-channel binarization ─────────────────────────────────────────────
    # ink: min(R,G,B) < 100  (black ink ≈ 20; blue grid min ≈ 170)
    min_ch = np.min(cell, axis=2)
    _, binarized = cv2.threshold(min_ch, 100, 255, cv2.THRESH_BINARY_INV)

    # Morphological open 2×2 (removes isolated noise)
    binarized = cv2.morphologyEx(binarized, cv2.MORPH_OPEN,
                                  np.ones((2, 2), np.uint8))

    # Remove horizontal / vertical lines spanning ≥60% of cell
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, int(w_cell * 0.60)), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, int(h_cell * 0.60))))
    h_lines = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, hk)
    v_lines = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, vk)
    binarized = cv2.subtract(binarized, cv2.add(h_lines, v_lines))

    # Remove tiny connected components (area < 12 px)
    n_cc, lbl, stats, _ = cv2.connectedComponentsWithStats(binarized, 8)
    for i in range(1, n_cc):
        if stats[i, cv2.CC_STAT_AREA] < 12:
            binarized[lbl == i] = 0

    ink_coords = np.argwhere(binarized > 0)
    if len(ink_coords) < min_ink:
        # Adaptive fallback on red channel
        red = cell[:, :, 2]
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

    # Autocrop to ink bounding box + padding
    y_min, x_min = ink_coords.min(axis=0)
    y_max, x_max = ink_coords.max(axis=0)
    y_min = max(0, y_min - pad)
    x_min = max(0, x_min - pad)
    y_max = min(binarized.shape[0] - 1, y_max + pad)
    x_max = min(binarized.shape[1] - 1, x_max + pad)
    crop = binarized[y_min:y_max + 1, x_min:x_max + 1]

    if crop.size == 0 or crop.shape[0] < 3 or crop.shape[1] < 3:
        return None

    # Build RGBA PNG
    alpha = crop.copy()
    rgba  = np.zeros((*crop.shape, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, 'RGBA')


def extract_all_pages():
    """Run direct extraction on all 4 test pages. Returns {label: [PIL.Image,...]}."""
    bank: dict[str, list] = {}
    for img_path, pg in TEST_PAGES:
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            print(f'ERROR: could not read {img_path}')
            continue

        cols, rows = tc.PAGE_GRIDS[pg]
        cells = ex._page_cells(pg)   # raw char labels

        print(f'  Page {pg}: {cols}×{rows} grid, {len(cells)} cells', flush=True)

        for idx, raw_char in enumerate(cells):
            col = idx % cols
            row = idx // cols
            if row >= rows:
                break
            if raw_char is None:
                continue

            label = normalize_label(raw_char, pg)
            glyph = extract_cell_direct(img_bgr, col, row, pg)
            if glyph is not None:
                bank.setdefault(label, []).append(glyph)

    return bank


# ── Coverage sets (literal chars, matching render engine expectations) ─────────
LOWERCASE   = set('abcdefghijklmnopqrstuvwxyz')
UPPERCASE   = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
DIGITS      = set('0123456789')
PUNCTUATION = set('.  ,  !  ?  \'  "  -  :  ;  (  )  /  @  &  #  $'.split())


def save_profile(bank: dict):
    """Save glyph PNGs + profile.json. Returns stats dict."""
    GLYPHS_DIR.mkdir(parents=True, exist_ok=True)

    saved_chars = {}
    stats = {'good': 0, 'empty': 0, 'contaminated': 0, 'oversized': 0}

    for label, images in sorted(bank.items()):
        variants = []
        for i, img in enumerate(images):
            if img is None:
                stats['empty'] += 1
                continue
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            arr = np.array(img)
            alpha = arr[:, :, 3]
            ink_px = int((alpha > 10).sum())
            h, w = arr.shape[:2]
            ink_ratio = ink_px / max(1, h * w)

            if ink_px < tc.MIN_INK_PIXELS:
                stats['empty'] += 1;       continue
            if ink_ratio > 0.85:
                stats['contaminated'] += 1; continue
            ar = w / max(1, h)
            if ar > 4.0 or ar < 0.08:
                stats['oversized'] += 1;    continue

            safe = label.replace('/', 'slash')
            filename = f'{safe}_{i}.png'
            img.save(str(GLYPHS_DIR / filename), 'PNG')
            conf = min(1.0, ink_px / max(1, h * w) * 10)
            variants.append({'path': f'glyphs/{safe}_{i}.png',
                             'confidence': round(conf, 3), 'ink_px': ink_px})
            stats['good'] += 1

        if variants:
            saved_chars[label] = variants

    # Build profile.json
    per_character = {}
    all_widths, all_heights, all_densities = [], [], []

    for label, variants in saved_chars.items():
        widths, heights, densities, confs = [], [], [], []
        paths = [v['path'] for v in variants]
        for v in variants:
            confs.append(v['confidence'])
            try:
                img2 = Image.open(GLYPHS_DIR / Path(v['path']).name).convert('RGBA')
                w2, h2 = img2.size
                arr2 = np.array(img2)
                dens = float((arr2[:,:,3] > 10).sum()) / max(1, arr2[:,:,3].size)
                widths.append(w2); heights.append(h2); densities.append(dens)
            except Exception:
                pass

        max_conf = max(confs) if confs else 0.2
        per_character[label] = {
            'variants': paths,
            'avg_width':  round(float(np.mean(widths)),  2) if widths  else 0.0,
            'avg_height': round(float(np.mean(heights)), 2) if heights else 0.0,
            'confidence': round(max_conf, 3),
            'is_weak':    max_conf < 0.5,
            'extraction_method': 'template_cell',
        }
        all_widths.extend(widths); all_heights.extend(heights); all_densities.extend(densities)

    lc = LOWERCASE   & set(saved_chars)
    uc = UPPERCASE   & set(saved_chars)
    dg = DIGITS      & set(saved_chars)
    pu = PUNCTUATION & set(saved_chars)
    missing = sorted((LOWERCASE | UPPERCASE | DIGITS | PUNCTUATION) - set(saved_chars))

    profile = {
        'profile_id':    PROFILE_ID,
        'created_at':    datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source_method': 'synthetic_test',
        'character_coverage': {
            'lowercase_pct':     round(len(lc) / 26 * 100, 1),
            'uppercase_pct':     round(len(uc) / 26 * 100, 1),
            'digits_pct':        round(len(dg) / 10 * 100, 1),
            'punctuation_pct':   round(len(pu) / 16 * 100, 1),
            'total_characters':  len(saved_chars),
            'total_variants':    stats['good'],
        },
        'per_character': per_character,
        'style_metrics': {
            'avg_glyph_width':  round(float(np.mean(all_widths)),    2) if all_widths    else 0.0,
            'avg_glyph_height': round(float(np.mean(all_heights)),   2) if all_heights   else 0.0,
            'ink_density':      round(float(np.mean(all_densities)), 4) if all_densities else 0.0,
        },
        'missing_characters': missing,
        'usable': len(lc) >= 20,
    }
    (PROFILE_DIR / 'profile.json').write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding='utf-8')

    stats.update({'lc': len(lc), 'uc': len(uc), 'dg': len(dg), 'pu': len(pu),
                  'missing': missing, 'per_character': per_character})
    return stats


def main():
    for path, _ in TEST_PAGES:
        if not path.exists():
            print(f'ERROR: {path} not found. Run generate_filled_test_pages.py first.')
            sys.exit(1)

    print('Direct-extracting synthetic_test profile (no warp — already 2550×3300)...')
    bank = extract_all_pages()

    raw_total = sum(len(v) for v in bank.values())
    print(f'\nRaw bank: {raw_total} glyphs across {len(bank)} characters')

    print('\nInk pixel sample (first 5 chars):')
    for label in list(sorted(bank))[:5]:
        pxs = []
        for g in bank[label]:
            if g is None: continue
            arr = np.array(g.convert('RGBA'))
            pxs.append(int((arr[:,:,3] > 10).sum()))
        print(f'  {label:12s}: {pxs}')

    print('\nSaving profile...')
    stats = save_profile(bank)

    print('\n── Extraction Results ──────────────────────────────────────────')
    print(f'  Good glyphs saved  : {stats["good"]}')
    print(f'  Empty / no ink     : {stats["empty"]}')
    print(f'  Contaminated >85%  : {stats["contaminated"]}')
    print(f'  Oversized AR       : {stats["oversized"]}')
    print()
    print(f'  Lowercase  a–z     : {stats["lc"]}/26')
    print(f'  Uppercase  A–Z     : {stats["uc"]}/26')
    print(f'  Digits     0–9     : {stats["dg"]}/10')
    print(f'  Punctuation        : {stats["pu"]}/16')
    if stats['missing']:
        missing_str = ', '.join(stats['missing'][:15])
        if len(stats['missing']) > 15:
            missing_str += f' ... (+{len(stats["missing"])-15} more)'
        print(f'\n  Missing: {missing_str}')
    else:
        print('\n  ✓ No missing standard characters')

    lc_ok   = stats['lc'] == 26
    uc_ok   = stats['uc'] == 26
    dg_ok   = stats['dg'] == 10
    ok_cont = stats['contaminated'] == 0
    ok_over = stats['oversized'] == 0

    print('\n── Pass/Fail ────────────────────────────────────────────────────')
    print(f'  Lowercase complete : {"PASS ✓" if lc_ok   else "FAIL ✗"}')
    print(f'  Uppercase complete : {"PASS ✓" if uc_ok   else "FAIL ✗"}')
    print(f'  Digits complete    : {"PASS ✓" if dg_ok   else "FAIL ✗"}')
    print(f'  Zero contaminated  : {"PASS ✓" if ok_cont else "FAIL ✗ (" + str(stats["contaminated"]) + ")"}')
    print(f'  Zero oversized AR  : {"PASS ✓" if ok_over else "FAIL ✗ (" + str(stats["oversized"]) + ")"}')

    all_pass = lc_ok and uc_ok and dg_ok and ok_cont and ok_over
    print(f'\n  OVERALL: {"✓ PASS" if all_pass else "✗ FAIL"}')
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
