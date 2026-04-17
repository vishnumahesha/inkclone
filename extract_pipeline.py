#!/usr/bin/env python3
"""
Calligraphr-style extraction pipeline for InkClone v4 template scans.
Warp to known dimensions, cut at known positions, hysteresis threshold, done.
"""
import sys, json, argparse
from pathlib import Path
from datetime import datetime, timezone
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from template_layout import PAGE_LAYOUTS, COLS, ROWS, CELLS_PER_PAGE, char_to_stem

# Known dimensions (8.5"×11" at 300dpi)
TGT_W, TGT_H = 2550, 3300
MARGIN_L, MARGIN_T = 135, 345
CELL_W = (TGT_W - 135 - 135) / COLS   # 285.0
CELL_H = (TGT_H - 345 - 165) / ROWS   # 214.6
LABEL_ZONE = 0.35  # top 35% of cell is label

SCAN_FILES = [ROOT / f"template_v4_scan_page{i}.png" for i in range(1, 4)]
SCAN_TO_PAGE = {0: 3, 1: 2, 2: 1}

# ── Step 1: Find corners via bullseye template matching ──────────

def _synth_bullseye(sz=48):
    t = np.ones((sz, sz), np.uint8) * 255
    c = sz // 2
    cv2.circle(t, (c, c), sz // 2 - 1, 0, -1)
    cv2.circle(t, (c, c), int(sz * 0.32), 255, -1)
    cv2.circle(t, (c, c), int(sz * 0.15), 0, -1)
    return t

def find_corners(gray):
    h, w = gray.shape
    best = []
    for sz in [36, 48, 60, 72, 84]:
        tpl = _synth_bullseye(sz)
        res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        for py, px in zip(*np.where(res >= 0.40)):
            best.append((px + sz // 2, py + sz // 2, float(res[py, px])))
    if not best:
        return _edge_fallback(gray)
    best.sort(key=lambda m: -m[2])
    kept = []
    for cx, cy, s in best:
        if not any(abs(cx - kx) < 80 and abs(cy - ky) < 80 for kx, ky, _ in kept):
            kept.append((cx, cy, s))
    mid_x, mid_y = w / 2, h / 2
    corners = {}
    for cx, cy, s in kept:
        k = ('TL' if cx < mid_x and cy < mid_y else
             'TR' if cx >= mid_x and cy < mid_y else
             'BL' if cx < mid_x else 'BR')
        if k not in corners or s > corners[k][2]:
            corners[k] = (cx, cy, s)
    if len(corners) == 3:
        miss = ({'TL','TR','BL','BR'} - set(corners.keys())).pop()
        pts = {k: np.array([v[0], v[1]]) for k, v in corners.items()}
        opp = {'TL': ('TR','BL','BR'), 'TR': ('TL','BR','BL'),
               'BL': ('TL','BR','TR'), 'BR': ('TR','BL','TL')}
        a, b, c = opp[miss]
        corners[miss] = (float(pts[a][0]+pts[b][0]-pts[c][0]),
                         float(pts[a][1]+pts[b][1]-pts[c][1]), 0.0)
    return corners if len(corners) >= 4 else _edge_fallback(gray)

def _edge_fallback(gray):
    h, w = gray.shape
    m = 0.02
    return {'TL': (w*m, h*m, 0), 'TR': (w*(1-m), h*m, 0),
            'BL': (w*m, h*(1-m), 0), 'BR': (w*(1-m), h*(1-m), 0)}

# ── Step 2: Perspective warp ─────────────────────────────────────

def warp(img, corners):
    src = np.array([[corners[k][0], corners[k][1]]
                    for k in ('TL','TR','BR','BL')], dtype=np.float32)
    dst = np.array([[0,0],[TGT_W,0],[TGT_W,TGT_H],[0,TGT_H]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (TGT_W, TGT_H),
                               flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)

# ── Steps 3-9: Extract cells ────────────────────────────────────

def extract_cells(warped_gray, page_dots):
    layout = PAGE_LAYOUTS.get(page_dots, PAGE_LAYOUTS[1])
    inset, results = 8, []

    for idx, char in enumerate(layout):
        if char is None:
            continue
        col, row = idx % COLS, idx // COLS
        x0 = max(0, int(MARGIN_L + col * CELL_W) + inset)
        y0 = max(0, int(MARGIN_T + row * CELL_H) + inset)
        x1 = min(TGT_W, int(MARGIN_L + (col+1) * CELL_W) - inset)
        y1 = min(TGT_H, int(MARGIN_T + (row+1) * CELL_H) - inset)
        cell = warped_gray[y0:y1, x0:x1].copy()
        ch, cw = cell.shape
        if ch < 20 or cw < 20:
            continue

        # Mask label zone and cell borders
        label_h = int(ch * LABEL_ZONE)
        cell[:label_h, :] = 255
        cell[max(label_h, ch-8):, :] = 255
        cell[label_h:, :6] = 255
        cell[label_h:, -6:] = 255

        # Two-threshold hysteresis: tight captures definite ink,
        # loose captures ink + guide gray. Keep only loose CCs
        # that overlap with tight seeds.
        wz = cell[label_h:, 6:-6]
        light = wz[wz > 200]
        bg = float(np.median(light)) if len(light) > 100 else 240.0
        thresh_tight = min(bg - 100, 140)
        thresh_loose = bg - 55
        ink_tight = (cell < thresh_tight).astype(np.uint8) * 255
        ink_loose = (cell < thresh_loose).astype(np.uint8) * 255

        # Minimal morphology on loose mask
        k2 = np.ones((2, 2), np.uint8)
        ink_loose = cv2.morphologyEx(ink_loose, cv2.MORPH_OPEN, k2)
        ink_loose = cv2.morphologyEx(ink_loose, cv2.MORPH_CLOSE, k2)

        # Keep only CCs overlapping tight ink; drop isolated guide fragments
        n_lab, labels, st, _ = cv2.connectedComponentsWithStats(ink_loose, 8)
        ink = np.zeros_like(ink_loose)
        for lbl in range(1, n_lab):
            if np.any(ink_tight[labels == lbl] > 0):
                ink[labels == lbl] = 255

        # CC shape filter: remove wide+thin (guide) / tall+thin (border) / tiny
        n_lab, labels, st, _ = cv2.connectedComponentsWithStats(ink, 8)
        for lbl in range(1, n_lab):
            bw_c, bh_c = st[lbl, cv2.CC_STAT_WIDTH], st[lbl, cv2.CC_STAT_HEIGHT]
            area = st[lbl, cv2.CC_STAT_AREA]
            if (bw_c > cw*0.40 and bh_c < 10) or (bh_c > ch*0.35 and bw_c < 8) or area < 6:
                ink[labels == lbl] = 0

        # Per-row guide line filter: wide span + many runs = guide line
        ink_wz = ink[label_h:, :]
        wz_h_px = ink_wz.shape[0]
        for ry in range(wz_h_px):
            nz = np.where(ink_wz[ry, :] > 0)[0]
            if len(nz) < 3:
                continue
            span = nz[-1] - nz[0] + 1
            runs = 1 + int(np.sum(np.diff(nz) > 3))
            if (span > cw*0.40 and runs >= 4) or span > cw*0.65:
                ink_wz[ry, :] = 0
        # Per-column cell border filter
        for rx in range(ink_wz.shape[1]):
            nz = np.where(ink_wz[:, rx] > 0)[0]
            if len(nz) < 3:
                continue
            span = nz[-1] - nz[0] + 1
            runs = 1 + int(np.sum(np.diff(nz) > 3))
            if (span > wz_h_px*0.40 and runs >= 4) or span > wz_h_px*0.65:
                ink_wz[:, rx] = 0

        # Autocrop
        coords = np.argwhere(ink > 0)
        if len(coords) < 10:
            results.append((char, idx, None, 'empty'))
            continue
        ymin, xmin = coords.min(axis=0)
        ymax, xmax = coords.max(axis=0)
        pad = 3
        ymin, xmin = max(0, ymin-pad), max(0, xmin-pad)
        ymax, xmax = min(ink.shape[0]-1, ymax+pad), min(ink.shape[1]-1, xmax+pad)
        cropped = ink[ymin:ymax+1, xmin:xmax+1]

        # Resize to 128px height → RGBA
        rh, rw = cropped.shape
        scale = 128.0 / max(rh, 1)
        nw = max(1, int(rw * scale))
        resized = cv2.resize(cropped, (nw, 128), interpolation=cv2.INTER_LANCZOS4)
        rgba = np.zeros((128, nw, 4), np.uint8)
        rgba[resized > 128] = [0, 0, 0, 240]

        # Quality flag
        ink_pct = float(np.count_nonzero(resized > 128)) / max(1, 128 * nw)
        dist = cv2.distanceTransform((resized > 128).astype(np.uint8), cv2.DIST_L2, 5)
        nz_d = dist[dist > 0]
        avg_sw = float(np.median(nz_d) * 2) if len(nz_d) > 0 else 0
        flag = 'thin' if avg_sw < 2.0 else 'good'

        results.append((char, idx, Image.fromarray(rgba, 'RGBA'),
                         flag, ink_pct, avg_sw, rh, rw))
    return results

# ── Main pipeline ────────────────────────────────────────────────

def run(profile='vishnu_v4'):
    profile_dir = ROOT / 'profiles' / profile
    glyphs_dir = profile_dir / 'glyphs'
    glyphs_dir.mkdir(parents=True, exist_ok=True)

    bank, report = {}, {}
    stats = {'good': 0, 'thin': 0, 'empty': 0, 'total': 0}

    for file_idx, scan_path in enumerate(SCAN_FILES):
        if not scan_path.exists():
            print(f"SKIP {scan_path.name}")
            continue
        page_dots = SCAN_TO_PAGE[file_idx]
        img = cv2.imread(str(scan_path))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        print(f"[{scan_path.name}] {img.shape[1]}×{img.shape[0]} → page {page_dots}")
        corners = find_corners(gray)
        print(f"  corners: {({k: f'({int(v[0])},{int(v[1])})' for k,v in corners.items()})}")
        warped_gray = cv2.cvtColor(warp(img, corners), cv2.COLOR_BGR2GRAY)

        for r in extract_cells(warped_gray, page_dots):
            char, cell_idx = r[0], r[1]
            stats['total'] += 1
            if r[2] is None:
                stats['empty'] += 1
                continue
            glyph, flag, ink_pct, avg_sw, bh, bw = r[2], r[3], r[4], r[5], r[6], r[7]
            stats[flag] += 1
            bank.setdefault(char, []).append(glyph)
            stem = char_to_stem(char)
            key = f"{stem}_{len(bank[char])-1}"
            report[key] = {'char': char, 'flag': flag, 'ink_pct': round(ink_pct, 4),
                           'stroke_width': round(avg_sw, 1), 'bbox': [bh, bw]}

    # Save glyphs
    saved = {}
    for char, glyphs in bank.items():
        stem = char_to_stem(char)
        for v_idx, g in enumerate(glyphs):
            fname = f"{stem}_{v_idx}.png"
            g.save(str(glyphs_dir / fname))
            saved.setdefault(char, []).append(f"glyphs/{fname}")

    total = sum(len(v) for v in saved.values())
    print(f"\nSaved {total} glyphs ({stats['good']} good, {stats['thin']} thin, {stats['empty']} empty)")

    # Quality report + profile metadata
    (profile_dir / 'quality_report.json').write_text(
        json.dumps({'summary': stats, 'glyphs': report}, indent=2))
    lc = sum(1 for c in saved if len(c)==1 and c.islower())
    uc = sum(1 for c in saved if len(c)==1 and c.isupper())
    dg = sum(1 for c in saved if len(c)==1 and c.isdigit())
    (profile_dir / 'profile.json').write_text(json.dumps({
        'profile_id': profile, 'created_at': datetime.now(timezone.utc).isoformat(),
        'source_method': 'calligraphr_pipeline', 'template_version': 'v4',
        'total_variants': total,
        'character_coverage': {'lowercase_pct': round(lc/26*100,1),
            'uppercase_pct': round(uc/26*100,1), 'digits_pct': round(dg/10*100,1),
            'bigrams': sum(1 for c in saved if len(c)>1)},
        'per_character': {c: {'variants': len(p), 'files': p} for c,p in saved.items()},
        'usable': True,
    }, indent=2, ensure_ascii=False))

    # Test render
    try:
        from glyph_loader import load_profile_glyphs
        from render_engine import HandwritingRenderer
        glyphs = load_profile_glyphs(str(profile_dir))
        renderer = HandwritingRenderer(glyphs)
        result = renderer.render('hi my name is vishnu')
        out = ROOT / 'test_calligraphr.png'
        result.save(str(out))
        print(f"Test render: {out}")
    except Exception as e:
        print(f"Test render failed: {e}")
    return profile_dir

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='vishnu_v4')
    args = parser.parse_args()
    run(args.profile)
