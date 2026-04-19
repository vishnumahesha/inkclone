#!/usr/bin/env python3
"""extract_v6.py — Extract V6 template glyphs from camera photos.

Resolution-independent: warps to SOURCE native resolution (never upscales).
All cell positions computed from template margin ratios, not hardcoded pixels.
"""
import json, argparse
from pathlib import Path
from datetime import datetime, timezone
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).parent

SCAN_MAP = [
    (ROOT / "profiles" / "IMG_3807.jpeg", 1),  # lowercase a-o
    (ROOT / "profiles" / "IMG_3806.jpeg", 2),  # lowercase p-z
    (ROOT / "profiles" / "IMG_3809.jpeg", 3),  # uppercase A-Z
    (ROOT / "profiles" / "IMG_3808.jpeg", 4),  # digits+punct+bigrams
]

# Template margin ratios (8.5"x11" letter paper layout)
MARGIN_LEFT_RATIO   = 0.5  / 8.5   # 0.0588
MARGIN_TOP_RATIO    = 0.95 / 11.0  # 0.0864
MARGIN_RIGHT_RATIO  = 0.5  / 8.5   # 0.0588
MARGIN_BOTTOM_RATIO = 0.45 / 11.0  # 0.0409

# Never upscale beyond this
MAX_W, MAX_H = 2550, 3300

SMALL_CHARS = {'.', ',', "'", '"', '-', ':', ';', '!', '`', '*'}

_PUNCT = {
    '.': 'period', ',': 'comma', '!': 'exclaim', '?': 'question',
    "'": 'apostrophe', '"': 'quote', '-': 'hyphen', ':': 'colon',
    ';': 'semicolon', '(': 'lparen', ')': 'rparen', '/': 'slash',
    '@': 'atsign', '&': 'ampersand', '#': 'hash', '$': 'dollar',
}


def char_stem(c):
    if c in _PUNCT:
        return _PUNCT[c]
    if len(c) > 1:
        return c
    if c.isupper():
        return 'upper_' + c
    if c.isdigit():
        return 'digit_' + c
    return c


def page_cells(pg):
    if pg == 1:
        return [c for c in 'abcdefghijklmno' for _ in range(4)]
    if pg == 2:
        return [c for c in 'pqrstuvwxyz' for _ in range(4)]
    if pg == 3:
        return [c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' for _ in range(2)]
    cells = [d for d in '0123456789' for _ in range(3)]
    punct_chars = ['.', ',', '!', '?', "'", '"', '-', ':', ';',
                   '(', ')', '/', '@', '&', '#', '$']
    cells += [p for p in punct_chars for _ in range(2)]
    cells += ['th', 'he', 'in', 'an', 'er', 'on', 'ed', 're', 'ou', 'es',
              'ti', 'at', 'st', 'en', 'or', 'ng', 'ing', 'the', 'and', 'tion']
    return cells


def page_grid(pg, target_w, target_h):
    """Return (cols, rows, margin_left, margin_top, cell_w, cell_h)."""
    ml = int(target_w * MARGIN_LEFT_RATIO)
    mt = int(target_h * MARGIN_TOP_RATIO)
    gw = target_w - ml - int(target_w * MARGIN_RIGHT_RATIO)
    gh = target_h - mt - int(target_h * MARGIN_BOTTOM_RATIO)
    cols, rows = (6, 10) if pg <= 3 else (8, 11)
    return cols, rows, ml, mt, gw / cols, gh / rows


def find_corners(gray):
    """Find 4 corner markers as largest dark blob per quadrant."""
    _, binarized = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
    n_comp, _, stats, centroids = cv2.connectedComponentsWithStats(binarized, 8)
    h, w = gray.shape
    blobs = []
    for i in range(1, n_comp):
        area = stats[i, cv2.CC_STAT_AREA]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        if area > 50 and bh > 0 and 0.3 < bw / bh < 3.0:
            blobs.append((area, float(centroids[i, 0]), float(centroids[i, 1])))
    mid_x, mid_y = w / 2, h / 2
    quadrants = {
        'TL': [b for b in blobs if b[1] < mid_x and b[2] < mid_y],
        'TR': [b for b in blobs if b[1] >= mid_x and b[2] < mid_y],
        'BL': [b for b in blobs if b[1] < mid_x and b[2] >= mid_y],
        'BR': [b for b in blobs if b[1] >= mid_x and b[2] >= mid_y],
    }
    fallback = {
        'TL': (w * .02, h * .02), 'TR': (w * .98, h * .02),
        'BL': (w * .02, h * .98), 'BR': (w * .98, h * .98),
    }
    corners = {}
    for q, qblobs in quadrants.items():
        if qblobs:
            best = max(qblobs, key=lambda x: x[0])
            corners[q] = (best[1], best[2])
        else:
            corners[q] = fallback[q]
    return corners


def perspective_warp(img, corners, target_w, target_h):
    """Warp image to target dimensions using detected corners."""
    src = np.array([corners['TL'], corners['TR'],
                    corners['BR'], corners['BL']], np.float32)
    dst = np.array([[0, 0], [target_w, 0],
                    [target_w, target_h], [0, target_h]], np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    # Downscale: use area interpolation. Same size: use linear.
    interp = cv2.INTER_AREA if (target_w < img.shape[1]) else cv2.INTER_LINEAR
    return cv2.warpPerspective(img, matrix, (target_w, target_h), flags=interp)


def extract_glyph(warped_gray, col, row, ml, mt, cw, ch,
                  target_w, target_h, char_name=''):
    """Extract one cell at native resolution, threshold, autocrop, return RGBA."""
    scale = target_w / 2550.0
    inward_x = max(3, int(cw * 0.03))
    inward_y = max(3, int(ch * 0.03))
    pad = max(2, int(4 * scale))

    x0 = int(round(ml + col * cw)) + inward_x
    y0 = int(round(mt + row * ch)) + inward_y
    x1 = min(target_w, int(round(ml + (col + 1) * cw)) - inward_x)
    y1 = min(target_h, int(round(mt + (row + 1) * ch)) - inward_y)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None

    cell = warped_gray[y0:y1, x0:x1].copy()
    cell_h = cell.shape[0]

    # Mask label zone (top 12% of cell)
    label_mask_h = int(cell_h * 0.12)
    cell[:label_mask_h, :] = 255

    # Otsu threshold per-cell
    _, binarized = cv2.threshold(cell, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Dilate to recover stroke edges at lower resolutions (<2040px wide)
    if scale < 0.8:
        binarized = cv2.dilate(binarized, np.ones((2, 2), np.uint8), iterations=1)

    # Remove noise — cc_min scales with resolution
    cc_min = max(5, int(12 * scale))
    n_cc, labels, cc_stats, _ = cv2.connectedComponentsWithStats(binarized, 8)
    for i in range(1, n_cc):
        if cc_stats[i, cv2.CC_STAT_AREA] < cc_min:
            binarized[labels == i] = 0

    # Autocrop to ink bounding box
    ink_coords = np.argwhere(binarized > 0)
    min_ink_small = max(5, int(15 * scale))
    min_ink = min_ink_small if char_name in SMALL_CHARS else max(10, int(35 * scale))
    if len(ink_coords) < min_ink:
        return None

    y_min, x_min = ink_coords.min(axis=0)
    y_max, x_max = ink_coords.max(axis=0)
    y_min = max(0, y_min - pad)
    x_min = max(0, x_min - pad)
    y_max = min(binarized.shape[0] - 1, y_max + pad)
    x_max = min(binarized.shape[1] - 1, x_max + pad)
    crop = binarized[y_min:y_max + 1, x_min:x_max + 1]

    min_crop = max(4, int(8 * scale))
    if crop.shape[0] < min_crop or crop.shape[1] < min_crop:
        return None

    rgba = np.zeros((*crop.shape, 4), np.uint8)
    rgba[crop > 128] = [0, 0, 0, 240]
    return Image.fromarray(rgba, 'RGBA')


def run(profile='vishnu_v6'):
    """Main extraction pipeline."""
    profile_dir = ROOT / 'profiles' / profile
    glyphs_dir = profile_dir / 'glyphs'
    glyphs_dir.mkdir(parents=True, exist_ok=True)
    for old_file in glyphs_dir.glob('*.png'):
        if '_fallback' not in old_file.name:
            try:
                old_file.unlink()
            except OSError:
                pass

    bank = {}
    all_heights = []

    for scan_path, pg in SCAN_MAP:
        if not scan_path.exists():
            print(f"MISSING: {scan_path.name}")
            continue
        img = cv2.imread(str(scan_path))
        src_h, src_w = img.shape[:2]
        # Never upscale — cap at MAX_W x MAX_H
        target_w = min(src_w, MAX_W)
        target_h = min(src_h, MAX_H)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = find_corners(gray)
        print(f"Page {pg}: {scan_path.name}  {src_w}x{src_h} -> warp {target_w}x{target_h}")
        warped = cv2.cvtColor(
            perspective_warp(img, corners, target_w, target_h),
            cv2.COLOR_BGR2GRAY
        )
        cols, rows, ml, mt, cw, ch = page_grid(pg, target_w, target_h)
        cells = page_cells(pg)
        good = empty = 0
        for idx, char in enumerate(cells):
            col = idx % cols
            row = idx // cols
            if row >= rows:
                break
            glyph = extract_glyph(warped, col, row, ml, mt, cw, ch,
                                   target_w, target_h, char_name=char)
            if glyph is None:
                empty += 1
                continue
            bank.setdefault(char, []).append(glyph)
            all_heights.append(glyph.size[1])
            good += 1
        print(f"  good={good}  empty={empty}  scale={target_w/2550:.2f}")

    saved = {}
    for char, imgs in bank.items():
        stem = char_stem(char)
        for vi, glyph_img in enumerate(imgs):
            fname = f"{stem}_{vi}.png"
            glyph_img.save(str(glyphs_dir / fname))
            saved.setdefault(char, []).append(f"glyphs/{fname}")

    total = sum(len(v) for v in saved.values())
    lc = sum(1 for c in saved if len(c) == 1 and c.islower())
    uc = sum(1 for c in saved if len(c) == 1 and c.isupper())
    dg = sum(1 for c in saved if len(c) == 1 and c.isdigit())
    bi = sum(1 for c in saved if len(c) > 1)
    print(f"\nSaved {total} glyphs / {len(saved)} chars  "
          f"lc={lc}/26 uc={uc}/26 dg={dg}/10 bi={bi}")
    if all_heights:
        print(f"Heights: min={min(all_heights)} max={max(all_heights)} "
              f"mean={sum(all_heights) // len(all_heights)}px")

    profile_meta = {
        'profile_id': profile,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_method': 'template_v6',
        'total_variants': total,
        'usable': total > 0,
    }
    (profile_dir / 'profile.json').write_text(json.dumps(profile_meta, indent=2))
    print(f"Profile: {profile_dir / 'profile.json'}")

    try:
        from glyph_loader import load_profile_glyphs
        from render_engine import HandwritingRenderer
        glyphs = load_profile_glyphs(str(profile_dir))
        renderer = HandwritingRenderer(glyphs)
        for text in ['hi my name is vishnu',
                     'The quick brown fox jumps over the lazy dog.']:
            result = renderer.render(text)
            out_path = ROOT / f"test_v6_{text[:12].replace(' ', '_')}.png"
            result.save(str(out_path))
            print(f"Render: {out_path.name}  {result.size}")
    except Exception as exc:
        import traceback
        print(f"Render error: {exc}")
        traceback.print_exc()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='vishnu_v6')
    run(parser.parse_args().profile)
