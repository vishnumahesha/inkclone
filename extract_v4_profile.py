#!/usr/bin/env python3
"""
extract_v4_profile.py  —  Extract glyphs from InkClone v4 template scans.

Usage:
    python extract_v4_profile.py [--profile vishnu_v4]

Reads the three v4 scan PNGs from the repo root, extracts every filled cell
using the v4 8-column × 13-row grid layout, and writes a profile to
profiles/<name>/.

V4 differences from v3:
  - Guide lines are light gray (≤30% opacity), not solid dark.
  - File → page mapping: page1.png=3/3, page2.png=2/3, page3.png=1/3.
  - Layout is identical to v3 (same chars per page).
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

SCAN_FILES = [
    ROOT / "template_v4_scan_page1.png",
    ROOT / "template_v4_scan_page2.png",
    ROOT / "template_v4_scan_page3.png",
]

# From visual inspection of page headers:
#   page1.png → "3/3" Punctuation + Letter Combos
#   page2.png → "2/3" Uppercase + Digits
#   page3.png → "1/3" Lowercase Letters
_KNOWN_ORDER = {0: 3, 1: 2, 2: 1}

Y_TOP_DEFAULT  = 347
CELL_H_DEFAULT = 205


def detect_grid_params(gray: np.ndarray):
    """Auto-detect x_left, cell_w, y_top, cell_h from printed grid lines.
    V4 guide lines are lighter (gray ~160-220), so widen the detection band.
    """
    h, w = gray.shape

    # V4 guide lines are light gray; widen band compared to v3 (was 100-215)
    line_mask = ((gray >= 80) & (gray <= 230)).astype(np.uint8) * 255

    # ── Vertical lines → x_left, cell_w ──────────────────────────────────────
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 80))
    v_spans = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, vk)
    vproj = v_spans.sum(axis=0) // 255

    vcols = np.where(vproj > 200)[0]

    bands = []
    if len(vcols):
        prev, bs = int(vcols[0]), int(vcols[0])
        for x in vcols[1:]:
            if x - prev > 5:
                bands.append((bs + prev) // 2)
                bs = int(x)
            prev = int(x)
        bands.append((bs + prev) // 2)

    spacings = [bands[i+1] - bands[i] for i in range(len(bands)-1)]
    cell_w = int(np.median(spacings)) if spacings else int(w * 0.106)

    if bands and cell_w > 0:
        margins = []
        ref = w * 0.09
        for b in bands:
            k = round((b - ref) / cell_w)
            margins.append(b - k * cell_w)
        x_left = int(np.median(margins))
    else:
        x_left = int(w * 0.09)

    # ── Horizontal lines → y_top, cell_h ─────────────────────────────────────
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (80, 1))
    h_spans = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, hk)
    hproj = h_spans.sum(axis=1) // 255

    hrows = np.where(hproj > 200)[0]

    hbands = []
    if len(hrows):
        prev, bs = int(hrows[0]), int(hrows[0])
        for y in hrows[1:]:
            if y - prev > 5:
                hbands.append((bs + prev) // 2)
                bs = int(y)
            prev = int(y)
        hbands.append((bs + prev) // 2)

    # Derive row geometry from image height to guarantee all 13 rows fit.
    # Y_TOP ≈ 14% of image height (header area), cell_h fills remaining space.
    y_top = int(h * 0.14)
    cell_h = int((h - y_top - int(h * 0.02)) / ROWS)

    return x_left, cell_w, y_top, cell_h


def cell_to_rgba(cell_bin: np.ndarray, cell_gray: np.ndarray):
    """Convert binary cell crop to clean RGBA glyph at 128px height."""
    rows = np.any(cell_bin > 0, axis=1)
    cols = np.any(cell_bin > 0, axis=0)

    if not rows.any() or not cols.any():
        return None

    rmin = int(np.where(rows)[0][0])
    rmax = int(np.where(rows)[0][-1])
    cmin = int(np.where(cols)[0][0])
    cmax = int(np.where(cols)[0][-1])

    if (rmax - rmin) < 10 or (cmax - cmin) < 10:
        return None

    bbox_h = rmax - rmin + 1
    bbox_w = cmax - cmin + 1
    ink_in_bbox = int(cell_bin[rmin:rmax+1, cmin:cmax+1].sum()) // 255
    if ink_in_bbox < bbox_h * bbox_w * 0.005:
        return None
    if ink_in_bbox < 20:
        return None

    pad = 4
    rmin = max(0, rmin - pad)
    rmax = min(cell_bin.shape[0] - 1, rmax + pad)
    cmin = max(0, cmin - pad)
    cmax = min(cell_bin.shape[1] - 1, cmax + pad)
    cropped = cell_bin[rmin:rmax+1, cmin:cmax+1]

    ch, cw = cropped.shape
    target_h = 128
    scale    = target_h / max(ch, 1)
    target_w = max(1, int(round(cw * scale)))
    resized  = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

    ink_mask = resized > 128
    arr = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    arr[ink_mask, 3] = 240
    return Image.fromarray(arr, "RGBA")


def extract_page(img_path: Path, page_dots: int):
    """Extract all glyphs from one template page scan."""
    img_cv = cv2.imread(str(img_path))
    if img_cv is None:
        raise FileNotFoundError(img_path)

    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    x_left, cell_w, y_top, cell_h = detect_grid_params(gray)

    print(f"  Grid: x_left={x_left} cell_w={cell_w} y_top={y_top} cell_h={cell_h}")

    # Use a fixed threshold of 140 for v4: ink is dark (<100), guide lines are
    # light gray (>150 after scanning). Otsu works too but fixed is more stable.
    _, binary = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    layout = PAGE_LAYOUTS.get(page_dots, PAGE_LAYOUTS[1])
    h_img, w_img = gray.shape

    extracted = []
    empty_cells = 0
    for cell_idx, char in enumerate(layout):
        if char is None:
            continue

        row = cell_idx // COLS
        col = cell_idx % COLS

        x0 = x_left + col * cell_w
        y0 = y_top  + row * cell_h
        x1 = min(w_img, x0 + cell_w)
        y1 = min(h_img, y0 + cell_h)

        if x0 >= w_img or y0 >= h_img:
            continue

        pad_x = max(1, int(cell_w * 0.08))
        pad_y = max(1, int(cell_h * 0.06))
        ix0, iy0 = x0 + pad_x, y0 + pad_y
        ix1, iy1 = x1 - pad_x, y1 - pad_y

        cell_bin  = binary[iy0:iy1, ix0:ix1]
        cell_gray = gray[iy0:iy1, ix0:ix1]

        glyph = cell_to_rgba(cell_bin, cell_gray)
        if glyph is not None:
            extracted.append((char, glyph))
        else:
            empty_cells += 1

    print(f"  Extracted {len(extracted)} glyphs, {empty_cells} empty/noise cells")
    return extracted


def build_profile(profile_name: str):
    """Process all 3 v4 scans and write the profile to profiles/<profile_name>/."""
    profile_dir = ROOT / "profiles" / profile_name
    glyphs_dir  = profile_dir / "glyphs"

    if profile_dir.exists():
        print(f"Removing existing profile at {profile_dir}")
        shutil.rmtree(profile_dir)
    glyphs_dir.mkdir(parents=True)

    bank: dict[str, list] = {}

    for file_idx, scan_path in enumerate(SCAN_FILES):
        if not scan_path.exists():
            print(f"  SKIP (not found): {scan_path}")
            continue

        page_dots = _KNOWN_ORDER[file_idx]
        print(f"[{scan_path.name}] page_dots={page_dots} (from known ordering)")
        print(f"[{scan_path.name}] Extracting layout page {page_dots} ...")
        pairs = extract_page(scan_path, page_dots)

        for char, glyph_img in pairs:
            bank.setdefault(char, []).append(glyph_img)

    saved_chars: dict[str, list] = {}
    for char, imgs in bank.items():
        stem = char_to_stem(char)
        for v_idx, img in enumerate(imgs):
            fname = f"{stem}_{v_idx}.png"
            img.save(str(glyphs_dir / fname))
            saved_chars.setdefault(char, []).append(f"glyphs/{fname}")

    total = sum(len(v) for v in saved_chars.values())
    print(f"\nSaved {len(saved_chars)} characters, {total} glyph variants")

    lc = sum(1 for c in saved_chars if len(c) == 1 and c.islower())
    uc = sum(1 for c in saved_chars if len(c) == 1 and c.isupper())
    dg = sum(1 for c in saved_chars if len(c) == 1 and c.isdigit())
    bi = sum(1 for c in saved_chars if len(c) > 1)

    profile = {
        "profile_id":   profile_name,
        "created_at":   datetime.now(timezone.utc).isoformat(),
        "source_method": "template_v4",
        "template_version": "v4",
        "total_variants": total,
        "character_coverage": {
            "lowercase_pct":  round(lc / 26 * 100, 1),
            "uppercase_pct":  round(uc / 26 * 100, 1),
            "digits_pct":     round(dg / 10 * 100, 1),
            "bigrams":        bi,
            "total_variants": total,
        },
        "per_character": {
            char: {"variants": len(paths), "files": paths}
            for char, paths in saved_chars.items()
        },
        "usable": True,
    }

    with open(profile_dir / "profile.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    print(f"Profile written to {profile_dir / 'profile.json'}")
    print(f"  lowercase: {lc}/26  uppercase: {uc}/26  digits: {dg}/10  bigrams: {bi}")
    return profile_dir, saved_chars


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="vishnu_v4")
    args = parser.parse_args()

    profile_dir, saved = build_profile(args.profile)
    print(f"\n✅  Profile '{args.profile}' ready at {profile_dir}")
