#!/usr/bin/env python3
"""extract_v6.py — Extract V6 template glyphs from camera photos.

Finds 4 square corner markers, perspective warps, extracts cells as RGBA glyphs.
Uses fixed threshold 130 (ink<=30, paper>=230, labels>=140).
"""
import json, shutil, argparse
from pathlib import Path
from datetime import datetime, timezone
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).parent

SCAN_MAP = [
    (ROOT / "profiles" / "IMG_3803.jpeg", 1),
    (ROOT / "profiles" / "IMG_3802.jpeg", 2),
    (ROOT / "profiles" / "IMG_3805.jpeg", 3),
    (ROOT / "profiles" / "IMG_3804.jpeg", 4),
]

TGT_W, TGT_H = 2550, 3300
ML, MT, GW, GH = 150, 285, 2250, 2880
INK_THRESHOLD = 130

_PUNCT = {
    '.': 'period', ',': 'comma', '!': 'exclaim', '?': 'question',
    "'": 'apostrophe', '"': 'quote', '-': 'hyphen', ':': 'colon',
    ';': 'semicolon', '(': 'lparen', ')': 'rparen', '/': 'slash',
    '@': 'atsign', '&': 'ampersand', '#': 'hash', '$': 'dollar',
}


def char_stem(c):
    """Convert character to filesystem-safe stem."""
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
    """Return ordered list of characters for each cell on the page."""
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


def page_grid(pg):
    """Return (cols, rows, cell_w, cell_h) for the page."""
    if pg <= 3:
        return 6, 10, GW / 6, GH / 10
    return 8, 11, GW / 8, GH / 11


def find_corners(gray):
    """Find 4 corner markers as largest dark blob per quadrant."""
    _, binarized = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
    n_components, _, stats, centroids = cv2.connectedComponentsWithStats(binarized, 8)
    h, w = gray.shape
    blobs = []
    for i in range(1, n_components):
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


def perspective_warp(img, corners):
    """Warp image to standard 2550x3300 using detected corners."""
    src = np.array([corners['TL'], corners['TR'], corners['BR'], corners['BL']], np.float32)
    dst = np.array([[0, 0], [TGT_W, 0], [TGT_W, TGT_H], [0, TGT_H]], np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, matrix, (TGT_W, TGT_H), flags=cv2.INTER_LANCZOS4)


def extract_glyph(warped_gray, col, row, cw, ch):
    """Extract one cell, threshold, autocrop, return RGBA or None."""
    x0 = int(round(ML + col * cw)) + 10
    y0 = int(round(MT + row * ch)) + 10
    x1 = min(TGT_W, int(round(ML + (col + 1) * cw)) - 10)
    y1 = min(TGT_H, int(round(MT + (row + 1) * ch)) - 10)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None
    cell = warped_gray[y0:y1, x0:x1].copy()
    cell_h = cell.shape[0]
    # Mask label zone — top 12% contains the 7pt character label
    cell[:int(cell_h * 0.12), :] = 255
    # Otsu threshold: ink is dark (~0-30), paper is bright (~230-255)
    _, binarized = cv2.threshold(cell, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    # Remove small noise components (< 20 pixels)
    n_cc, labels, cc_stats, _ = cv2.connectedComponentsWithStats(binarized, 8)
    for i in range(1, n_cc):
        if cc_stats[i, cv2.CC_STAT_AREA] < 20:
            binarized[labels == i] = 0
    # Autocrop to ink bounding box with 4px padding
    ink_coords = np.argwhere(binarized > 0)
    if len(ink_coords) < 25:
        return None
    y_min, x_min = ink_coords.min(axis=0)
    y_max, x_max = ink_coords.max(axis=0)
    y_min = max(0, y_min - 4)
    x_min = max(0, x_min - 4)
    y_max = min(binarized.shape[0] - 1, y_max + 4)
    x_max = min(binarized.shape[1] - 1, x_max + 4)
    crop = binarized[y_min:y_max + 1, x_min:x_max + 1]
    if crop.shape[0] < 8 or crop.shape[1] < 8:
        return None
    rgba = np.zeros((*crop.shape, 4), np.uint8)
    rgba[crop > 128] = [0, 0, 0, 240]
    return Image.fromarray(rgba, 'RGBA')


def run(profile='vishnu_v6'):
    """Main extraction pipeline."""
    profile_dir = ROOT / 'profiles' / profile
    glyphs_dir = profile_dir / 'glyphs'
    glyphs_dir.mkdir(parents=True, exist_ok=True)
    # Clear old glyphs
    for old_file in glyphs_dir.glob('*.png'):
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
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = find_corners(gray)
        print(f"Page {pg}: {scan_path.name}  {img.shape[1]}x{img.shape[0]}")
        warped = cv2.cvtColor(perspective_warp(img, corners), cv2.COLOR_BGR2GRAY)
        cols, rows, cw, ch = page_grid(pg)
        cells = page_cells(pg)
        good = empty = 0
        for idx, char in enumerate(cells):
            col = idx % cols
            row = idx // cols
            if row >= rows:
                break
            glyph = extract_glyph(warped, col, row, cw, ch)
            if glyph is None:
                empty += 1
                continue
            bank.setdefault(char, []).append(glyph)
            all_heights.append(glyph.size[1])
            good += 1
        print(f"  good={good}  empty={empty}")

    # Save glyphs
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

    # Write profile.json
    profile_meta = {
        'profile_id': profile,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_method': 'template_v6',
        'total_variants': total,
        'usable': total > 0,
    }
    (profile_dir / 'profile.json').write_text(json.dumps(profile_meta, indent=2))
    print(f"Profile: {profile_dir / 'profile.json'}")

    # Test render
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
