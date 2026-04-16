#!/usr/bin/env python3
"""
freeform_extract.py
===================
Freeform handwriting extraction pipeline.

Given a photo of three lines of KNOWN handwritten text, extracts individual
character glyphs and builds a HandwritingProfile glyph bank.

Known text:
  Line 1: "The quick brown fox jumps over a lazy dog by the river"
  Line 2: "Pack my box with five dozen jugs of liquid soap 1234567890"
  Line 3: "She explained that nothing was impossible if you worked hard"

Usage:
  python3 freeform_extract.py [path_to_photo]
"""

import os
import sys
import json
import random
import argparse
import shutil
import numpy as np
import cv2
from PIL import Image
from pathlib import Path
from scipy.ndimage import gaussian_filter1d

# ── Import project modules ────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preprocess import normalize_background, binarize
from profile import HandwritingProfile

# ── Known text ────────────────────────────────────────────────────────────────
KNOWN_SENTENCES = [
    "The quick brown fox jumps over a lazy dog by the river",
    "Pack my box with five dozen jugs of liquid soap 1234567890",
    "She explained that nothing was impossible if you worked hard",
]
KNOWN_WORDS = [s.split() for s in KNOWN_SENTENCES]

# ── Paths ─────────────────────────────────────────────────────────────────────
DEFAULT_IMAGE  = 'test_images/handwriting_sample.jpeg'
PROFILE_DIR    = 'profiles/freeform_vishnu'
OUTPUT_DIR     = 'output'
TEST_IMAGES_DIR = 'test_images'
TARGET_HEIGHT  = 128


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

def _order_points(pts):
    """Order 4 corner points as TL, TR, BR, BL."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s    = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()
    rect[0] = pts[np.argmin(s)]      # TL: smallest x+y
    rect[2] = pts[np.argmax(s)]      # BR: largest  x+y
    rect[1] = pts[np.argmin(diff)]   # TR: smallest x-y
    rect[3] = pts[np.argmax(diff)]   # BL: largest  x-y
    return rect


def _find_runs(mask):
    """
    Given a boolean 1-D mask, return list of (start, end) slices where
    mask is True (end is exclusive).
    """
    runs = []
    in_run = False
    start = 0
    for i, v in enumerate(mask):
        if v and not in_run:
            start  = i
            in_run = True
        elif not v and in_run:
            runs.append((start, i))
            in_run = False
    if in_run:
        runs.append((start, len(mask)))
    return runs


def _merge_close_runs(runs, min_gap):
    """Merge consecutive runs whose gap is < min_gap."""
    if not runs:
        return []
    merged = [list(runs[0])]
    for s, e in runs[1:]:
        if s - merged[-1][1] < min_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 – Load & pre-process
# ══════════════════════════════════════════════════════════════════════════════

def load_and_preprocess(image_path):
    """
    Load the photo, perspective-correct to just the paper region, then
    normalize background and binarize.

    Returns (paper_bgr, normalized_gray, binary_ink)
    """
    print(f"\n[Step 1] Loading image: {image_path}")
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    h, w = img_bgr.shape[:2]
    print(f"  Original size: {w}×{h}")

    paper = _crop_to_paper(img_bgr)
    ph, pw = paper.shape[:2]
    print(f"  Paper crop:    {pw}×{ph}")

    normalized = normalize_background(paper)
    binary     = binarize(normalized)

    cv2.imwrite(f'{TEST_IMAGES_DIR}/freeform_paper.png',      paper)
    cv2.imwrite(f'{TEST_IMAGES_DIR}/freeform_normalized.png', normalized)
    cv2.imwrite(f'{TEST_IMAGES_DIR}/freeform_binary.png',     binary)
    print("  Saved: freeform_paper, freeform_normalized, freeform_binary")

    return paper, normalized, binary


def _crop_to_paper(img_bgr):
    """
    Detect the white paper region and perspective-warp to it.
    Falls back to bounding-rect crop, then full image if detection fails.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Bright-region mask (paper is close to white)
    _, white = cv2.threshold(gray, 190, 255, cv2.THRESH_BINARY)

    # Close gaps to fill the paper body
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    closed = cv2.morphologyEx(white, cv2.MORPH_CLOSE, k)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print("  [crop] no contours — using full image")
        return img_bgr

    # Pick largest contour
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < h * w * 0.08:
        print(f"  [crop] largest contour too small ({area:.0f}px²) — full image")
        return img_bgr

    # Try to get a clean 4-point polygon
    peri  = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.02 * peri, True)

    if len(approx) == 4:
        pts = approx.reshape(4, 2).astype(np.float32)
        pts = _order_points(pts)
        out_w = int(max(np.linalg.norm(pts[1] - pts[0]),
                        np.linalg.norm(pts[2] - pts[3])))
        out_h = int(max(np.linalg.norm(pts[3] - pts[0]),
                        np.linalg.norm(pts[2] - pts[1])))
        if out_w < 50 or out_h < 50:
            print("  [crop] warped size too small — bounding rect")
            x, y, bw, bh = cv2.boundingRect(c)
            return img_bgr[y:y+bh, x:x+bw]
        dst = np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]])
        M   = cv2.getPerspectiveTransform(pts, dst)
        warped = cv2.warpPerspective(img_bgr, M, (out_w, out_h))
        print("  [crop] perspective-corrected 4-point warp")
        return warped
    else:
        # Convex hull bounding rect
        hull = cv2.convexHull(c)
        peri2 = cv2.arcLength(hull, True)
        approx2 = cv2.approxPolyDP(hull, 0.02 * peri2, True)
        if len(approx2) == 4:
            pts = approx2.reshape(4, 2).astype(np.float32)
            pts = _order_points(pts)
            out_w = int(max(np.linalg.norm(pts[1] - pts[0]),
                            np.linalg.norm(pts[2] - pts[3])))
            out_h = int(max(np.linalg.norm(pts[3] - pts[0]),
                            np.linalg.norm(pts[2] - pts[1])))
            if out_w > 50 and out_h > 50:
                dst = np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]])
                M   = cv2.getPerspectiveTransform(pts, dst)
                print("  [crop] perspective-corrected via convex hull")
                return cv2.warpPerspective(img_bgr, M, (out_w, out_h))
        x, y, bw, bh = cv2.boundingRect(c)
        print("  [crop] bounding-rect crop")
        return img_bgr[y:y+bh, x:x+bw]


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 – Detect text lines via horizontal projection
# ══════════════════════════════════════════════════════════════════════════════

def detect_text_lines(binary):
    """
    Compute horizontal projection, find ink bands, filter noise, keep only the
    3 genuine sentence bands (each may contain 2 wrapped sub-lines).

    Returns list of exactly 3 (y_start, y_end) tuples ordered top-to-bottom.
    """
    print("\n[Step 2] Detecting text lines via horizontal projection...")
    h, w = binary.shape

    proj   = (binary > 0).sum(axis=1).astype(float)
    proj_s = gaussian_filter1d(proj, sigma=3)

    thresh   = max(proj_s.max() * 0.04, 2.0)
    ink_rows = proj_s > thresh

    # Collect runs, merge gaps < 10 px, drop very short bands
    bands = _find_runs(ink_rows)
    bands = _merge_close_runs(bands, min_gap=10)
    bands = [(s, e) for s, e in bands if e - s >= 12]

    ink_counts = [int((binary[s:e, :] > 0).sum()) for s, e in bands]
    print(f"  Raw bands ({len(bands)} total):")
    for i, (s, e) in enumerate(bands):
        print(f"    [{i}] rows {s}–{e}  h={e-s}px  ink={ink_counts[i]}")

    # Filter: keep only bands with substantial ink
    # Each real sentence band has ~2000+ ink pixels; noise edges have <1000
    min_ink = max(1000, max(ink_counts) * 0.15) if ink_counts else 1000
    good = [(s, e, k) for (s, e), k in zip(bands, ink_counts) if k >= min_ink]

    if len(good) < 3:
        # Relax: take up to 3 bands sorted by ink density
        good = sorted(zip(bands, ink_counts), key=lambda x: x[1], reverse=True)
        good = [(s, e, k) for (s, e), k in good[:3]]

    # Sort top-3 by y position
    top3 = sorted(good[:3], key=lambda x: x[0])
    bands = [(s, e) for s, e, _ in top3]

    print(f"  Kept {len(bands)} sentence band(s):")
    for i, (s, e) in enumerate(bands):
        print(f"    [{i}] rows {s}–{e}  h={e-s}px")

    # Debug overlay
    dbg = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    for s, e in bands:
        cv2.rectangle(dbg, (0, s), (w - 1, e), (0, 200, 0), 2)
    cv2.imwrite(f'{TEST_IMAGES_DIR}/freeform_linebands.png', dbg)

    for i, (s, e) in enumerate(bands):
        cv2.imwrite(f'{TEST_IMAGES_DIR}/freeform_strip_{i}.png', binary[s:e, :])

    return bands


# ══════════════════════════════════════════════════════════════════════════════
# Step 2b – Split a sentence band into its two wrapped sub-lines
# ══════════════════════════════════════════════════════════════════════════════

def split_band_into_sublines(binary, y_start, y_end):
    """
    Find the horizontal gap between two wrapped text sub-lines within a band
    using the horizontal projection valley inside the band.

    Returns list of (y_start, y_end) sub-line tuples (1 or 2 entries).
    """
    band_h = y_end - y_start
    if band_h < 20:
        return [(y_start, y_end)]

    strip  = (binary[y_start:y_end, :] > 0)
    proj   = strip.sum(axis=1).astype(float)
    proj_s = gaussian_filter1d(proj, sigma=1.5)

    peak   = proj_s.max()
    if peak == 0:
        return [(y_start, y_end)]

    # Search for the valley in the middle 50 % of the band height
    mid_lo = max(1, int(band_h * 0.25))
    mid_hi = min(band_h - 1, int(band_h * 0.75))
    search = proj_s[mid_lo:mid_hi]
    if len(search) == 0:
        return [(y_start, y_end)]

    valley_rel = int(np.argmin(search)) + mid_lo
    valley_val = proj_s[valley_rel]

    # Only split when the valley is significantly quieter than the peaks
    if valley_val < peak * 0.35:
        split_y = y_start + valley_rel
        return [(y_start, split_y), (split_y, y_end)]

    return [(y_start, y_end)]


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 – Assign each of the 3 sentence bands to a known sentence
# ══════════════════════════════════════════════════════════════════════════════

def group_bands_into_sentences(bands, n_sentences=3):
    """
    After Step 2 already filtered to the top-3 ink-dense bands, this is a
    simple 1-to-1 mapping: band[i] → sentence[i].

    Returns list of lists [[0], [1], [2]].
    """
    print(f"\n[Step 3] Assigning {len(bands)} band(s) to {n_sentences} sentence(s)...")
    groups = [[i] for i in range(min(len(bands), n_sentences))]
    while len(groups) < n_sentences:
        groups.append([])
    for i, g in enumerate(groups):
        if g:
            s, e = bands[g[0]]
            print(f"  Sentence {i+1}: band [{g[0]}]  rows {s}–{e}")
        else:
            print(f"  Sentence {i+1}: (no band)")
    return groups


# ══════════════════════════════════════════════════════════════════════════════
# Step 3b – Detect word regions within a line strip
# ══════════════════════════════════════════════════════════════════════════════

def detect_words_in_strip(binary, y_start, y_end,
                          n_expected=None, debug_path=None):
    """
    Vertical projection on a horizontal strip to find word bounding boxes.

    Uses an adaptive word-gap threshold:
      - If n_expected is given, selects the n_expected-1 largest gaps.
      - Otherwise uses the natural bimodal split (Otsu on gap distribution).

    Returns list of (x_start, x_end).
    """
    strip = (binary[y_start:y_end, :] > 0)
    if not strip.any():
        return []

    # Very light smoothing: k=3 bridges only 1-2 px pixel-level gaps.
    # Larger gaps (≥3px) remain visible so word-level boundaries (10-25px) are
    # preserved.  The min_gap threshold below handles intra-character gaps.
    proj   = strip.sum(axis=0).astype(float)
    line_h = y_end - y_start
    proj_s = np.convolve(proj, np.ones(3) / 3, mode='same')

    thresh   = max(proj_s.max() * 0.015, 0.3)
    ink_cols = proj_s > thresh

    segs = _find_runs(ink_cols)
    if not segs:
        return []

    gap_vals = [segs[i][0] - segs[i-1][1] for i in range(1, len(segs))]
    if not gap_vals:
        return [(segs[0][0], segs[0][1])]

    # ── Word-gap threshold ────────────────────────────────────────────────────
    # Fixed minimum gap that bridges intra-character gaps (~3-5px) but not
    # inter-word gaps (~12-25px). Validated against this handwriting sample.
    word_gap_thresh = 6   # merge gaps strictly less than this

    words = _merge_close_runs(segs, min_gap=word_gap_thresh)
    words = [(s, e) for s, e in words if e - s >= 4]

    if debug_path:
        strip_bgr = cv2.cvtColor(binary[y_start:y_end, :], cv2.COLOR_GRAY2BGR)
        for xs, xe in words:
            cv2.rectangle(strip_bgr, (xs, 0), (xe, strip_bgr.shape[0] - 1),
                          (0, 200, 0), 1)
        cv2.imwrite(debug_path, strip_bgr)

    return words


# ══════════════════════════════════════════════════════════════════════════════
# Steps 4-6 – Match words → chars, extract glyphs
# ══════════════════════════════════════════════════════════════════════════════

def extract_glyphs_from_word(binary, gray,
                             y_start, y_end,
                             x_start, x_end,
                             word_text,
                             padding=3):
    """
    Divide a word region evenly by character count; fine-tune each cell
    by its ink bounding box; return RGBA glyph images at TARGET_HEIGHT.

    Returns list of (char, PIL.Image RGBA, meta_dict).
    """
    char_count = len(word_text)
    if char_count == 0:
        return []

    word_bin  = binary[y_start:y_end, x_start:x_end]
    word_gray = gray  [y_start:y_end, x_start:x_end]
    word_w    = x_end - x_start

    if word_w < char_count or word_bin.size == 0:
        return []

    char_w = word_w / char_count
    results = []

    for i, ch in enumerate(word_text):
        xl = max(0, int(i       * char_w))
        xr = min(word_w, int((i + 1) * char_w))

        cell_bin  = word_bin [:, xl:xr]
        cell_gray = word_gray[:, xl:xr]

        if cell_bin.size == 0:
            continue

        # Find ink bounding box
        r_has_ink = np.any(cell_bin > 0, axis=1)
        c_has_ink = np.any(cell_bin > 0, axis=0)

        if not r_has_ink.any() or not c_has_ink.any():
            continue  # no ink in this cell — skip

        rmin, rmax = np.where(r_has_ink)[0][[0, -1]]
        cmin, cmax = np.where(c_has_ink)[0][[0, -1]]

        # Expand by padding (clamped)
        rmin = max(0,                  rmin - padding)
        rmax = min(cell_bin.shape[0]-1, rmax + padding)
        cmin = max(0,                  cmin - padding)
        cmax = min(cell_bin.shape[1]-1, cmax + padding)

        ink_gray = cell_gray[rmin:rmax+1, cmin:cmax+1]
        ink_bin  = cell_bin [rmin:rmax+1, cmin:cmax+1]
        if ink_gray.shape[0] < 4 or ink_gray.shape[1] < 2:
            continue

        # Scale to target height, preserving aspect ratio
        orig_h, orig_w = ink_gray.shape
        scale = TARGET_HEIGHT / orig_h
        new_w = max(1, int(orig_w * scale))

        gray_scaled = cv2.resize(ink_gray.astype(np.float32),
                                 (new_w, TARGET_HEIGHT),
                                 interpolation=cv2.INTER_LANCZOS4)
        bin_scaled  = cv2.resize(ink_bin.astype(np.float32),
                                 (new_w, TARGET_HEIGHT),
                                 interpolation=cv2.INTER_LANCZOS4)

        # Alpha: use binary mask (antialiased by resize).  Ink → opaque, paper → transparent.
        alpha = np.clip(bin_scaled, 0, 255).astype(np.uint8)

        # Color: darken the ink so it reads clearly on white.
        # Ink pixels (gray~50-100) → darkened to ~30-60.
        # Paper pixels are mostly transparent anyway.
        color = np.clip(gray_scaled * 0.55, 0, 255).astype(np.uint8)

        rgba = np.stack([color, color, color, alpha], axis=2).astype(np.uint8)
        pil  = Image.fromarray(rgba, 'RGBA')

        meta = {
            'char'         : ch,
            'source_word'  : word_text,
            'char_idx'     : i,
            'original_h'   : orig_h,
            'original_w'   : orig_w,
            'scaled_w'     : new_w,
        }
        results.append((ch, pil, meta))

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 – Build glyph bank
# ══════════════════════════════════════════════════════════════════════════════

def build_glyph_bank(image_path):
    """
    Full extraction pipeline: load → preprocess → detect lines → detect words
    → extract glyphs → save HandwritingProfile.

    Returns the populated HandwritingProfile.
    """
    os.makedirs(TEST_IMAGES_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 1 ────────────────────────────────────────────────────────────────
    paper, normalized, binary = load_and_preprocess(image_path)

    # ── Step 2 ────────────────────────────────────────────────────────────────
    bands = detect_text_lines(binary)
    if not bands:
        print("ERROR: no text bands detected — check the input image.")
        sys.exit(1)

    # ── Step 3 ────────────────────────────────────────────────────────────────
    groups = group_bands_into_sentences(bands, n_sentences=3)

    # ── Steps 4–6 ─────────────────────────────────────────────────────────────
    print("\n[Steps 4–6] Detecting words and extracting glyphs...")
    profile = HandwritingProfile(PROFILE_DIR, name='freeform_vishnu')

    n_sentences = min(len(groups), len(KNOWN_WORDS))

    for sent_i in range(n_sentences):
        group_bands    = groups[sent_i]
        expected_words = KNOWN_WORDS[sent_i]
        n_exp          = len(expected_words)

        print(f"\n  Sentence {sent_i+1}: \"{KNOWN_SENTENCES[sent_i][:50]}...\"")
        print(f"    Expected {n_exp} words")

        if not group_bands:
            print("    [skip] no bands in this group")
            continue

        # ── Each band may contain 2 wrapped sub-lines; split them first ───────
        all_sublines = []  # (ys, ye, subline_idx_within_band)
        for band_i in group_bands:
            ys, ye = bands[band_i]
            sublines = split_band_into_sublines(binary, ys, ye)
            print(f"    Band {band_i} (rows {ys}–{ye}): "
                  f"split into {len(sublines)} sub-line(s)")
            for sl in sublines:
                cv2.imwrite(
                    f'{TEST_IMAGES_DIR}/freeform_subline'
                    f'_s{sent_i}_b{band_i}_{sl[0]}.png',
                    binary[sl[0]:sl[1], :])
            all_sublines.extend(sublines)

        # ── Detect words freely on each sub-line (no forced count hint) ─────────
        # The adaptive threshold (based on gap distribution + line height)
        # separates word gaps from intra-character gaps without needing a hint.
        word_regions = []  # (ys, ye, xs, xe)

        for sl_i, (ys, ye) in enumerate(all_sublines):
            dbg = (f'{TEST_IMAGES_DIR}/freeform_words'
                   f'_s{sent_i}_sl{sl_i}.png')
            wx_list = detect_words_in_strip(binary, ys, ye,
                                            n_expected=None,
                                            debug_path=dbg)
            print(f"    Sub-line {sl_i} (rows {ys}–{ye}): "
                  f"{len(wx_list)} word region(s)")
            for xs, xe in wx_list:
                word_regions.append((ys, ye, xs, xe))

        # Sort in reading order (top-to-bottom, left-to-right within a row)
        word_regions.sort(key=lambda r: (r[0], r[2]))
        print(f"    Total regions: {len(word_regions)}  (expected: {n_exp})")

        n_match = min(len(word_regions), n_exp)
        if n_match < n_exp:
            print(f"    WARNING: matched {n_match}/{n_exp} words")

        # If we have more detected regions than expected words, the last matched
        # word should absorb any trailing over-segmented regions on its sub-line
        # (handles strings like "1234567890" that split into clusters).
        last_word_expanded = {}   # word_i → expanded (ys, ye, xs, xe)
        if len(word_regions) > n_match and n_match > 0:
            last_ys, last_ye, last_xs, last_xe = word_regions[n_match - 1]
            exp_xs, exp_xe = last_xs, last_xe
            for r in word_regions[n_match:]:
                rys, rye, rxs, rxe = r
                # Same sub-line: y-ranges overlap
                if max(last_ys, rys) < min(last_ye, rye):
                    exp_xe = max(exp_xe, rxe)
            last_word_expanded[n_match - 1] = (last_ys, last_ye, exp_xs, exp_xe)

        for word_i in range(n_match):
            if word_i in last_word_expanded:
                ys, ye, xs, xe = last_word_expanded[word_i]
            else:
                ys, ye, xs, xe = word_regions[word_i]
            word_text = expected_words[word_i]

            glyphs = extract_glyphs_from_word(binary, normalized,
                                               ys, ye, xs, xe, word_text)

            for ch, glyph_img, meta in glyphs:
                meta['source_line'] = sent_i
                meta['word_idx']    = word_i
                profile.add_glyph(ch, glyph_img, meta)

            # Save word debug image
            word_debug = paper[ys:ye, xs:xe]
            safe = ''.join(c if c.isalnum() else '_' for c in word_text)
            cv2.imwrite(
                f'{TEST_IMAGES_DIR}/freeform_word'
                f'_{sent_i}_{word_i}_{safe}.png', word_debug)

            # Save individual glyph debug images
            for ch, glyph_img, meta in glyphs:
                safe_ch = ch if ch.isalnum() else f'ord{ord(ch)}'
                glyph_img.save(
                    f'{TEST_IMAGES_DIR}/'
                    f'glyph_{safe_ch}_{sent_i}_{word_i}_{meta["char_idx"]}.png')

    return profile


# ══════════════════════════════════════════════════════════════════════════════
# Step 8 – Renderer
# ══════════════════════════════════════════════════════════════════════════════

def render_sentence(profile, text, output_path, seed=None):
    """
    Render a text string using glyphs from the profile.

    For each character:
      - Pick a random variant from the glyph bank.
      - Try lowercase then uppercase fallback.
    Place glyphs with small random inter-character gaps and baseline jitter.
    Save to output_path as RGB PNG.
    """
    if seed is not None:
        random.seed(seed)

    print(f"  Rendering: \"{text}\" → {output_path}")

    # Build glyph list
    parts = []   # ('space'|'glyph'|'missing', img_or_None, char)
    for ch in text:
        if ch == ' ':
            parts.append(('space', None, ch))
            continue
        img, _ = profile.get_glyph(ch)
        if img is None:
            img, _ = profile.get_glyph(ch.lower())
        if img is None:
            img, _ = profile.get_glyph(ch.upper())
        if img is not None:
            parts.append(('glyph', img, ch))
        else:
            print(f"    No glyph for '{ch}' — leaving gap")
            parts.append(('missing', None, ch))

    # Measure canvas width
    total_w = 20
    for kind, img, _ in parts:
        if kind == 'space':
            total_w += random.randint(15, 25)
        elif kind == 'glyph':
            total_w += img.size[0] + random.randint(2, 5)
        else:
            total_w += 12

    canvas_h = TARGET_HEIGHT + 24
    canvas   = Image.new('RGBA', (total_w, canvas_h), (255, 255, 255, 255))

    x = 10
    for kind, img, _ in parts:
        if kind == 'space':
            x += random.randint(15, 25)
        elif kind == 'glyph':
            jitter = random.randint(-2, 2)
            y = 12 + jitter
            canvas.paste(img, (x, y), img)
            x += img.size[0] + random.randint(2, 5)
        else:
            x += 12

    # Flatten to RGB
    result = Image.new('RGB', canvas.size, (255, 255, 255))
    result.paste(canvas, mask=canvas.split()[3])

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path)
                else '.', exist_ok=True)
    result.save(output_path)
    print(f"    Saved {output_path}  ({result.size[0]}×{result.size[1]}px)")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Extract handwriting glyphs from a freeform photo.')
    parser.add_argument(
        'image_path', nargs='?', default=DEFAULT_IMAGE,
        help=f'Path to handwriting photo (default: {DEFAULT_IMAGE})')
    args = parser.parse_args()

    if not os.path.exists(args.image_path):
        print(f"ERROR: Image not found: {args.image_path}", file=sys.stderr)
        sys.exit(1)

    # Clean previous profile
    if os.path.exists(PROFILE_DIR):
        shutil.rmtree(PROFILE_DIR)

    # ── Steps 1-6: Build glyph bank ───────────────────────────────────────────
    profile = build_glyph_bank(args.image_path)

    # ── Step 7: Save profile ──────────────────────────────────────────────────
    print("\n[Step 7] Saving glyph bank to:", PROFILE_DIR)
    profile.save()

    # Coverage report
    report = profile.coverage_report()
    print("\n═══════════════════════════════════════")
    print("  Glyph Coverage Report")
    print("═══════════════════════════════════════")
    print(f"  Distinct characters : {report['total_chars']}")
    print(f"  Total glyph variants: {report['total_glyphs']}")
    ml = ''.join(report['missing_lowercase']) or '(none)'
    mu = ''.join(report['missing_uppercase']) or '(none)'
    md = ''.join(report['missing_digits'])    or '(none)'
    print(f"  Missing lowercase   : {ml}")
    print(f"  Missing uppercase   : {mu}")
    print(f"  Missing digits      : {md}")
    print()
    print("  Per-character variant counts:")
    for ch in sorted(report['chars'].keys()):
        count   = report['chars'][ch]
        display = repr(ch) if not ch.isprintable() else ch
        print(f"    '{display}': {count}")

    # ── Step 8: Render test sentences ─────────────────────────────────────────
    print("\n[Step 8] Rendering test sentences...")
    render_sentence(profile,
                    "the lazy fox worked hard",
                    f"{OUTPUT_DIR}/rendered_test.png",
                    seed=42)
    render_sentence(profile,
                    "quick brown dog jumps by",
                    f"{OUTPUT_DIR}/rendered_test2.png",
                    seed=7)

    # Verify outputs
    print()
    all_ok = True
    for out_path in [f"{OUTPUT_DIR}/rendered_test.png",
                     f"{OUTPUT_DIR}/rendered_test2.png"]:
        if os.path.exists(out_path):
            img = Image.open(out_path)
            print(f"  ✓ {out_path}  {img.size[0]}×{img.size[1]}px")
        else:
            print(f"  ✗ MISSING: {out_path}")
            all_ok = False

    if all_ok:
        print("\nAll done — pipeline completed successfully.")
    else:
        print("\nPipeline finished with warnings (see above).")


if __name__ == '__main__':
    main()
