#!/usr/bin/env python3
"""extract_simple.py — Calligraphr-style V3 extraction: Otsu threshold + span-based guide removal.
Usage:  python extract_simple.py [--profile vishnu_v3_clean]
"""
import sys, json, shutil, argparse
from pathlib import Path
from datetime import datetime, timezone
import cv2, numpy as np
from PIL import Image

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from template_layout import PAGE_LAYOUTS, COLS, ROWS, char_to_stem

TGT_W, TGT_H, MARGIN_L, MARGIN_T = 2550, 3300, 135, 345
CELL_W = (TGT_W - MARGIN_L - 135) / COLS
CELL_H = (TGT_H - MARGIN_T - 165) / ROWS
LABEL_ZONE = 0.35
SCAN_FILES = [ROOT / f"template_scans_v3_page{i}.png" for i in range(1, 4)]
SCAN_TO_PAGE = {0: 3, 1: 1, 2: 2}  # page1=punct, page2=lowercase, page3=upper+digits


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
        for py, px in zip(*np.where(res >= 0.35)):
            best.append((px + sz // 2, py + sz // 2, float(res[py, px])))
    if not best:
        m = 0.02
        return {'TL': (w*m, h*m, 0), 'TR': (w*(1-m), h*m, 0),
                'BL': (w*m, h*(1-m), 0), 'BR': (w*(1-m), h*(1-m), 0)}
    best.sort(key=lambda m: -m[2])
    kept = []
    for cx, cy, s in best:
        if not any(abs(cx-kx) < 80 and abs(cy-ky) < 80 for kx, ky, _ in kept):
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
        miss = ({'TL', 'TR', 'BL', 'BR'} - set(corners)).pop()
        pts = {k: np.array([v[0], v[1]]) for k, v in corners.items()}
        opp = {'TL': ('TR', 'BL', 'BR'), 'TR': ('TL', 'BR', 'BL'),
               'BL': ('TL', 'BR', 'TR'), 'BR': ('TR', 'BL', 'TL')}
        a, b, c = opp[miss]
        corners[miss] = (float(pts[a][0]+pts[b][0]-pts[c][0]),
                         float(pts[a][1]+pts[b][1]-pts[c][1]), 0.0)
    if len(corners) < 4:
        m = 0.02
        return {'TL': (w*m, h*m, 0), 'TR': (w*(1-m), h*m, 0),
                'BL': (w*m, h*(1-m), 0), 'BR': (w*(1-m), h*(1-m), 0)}
    return corners


def warp(img, corners):
    src = np.array([[corners[k][0], corners[k][1]]
                    for k in ('TL', 'TR', 'BR', 'BL')], dtype=np.float32)
    dst = np.array([[0,0],[TGT_W,0],[TGT_W,TGT_H],[0,TGT_H]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (TGT_W, TGT_H),
                               flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)


def extract_cells(warped_gray, page_dots):
    layout = PAGE_LAYOUTS.get(page_dots, PAGE_LAYOUTS[1])
    results, inset = [], 8
    for idx, char in enumerate(layout):
        if char is None:
            continue
        col, row = idx % COLS, idx // COLS
        x0 = int(MARGIN_L + col * CELL_W) + inset
        y0 = int(MARGIN_T + row * CELL_H) + inset
        x1 = min(TGT_W, int(MARGIN_L + (col+1) * CELL_W) - inset)
        y1 = min(TGT_H, int(MARGIN_T + (row+1) * CELL_H) - inset)
        cell = warped_gray[y0:y1, x0:x1].copy()
        ch, cw = cell.shape
        if ch < 20 or cw < 20:
            continue

        label_h = int(ch * LABEL_ZONE)
        work = cell[label_h:, :].copy()
        if work.size < 400:
            continue

        work[-8:, :] = 255; work[:, :6] = 255; work[:, -6:] = 255  # mask cell borders

        # Otsu's threshold — let OpenCV pick the level automatically
        _, binary = cv2.threshold(work, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Remove noise: drop connected components smaller than 20px
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        clean = np.zeros_like(binary)
        for lbl in range(1, n):
            if stats[lbl, cv2.CC_STAT_AREA] >= 20:
                clean[labels == lbl] = 255

        # Drop guide-line rows: span > 40% of cell width = printed guide, not stroke
        for ry in range(clean.shape[0]):
            nzc = np.where(clean[ry] > 0)[0]
            if len(nzc) > 1 and nzc[-1] - nzc[0] > cw * 0.40:
                clean[ry] = 0

        coords = np.argwhere(clean > 0)
        if len(coords) < 10:
            continue
        ymin, xmin = coords.min(axis=0)
        ymax, xmax = coords.max(axis=0)
        if (ymax - ymin) < 8 or (xmax - xmin) < 8:
            continue
        pad = 4
        ymin, xmin = max(0, ymin-pad), max(0, xmin-pad)
        ymax, xmax = min(clean.shape[0]-1, ymax+pad), min(clean.shape[1]-1, xmax+pad)
        cropped = clean[ymin:ymax+1, xmin:xmax+1]

        rh, rw = cropped.shape
        nw = max(1, int(round(rw * 128.0 / max(rh, 1))))
        resized = cv2.resize(cropped, (nw, 128), interpolation=cv2.INTER_LANCZOS4)
        rgba = np.zeros((128, nw, 4), np.uint8)
        rgba[resized > 128] = [0, 0, 0, 240]

        ink_pct = float(np.count_nonzero(resized > 128)) / max(1, 128 * nw)
        results.append((char, Image.fromarray(rgba, 'RGBA'), ink_pct))
    return results


def run(profile='vishnu_v3_clean'):
    profile_dir = ROOT / 'profiles' / profile
    glyphs_dir = profile_dir / 'glyphs'
    if profile_dir.exists(): shutil.rmtree(profile_dir)
    glyphs_dir.mkdir(parents=True)

    bank = {}
    for file_idx, scan_path in enumerate(SCAN_FILES):
        if not scan_path.exists(): print(f"SKIP {scan_path.name}"); continue
        page_dots = SCAN_TO_PAGE[file_idx]
        img = cv2.imread(str(scan_path))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        print(f"[{scan_path.name}] {img.shape[1]}×{img.shape[0]} → page_dots={page_dots}")
        corners = find_corners(gray)
        print(f"  corners: { {k: f'({int(v[0])},{int(v[1])})' for k,v in corners.items()} }")
        warped = cv2.cvtColor(warp(img, corners), cv2.COLOR_BGR2GRAY)
        for char, glyph, ink_pct in extract_cells(warped, page_dots):
            bank.setdefault(char, []).append(glyph)

    saved = {}
    for char, glyphs in bank.items():
        stem = char_to_stem(char)
        for v_idx, g in enumerate(glyphs):
            fname = f"{stem}_{v_idx}.png"
            g.save(str(glyphs_dir / fname))
            saved.setdefault(char, []).append(f"glyphs/{fname}")

    total = sum(len(v) for v in saved.values())
    lc = sum(1 for c in saved if len(c)==1 and c.islower())
    uc = sum(1 for c in saved if len(c)==1 and c.isupper())
    dg = sum(1 for c in saved if len(c)==1 and c.isdigit())
    bi = sum(1 for c in saved if len(c) > 1)
    print(f"\nSaved {total} glyphs — lc:{lc}/26  uc:{uc}/26  dig:{dg}/10  bigrams:{bi}")

    (profile_dir / 'profile.json').write_text(json.dumps({
        'profile_id': profile,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_method': 'simple_otsu_pipeline',
        'template_version': 'v3',
        'total_variants': total,
        'character_coverage': {
            'lowercase_pct': round(lc/26*100, 1),
            'uppercase_pct': round(uc/26*100, 1),
            'digits_pct':    round(dg/10*100, 1),
            'bigrams': bi, 'total_variants': total,
        },
        'per_character': {c: {'variants': len(p), 'files': p} for c, p in saved.items()},
        'usable': True,
    }, indent=2, ensure_ascii=False))
    print(f"Profile → {profile_dir/'profile.json'}")
    return profile_dir, saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='vishnu_v3_clean')
    args = parser.parse_args()
    run(args.profile)
