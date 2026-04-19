#!/usr/bin/env python3
"""extract_v6.py — Extract glyphs from InkClone template v6 native camera photos."""
import sys, json
from pathlib import Path
from datetime import datetime, timezone
import cv2
import numpy as np
from PIL import Image

ROOT     = Path(__file__).parent
PHOTO_DIR = Path("/Users/12-mac-alpha/Projects/inkclone/profiles")
PHOTOS   = {1: PHOTO_DIR/"IMG_3803.jpeg", 2: PHOTO_DIR/"IMG_3802.jpeg",
            3: PHOTO_DIR/"IMG_3805.jpeg", 4: PHOTO_DIR/"IMG_3804.jpeg"}
OUT_DIR  = ROOT / "profiles/vishnu_v6/glyphs"

PAGE_W, PAGE_H = 2550, 3300
GRID_X, GRID_Y = 150, 285
GRID_W, GRID_H = 2250, 2880
MARKER_INSET   = 84   # 0.28" * 300 DPI

PAGE_GRIDS = {1:(6,10), 2:(6,10), 3:(6,10), 4:(8,11)}

# Names must match what glyph_loader._parse_glyph_stem expects
PUNCT_NAMES = {".":"period",",":"comma","!":"exclaim","?":"question","'":"apostrophe",
               '"':"quote","-":"hyphen",":":"colon",";":"semicolon","(":"lparen",
               ")":"rparen","/":"slash","@":"atsign","&":"ampersand","#":"hash","$":"dollar"}


def get_page_cells(p):
    if p == 1:
        return [c for ch in "abcdefghijklmno" for c in [ch]*4]
    if p == 2:
        return [c for ch in "pqrstuvwxyz" for c in [ch]*4]
    if p == 3:
        return [c for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in [ch]*2]
    cells = [c for d in "0123456789" for c in [d]*3]
    for p_ in [".",",","!","?","'",'"',"-",":",";","(",")","/","@","&","#","$"]:
        cells += [p_]*2
    cells += ["th","he","in","an","er","on","ed","re","ou","es",
              "ti","at","st","en","or","ng","ing","the","and","tion"]
    return cells


def glyph_filename(ch, v):
    if ch in PUNCT_NAMES:
        stem = PUNCT_NAMES[ch]
    elif ch.isupper() and len(ch) == 1:
        stem = f"upper_{ch}"   # avoid case collision on macOS filesystem
    else:
        stem = ch
    return f"{stem}_{v}.png"


def find_markers(gray):
    """Locate 4 corner markers; return [(cx,cy)×4] order TL,TR,BL,BR or None."""
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, bw = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Expect marker area ~ (0.5-4% of page dim)^2
    lo, hi = (w * 0.004)**2, (w * 0.06)**2
    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if not lo < area < hi:
            continue
        x, y, cw, ch_ = cv2.boundingRect(cnt)
        if not 0.4 < cw/(ch_ or 1) < 2.5:
            continue
        candidates.append((x + cw//2, y + ch_//2))

    if len(candidates) < 4:
        return None

    # Assign best match to each corner quadrant
    expected = [(w*.15, h*.15), (w*.85, h*.15), (w*.15, h*.85), (w*.85, h*.85)]
    result, used = [], set()
    for ex, ey in expected:
        ranked = sorted([(i, c) for i, c in enumerate(candidates) if i not in used],
                        key=lambda ic: (ic[1][0]-ex)**2 + (ic[1][1]-ey)**2)
        if not ranked:
            return None
        i, pt = ranked[0]
        used.add(i)
        result.append(pt)
    return result   # TL, TR, BL, BR


def perspective_warp(img_bgr, markers):
    tl, tr, bl, br = markers
    src = np.float32([tl, tr, bl, br])
    dst = np.float32([[MARKER_INSET, MARKER_INSET],
                      [PAGE_W-MARKER_INSET, MARKER_INSET],
                      [MARKER_INSET, PAGE_H-MARKER_INSET],
                      [PAGE_W-MARKER_INSET, PAGE_H-MARKER_INSET]])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img_bgr, M, (PAGE_W, PAGE_H), flags=cv2.INTER_CUBIC)


def extract_cell(wgray, row, col, cw, ch_):
    x1 = int(GRID_X + col*cw) + 10
    y1 = int(GRID_Y + row*ch_) + 10
    x2 = int(GRID_X + (col+1)*cw) - 10
    y2 = int(GRID_Y + (row+1)*ch_) - 10
    if x2 <= x1 or y2 <= y1:
        return None
    cell = wgray[y1:y2, x1:x2]
    if cell.size == 0:
        return None
    # Mask top 12% (label)
    skip = int(cell.shape[0] * 0.12)
    cell = cell[skip:]
    if cell.size == 0:
        return None
    # Otsu threshold
    _, bw = cv2.threshold(cell, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Remove small components
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bw)
    clean = np.zeros_like(bw)
    for lbl in range(1, n):
        if stats[lbl, cv2.CC_STAT_AREA] >= 20:
            clean[labels == lbl] = 255
    if int(clean.sum()) // 255 < 25:
        return None
    # Autocrop
    ys, xs = np.where(clean > 0)
    pad = 4
    y0, y1_ = max(0, ys.min()-pad), min(clean.shape[0]-1, ys.max()+pad)
    x0, x1_ = max(0, xs.min()-pad), min(clean.shape[1]-1, xs.max()+pad)
    cropped = clean[y0:y1_+1, x0:x1_+1]
    if cropped.shape[0] < 5 or cropped.shape[1] < 5:
        return None
    h_, w_ = cropped.shape
    rgba = np.zeros((h_, w_, 4), dtype=np.uint8)
    rgba[cropped > 0] = [0, 0, 0, 240]
    return Image.fromarray(rgba, "RGBA")


def process_page(page_num, img_path):
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"  ERROR: cannot read {img_path}"); return 0, 0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    markers = find_markers(gray)
    if markers is None:
        print(f"  ERROR: markers not found in page {page_num}"); return 0, 0
    warped   = perspective_warp(img, markers)
    wgray    = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    cols, rows = PAGE_GRIDS[page_num]
    cw, ch_  = GRID_W/cols, GRID_H/rows
    cells    = get_page_cells(page_num)
    vcnt, saved, skipped = {}, 0, 0
    for idx, ch in enumerate(cells):
        col, row = idx % cols, idx // cols
        if row >= rows:
            break
        v = vcnt.get(ch, 0); vcnt[ch] = v+1
        glyph = extract_cell(wgray, row, col, cw, ch_)
        if glyph is None:
            skipped += 1; continue
        glyph.save(OUT_DIR / glyph_filename(ch, v))
        saved += 1
    return saved, skipped


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tot_saved = tot_skip = 0
    ws, hs = [], []
    for pg in [1, 2, 3, 4]:
        p = PHOTOS[pg]
        print(f"Page {pg}: {p.name} ...", end=" ", flush=True)
        s, sk = process_page(pg, p)
        tot_saved += s; tot_skip += sk
        print(f"saved={s} skipped={sk}")
    for png in OUT_DIR.glob("*.png"):
        try:
            im = Image.open(png); ws.append(im.width); hs.append(im.height)
        except: pass
    print(f"\nTotal: {tot_saved} saved, {tot_skip} skipped")
    if ws:
        print(f"Width: {min(ws)}-{max(ws)}px  Height: {min(hs)}-{max(hs)}px")
    prof = {"name":"vishnu_v6","display_name":"Vishnu v6 (Calligraphr template)",
            "created":datetime.now(timezone.utc).isoformat(),"source":"V6 native camera",
            "glyph_count":tot_saved}
    with open(OUT_DIR.parent/"profile.json","w") as f:
        json.dump(prof, f, indent=2)
    print(f"Profile: {OUT_DIR.parent/'profile.json'}")

if __name__ == "__main__":
    main()
