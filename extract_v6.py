#!/usr/bin/env python3
"""extract_v6.py — Extract glyphs from template photos using RED CHANNEL.

Blue guide lines (v7 template) have red channel ~166, same as paper (~240).
Black ink has red channel ~30. Threshold 160 cleanly separates ink from
both guide lines and paper — no guide line removal needed.

Also works on gray-template (v6) photos: gray guides have red=204, still
above threshold 160.

Always warps to 2550x3300 (letter @ 300 DPI) with sharpening after upscale.
All cell positions computed from template margin ratios.
"""
import json, argparse, glob
from pathlib import Path
from datetime import datetime, timezone
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).parent

SCAN_MAP = [
    (ROOT / "profiles" / "IMG_38072.png", 1),  # lowercase a-o (blue template)
    (ROOT / "profiles" / "IMG_38062.png", 2),  # lowercase p-z (blue template)
    (ROOT / "profiles" / "IMG_38092.png", 3),  # uppercase A-Z (blue template)
    (ROOT / "profiles" / "IMG_38082.png", 4),  # digits+punct+bigrams (blue template)
]

# Template margin ratios (8.5"x11" letter paper layout)
MARGIN_LEFT_RATIO   = 0.5  / 8.5   # 0.0588
MARGIN_TOP_RATIO    = 0.95 / 11.0  # 0.0864
MARGIN_RIGHT_RATIO  = 0.5  / 8.5   # 0.0588
MARGIN_BOTTOM_RATIO = 0.45 / 11.0  # 0.0409

# Never upscale beyond this
MAX_W, MAX_H = 2550, 3300

SMALL_CHARS = {'.', ',', "'", '"', '-', ':', ';', '!'}

_PUNCT = {
    '.': 'period', ',': 'comma', '!': 'exclaim', '?': 'question',
    "'": 'apostrophe', '"': 'quote', '-': 'hyphen', ':': 'colon',
    ';': 'semicolon', '(': 'lparen', ')': 'rparen', '/': 'slash',
    '@': 'atsign', '&': 'ampersand', '#': 'hash',
}

# Only characters present in the v6 template
VALID_V6_CHARS = (
    set('abcdefghijklmnopqrstuvwxyz') |
    set('ABCDEFGHIJKLMNOPQRSTUVWXYZ') |
    set('0123456789') |
    set('.,!?\'-:;()#@&/"') |
    {'th', 'he', 'in', 'an', 'er', 'on', 'ed', 're', 'ou', 'es',
     'ti', 'at', 'st', 'en', 'or', 'ng', 'ing', 'the', 'and', 'tion'}
)


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
    # Use cubic interpolation for upscaling (better than linear)
    is_upscale = target_w > img.shape[1]
    interp = cv2.INTER_CUBIC if is_upscale else cv2.INTER_AREA
    warped = cv2.warpPerspective(img, matrix, (target_w, target_h), flags=interp)
    # Sharpen after upscale to recover edges lost during interpolation
    if is_upscale:
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        warped = cv2.filter2D(warped, -1, kernel)
    return warped


def extract_glyph(warped_bgr, col, row, ml, mt, cw, ch,
                  target_w, target_h, char_name=''):
    """Extract one cell using RED CHANNEL — blue guide lines are invisible."""
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

    cell = warped_bgr[y0:y1, x0:x1].copy()
    cell_h = cell.shape[0]

    # Mask label zone (top 15% of cell) — white out in all channels
    label_mask_h = int(cell_h * 0.15)
    cell[:label_mask_h, :] = [255, 255, 255]

    # RED CHANNEL ONLY — blue guide lines have red~166 (invisible at threshold 160)
    # Black ink has red~30 (captured). Paper has red~240 (ignored).
    # Gap between ink and guides: 136px — impossible to miss.
    red_channel = cell[:, :, 2]  # OpenCV BGR order: index 2 = Red

    # Fixed threshold 160 — sits in the massive gap between ink (30) and guides (166)
    _, binarized = cv2.threshold(red_channel, 160, 255, cv2.THRESH_BINARY_INV)

    # No guide line removal needed — blue lines don't appear in red channel!

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


def normalize_glyph_heights(output_dir):
    """Scale all glyphs in each category to median height, preserving aspect ratio."""
    _PUNCT_NAMES = {"period", "comma", "exclaim", "question", "apostrophe",
                    "quote", "hyphen", "colon", "semicolon", "lparen",
                    "rparen", "slash", "atsign", "ampersand", "hash", "dollar"}
    categories = {
        'lowercase': [], 'uppercase': [], 'digits': [],
        'punctuation': [], 'bigrams': [],
    }
    for f in glob.glob(str(Path(output_dir) / '*.png')):
        if '.fuse_hidden' in f:
            continue
        char = Path(f).stem.rsplit('_', 1)[0]
        if char.startswith('upper_'):   categories['uppercase'].append(f)
        elif char.startswith('digit_'): categories['digits'].append(f)
        elif char in _PUNCT_NAMES:      categories['punctuation'].append(f)
        elif len(char) > 1:             categories['bigrams'].append(f)
        else:                           categories['lowercase'].append(f)

    for cat_name, files in categories.items():
        if not files:
            continue
        heights = [Image.open(f).size[1] for f in files]
        target_h = int(sorted(heights)[len(heights) // 2])
        height_range = max(heights) - min(heights)
        if height_range < target_h * 0.2:
            print(f"  {cat_name}: already consistent ({min(heights)}-{max(heights)}px), skip")
            continue
        print(f"  {cat_name}: normalizing {len(files)} glyphs to {target_h}px "
              f"(was {min(heights)}-{max(heights)}px)")
        for f in files:
            img = Image.open(f)
            w, h = img.size
            if h == target_h:
                continue
            scale = target_h / h
            new_w = max(1, int(w * scale))
            resized = img.resize((new_w, target_h), Image.LANCZOS)
            resized.save(f)
    print("  Normalization complete")


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
        # Always warp to 2550x3300 — native res cells are too small to extract from
        target_w, target_h = MAX_W, MAX_H
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = find_corners(gray)
        print(f"Page {pg}: {scan_path.name}  {src_w}x{src_h} -> warp {target_w}x{target_h}")
        # Keep color (BGR) — we need the red channel for extraction
        warped = perspective_warp(img, corners, target_w, target_h)
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
    skipped_invalid = 0
    skipped_fake = 0
    for char, imgs in bank.items():
        if char not in VALID_V6_CHARS:
            skipped_invalid += len(imgs)
            continue
        stem = char_stem(char)
        for vi, glyph_img in enumerate(imgs):
            w, h = glyph_img.size
            if w == 60 and h == 70:
                skipped_fake += 1
                continue
            fname = f"{stem}_{vi}.png"
            glyph_img.save(str(glyphs_dir / fname))
            saved.setdefault(char, []).append(f"glyphs/{fname}")

    if skipped_invalid:
        print(f"Skipped {skipped_invalid} glyphs for chars not in v6 template")
    if skipped_fake:
        print(f"Skipped {skipped_fake} fake 60×70px glyphs")

    # Post-filter: remove any glyph with extreme width:height ratio (>3:1)
    # These are residual guide line captures from gray-template photos.
    # Won't occur with blue-template photos.
    HLINE_EXEMPT = {'.', ',', '-', "'", '"', ':', ';', '!', '?'}
    deleted_hlines = 0
    for char, paths in list(saved.items()):
        if char in HLINE_EXEMPT:
            continue
        keep = []
        for rel_path in paths:
            png = profile_dir / rel_path
            if png.exists():
                img = Image.open(str(png))
                w, h = img.size
                if w > h * 3:
                    try:
                        png.unlink()
                    except OSError:
                        pass
                    deleted_hlines += 1
                else:
                    keep.append(rel_path)
            else:
                keep.append(rel_path)
        saved[char] = keep
    if deleted_hlines:
        print(f"Deleted {deleted_hlines} horizontal-line glyphs (residual from gray template)")
    saved = {c: v for c, v in saved.items() if v}

    # Verification pass
    problems = []
    for png in glyphs_dir.glob('*.png'):
        img = Image.open(str(png))
        w, h = img.size
        if w == 60 and h == 70:
            problems.append(f"FAKE 60x70: {png.name}")
        if w < 10 or h < 10:
            problems.append(f"TINY ({w}x{h}): {png.name}")
        if w > h * 3:
            problems.append(f"HLINE ({w}x{h}): {png.name}")
    if problems:
        print(f"\n=== {len(problems)} REMAINING PROBLEMS ===")
        for p in problems:
            print(f"  {p}")
    else:
        print("\nVerification: all checks passed (no lines, no fakes, no tiny glyphs)")

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

    # Normalize glyph heights per category
    print("\nNormalizing glyph heights...")
    normalize_glyph_heights(str(glyphs_dir))

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
