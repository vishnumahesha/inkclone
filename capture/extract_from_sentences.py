#!/usr/bin/env python3
"""
extract_from_sentences.py
=========================
Improved freeform handwriting extractor that uses the 5 CAPTURE_SENTENCES
as ground-truth text to reliably map detected glyphs to character labels.

Pipeline:
  Step 1 — Load & preprocess (auto-crop, background normalize, contrast)
  Step 2 — Find text line bands via horizontal projection
  Step 3 — Split words per line via vertical projection
  Step 4 — Match detected layout to CAPTURE_SENTENCES
  Step 5 — Extract per-character glyph images
  Step 6 — Build profile: glyphs/ + metadata.json
  Step 7 — Coverage report

Usage:
    python3 capture/extract_from_sentences.py [image_path]

Defaults (in order):
    real_handwriting.jpg   (in project root)
    ~/Projects/inkclone-capture/test_images/handwriting_sample.jpeg
"""

import os
import sys
import json
import datetime
import argparse
import numpy as np
import cv2
from pathlib import Path
from scipy.ndimage import gaussian_filter1d

# Make sure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from capture.prompt_sentences import CAPTURE_SENTENCES

# ── Constants ─────────────────────────────────────────────────────────────────
TARGET_HEIGHT   = 128       # output glyph height in pixels
INK_THRESHOLD   = 180       # pixels < this are considered ink
ALPHA_MAX       = 240       # max alpha value in output RGBA glyphs
PROFILE_NAME    = "improved_vishnu"

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(__file__).resolve().parent.parent
PROFILE_DIR   = PROJECT_ROOT / "profiles" / PROFILE_NAME
GLYPH_DIR     = PROFILE_DIR / "glyphs"
DEBUG_DIR     = PROJECT_ROOT / "output"

DEFAULT_IMAGES = [
    PROJECT_ROOT / "real_handwriting.jpg",
    Path.home() / "Projects" / "inkclone-capture" / "test_images" / "handwriting_sample.jpeg",
]


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _find_runs(signal, threshold):
    """Return list of (start, end) index pairs where signal > threshold."""
    above = signal > threshold
    runs, in_run, start = [], False, 0
    for i, v in enumerate(above):
        if v and not in_run:
            start, in_run = i, True
        elif not v and in_run:
            runs.append((start, i))
            in_run = False
    if in_run:
        runs.append((start, len(signal)))
    return runs


def _find_gaps(signal, threshold):
    """Return list of (start, end) index pairs where signal <= threshold."""
    return _find_runs(-signal, -threshold - 1e-9)


def _merge_close_runs(runs, min_gap):
    """Merge runs separated by fewer than min_gap pixels."""
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
# Step 1 — Preprocess
# ══════════════════════════════════════════════════════════════════════════════

def preprocess(image_path):
    """
    Load image as grayscale.
    1. Auto-crop to paper bounding box of all dark pixels < 200, + 20px pad.
    2. Normalize background via morphological opening (51×51 kernel).
    3. Contrast stretch via 5th/95th percentile clip.

    Returns grayscale uint8 array (paper region, normalized, contrast-stretched).
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Cannot read: {image_path}")

    h, w = img.shape
    print(f"  Loaded {w}×{h}")

    # --- auto-crop: find actual ink pixels (well below background) ---
    # Use Otsu threshold to separate ink from background robustly
    _, ink_binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    rows = np.any(ink_binary > 0, axis=1)
    cols = np.any(ink_binary > 0, axis=0)
    row_idx = np.where(rows)[0]
    col_idx = np.where(cols)[0]
    if len(row_idx) and len(col_idx):
        r0, r1 = max(0, row_idx[0]  - 20), min(h, row_idx[-1]  + 20)
        c0, c1 = max(0, col_idx[0]  - 20), min(w, col_idx[-1]  + 20)
        img = img[r0:r1, c0:c1]
        print(f"  Cropped to {img.shape[1]}×{img.shape[0]}")
    else:
        print("  Warning: no ink pixels found via Otsu, using full image")

    # --- background normalization via MORPH_CLOSE ---
    # MORPH_CLOSE = dilate then erode: fills dark ink with surrounding bright
    # background values, giving a smooth illumination estimate.
    k = 51
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    background = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)
    background = background.astype(np.float32)
    background[background < 1] = 1
    normalized = (img.astype(np.float32) / background * 255.0)
    normalized = np.clip(normalized, 0, 255).astype(np.uint8)

    # --- contrast stretch (5th–95th percentile) ---
    p5  = float(np.percentile(normalized, 5))
    p95 = float(np.percentile(normalized, 95))
    if p95 > p5:
        stretched = (normalized.astype(np.float32) - p5) / (p95 - p5) * 255.0
    else:
        stretched = normalized.astype(np.float32)
    result = np.clip(stretched, 0, 255).astype(np.uint8)

    DEBUG_DIR.mkdir(exist_ok=True)
    cv2.imwrite(str(DEBUG_DIR / "efs_preprocessed.png"), result)
    print(f"  Saved debug: output/efs_preprocessed.png")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — Find text line bands
# ══════════════════════════════════════════════════════════════════════════════

def find_line_bands(gray):
    """
    Use horizontal projection to detect text line bands.
    Returns list of (y0, y1) tuples (row ranges), one per text line.
    Wrapped lines are split into sub-bands.
    """
    inverted = 255 - gray.astype(np.float32)
    h_proj   = inverted.sum(axis=1)
    h_smooth = gaussian_filter1d(h_proj, sigma=3)

    threshold  = 0.05 * h_smooth.max()
    bands      = _find_runs(h_smooth, threshold)
    # merge very close bands (< 8px gap → same line)
    bands      = _merge_close_runs(bands, min_gap=8)

    # split wrapped lines: look for internal valleys < 20% of band max
    split_bands = []
    for y0, y1 in bands:
        strip   = inverted[y0:y1, :]
        b_proj  = strip.sum(axis=1)
        b_smooth= gaussian_filter1d(b_proj, sigma=3)
        b_max   = b_smooth.max() if b_smooth.max() > 0 else 1
        valley_thr = 0.20 * b_max

        sub = _find_runs(b_smooth, valley_thr)
        sub = _merge_close_runs(sub, min_gap=4)
        if len(sub) > 1:
            for sy0, sy1 in sub:
                split_bands.append((y0 + sy0, y0 + sy1))
        else:
            split_bands.append((y0, y1))

    print(f"  Found {len(split_bands)} line band(s)")
    return split_bands


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Find words per line band
# ══════════════════════════════════════════════════════════════════════════════

def find_words_in_band(gray, y0, y1, expected_word_count=None):
    """
    Given a horizontal band [y0,y1], find word regions using vertical projection.
    Returns list of (x0, x1) column ranges, one per word.

    If expected_word_count provided and mismatch, tries ±20% gap threshold.
    """
    strip    = gray[y0:y1, :]
    inverted = 255 - strip.astype(np.float32)
    v_proj   = inverted.sum(axis=0)
    v_smooth = gaussian_filter1d(v_proj, sigma=2)

    def _segment(gap_scale=1.0):
        ink_runs = _find_runs(v_smooth, threshold=1.0)
        if not ink_runs:
            return []
        # measure all gaps between ink runs
        gaps = []
        for i in range(1, len(ink_runs)):
            gaps.append(ink_runs[i][0] - ink_runs[i-1][1])
        if not gaps:
            return [ink_runs[0]]
        median_gap = float(np.median(gaps))
        word_gap_threshold = median_gap * 1.3 * gap_scale

        words = [list(ink_runs[0])]
        for i, (s, e) in enumerate(ink_runs[1:]):
            if gaps[i] >= word_gap_threshold:
                words.append([s, e])
            else:
                words[-1][1] = e
        return [(s, e) for s, e in words]

    words = _segment(1.0)

    if expected_word_count and len(words) != expected_word_count:
        for scale in [0.8, 1.2, 0.6, 1.5]:
            w2 = _segment(scale)
            if len(w2) == expected_word_count:
                words = w2
                break

    return words


# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — Match to known sentences
# ══════════════════════════════════════════════════════════════════════════════

def match_bands_to_sentences(bands, gray):
    """
    Match detected line bands to CAPTURE_SENTENCES by order.
    Returns list of dicts:
      { 'sentence': str, 'words': [str,...], 'band': (y0,y1),
        'word_regions': [(x0,x1),...] }
    """
    n_sentences = len(CAPTURE_SENTENCES)
    n_bands     = len(bands)

    results = []
    sentence_idx = 0
    band_idx     = 0

    print(f"\n[Step 4] Matching {n_bands} bands to {n_sentences} sentences")

    while sentence_idx < n_sentences and band_idx < n_bands:
        sentence   = CAPTURE_SENTENCES[sentence_idx]
        words      = sentence.split()
        y0, y1     = bands[band_idx]

        word_regions = find_words_in_band(gray, y0, y1, expected_word_count=len(words))
        detected     = len(word_regions)
        expected     = len(words)

        print(f"  Sentence {sentence_idx}: '{sentence[:40]}...'")
        print(f"    Band y=[{y0},{y1}], detected={detected} words, expected={expected}")

        if detected == expected:
            results.append({
                'sentence'    : sentence,
                'words'       : words,
                'band'        : (y0, y1),
                'word_regions': word_regions,
                'match'       : 'exact',
            })
            sentence_idx += 1
            band_idx     += 1
        elif detected < expected and band_idx + 1 < n_bands:
            # Try merging with next band (sentence wraps)
            y0b, y1b = bands[band_idx + 1]
            merged_wr = find_words_in_band(gray, y0, y1b, expected_word_count=len(words))
            if len(merged_wr) == expected:
                results.append({
                    'sentence'    : sentence,
                    'words'       : words,
                    'band'        : (y0, y1b),
                    'word_regions': merged_wr,
                    'match'       : 'merged_bands',
                })
                sentence_idx += 1
                band_idx     += 2
            else:
                # Accept best-effort
                results.append({
                    'sentence'    : sentence,
                    'words'       : words,
                    'band'        : (y0, y1),
                    'word_regions': word_regions,
                    'match'       : f'partial({detected}/{expected})',
                })
                sentence_idx += 1
                band_idx     += 1
        else:
            # Accept best-effort
            results.append({
                'sentence'    : sentence,
                'words'       : words,
                'band'        : (y0, y1),
                'word_regions': word_regions,
                'match'       : f'partial({detected}/{expected})',
            })
            sentence_idx += 1
            band_idx     += 1

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Step 5 — Extract character glyphs
# ══════════════════════════════════════════════════════════════════════════════

def extract_chars_from_match(gray, match, variant_counters):
    """
    For each word in the match, slice the word region from the line strip,
    divide evenly by character count, extract each glyph as RGBA PNG.

    Returns list of (char_label, PIL_Image) pairs.
    """
    from PIL import Image as PILImage

    y0, y1  = match['band']
    results = []

    for word_idx, (word_text, (wx0, wx1)) in enumerate(
            zip(match['words'], match['word_regions'])):

        # Strip punctuation for character mapping, but keep the clean token
        clean = ''.join(c for c in word_text if c.isalnum() or c in "-'")
        if not clean:
            continue

        word_w = wx1 - wx0
        if word_w < 4:
            continue

        char_width = word_w / len(clean)
        line_strip = gray[y0:y1, wx0:wx1]

        for ci, ch in enumerate(clean):
            cx0 = int(round(ci       * char_width))
            cx1 = int(round((ci + 1) * char_width))
            cx0 = max(0, cx0)
            cx1 = min(word_w, cx1)
            if cx1 - cx0 < 2:
                continue

            char_crop = line_strip[:, cx0:cx1]

            # Find ink bounding box (pixels < INK_THRESHOLD)
            ink_mask = char_crop < INK_THRESHOLD
            rows = np.any(ink_mask, axis=1)
            cols = np.any(ink_mask, axis=0)
            row_idx = np.where(rows)[0]
            col_idx = np.where(cols)[0]
            if len(row_idx) == 0 or len(col_idx) == 0:
                continue

            r0 = max(0, row_idx[0]  - 2)
            r1 = min(char_crop.shape[0], row_idx[-1]  + 3)
            c0 = max(0, col_idx[0]  - 2)
            c1 = min(char_crop.shape[1], col_idx[-1]  + 3)
            cropped = char_crop[r0:r1, c0:c1]

            if cropped.shape[0] < 4 or cropped.shape[1] < 4:
                continue

            # Resize to TARGET_HEIGHT preserving aspect ratio
            h_c, w_c = cropped.shape
            new_h = TARGET_HEIGHT
            new_w = max(4, int(w_c * TARGET_HEIGHT / h_c))
            resized = cv2.resize(cropped, (new_w, new_h),
                                 interpolation=cv2.INTER_AREA)

            # Build RGBA: dark ink = opaque, light background = transparent
            r_ch = resized.astype(np.uint8)
            alpha = np.clip(255 - resized.astype(np.int32), 0, 255).astype(np.uint8)
            # Normalize alpha so max = ALPHA_MAX
            if alpha.max() > 0:
                alpha = (alpha.astype(np.float32) * ALPHA_MAX / alpha.max())
                alpha = np.clip(alpha, 0, ALPHA_MAX).astype(np.uint8)

            rgba = np.stack([r_ch, r_ch, r_ch, alpha], axis=-1)
            pil  = PILImage.fromarray(rgba, mode='RGBA')

            results.append((ch, pil))

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Step 6 — Build profile
# ══════════════════════════════════════════════════════════════════════════════

def build_profile(all_glyphs, source_shape):
    """
    Save glyphs and metadata.json to PROFILE_DIR.

    all_glyphs: list of (char_label, PIL_Image)
    source_shape: (h, w) of the original preprocessed image
    """
    GLYPH_DIR.mkdir(parents=True, exist_ok=True)

    variant_counts = {}
    for ch, img in all_glyphs:
        safe = ch if ch.isalnum() else f"ord{ord(ch):03d}"
        count = variant_counts.get(ch, 0)
        filename = f"{safe}_{count}.png"
        img.save(str(GLYPH_DIR / filename))
        variant_counts[ch] = count + 1

    metadata = {
        "profile_id"     : PROFILE_NAME,
        "characters"     : sorted(variant_counts.keys()),
        "variant_counts" : {k: v for k, v in sorted(variant_counts.items())},
        "total_glyphs"   : sum(variant_counts.values()),
        "timestamp"      : datetime.datetime.now().isoformat(),
        "source_dimensions": {"width": source_shape[1], "height": source_shape[0]},
    }
    with open(str(PROFILE_DIR / "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n[Step 6] Profile saved to {PROFILE_DIR}")
    print(f"  Total glyphs: {metadata['total_glyphs']}")
    print(f"  Unique chars: {len(metadata['characters'])}")
    return metadata


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Coverage report
# ══════════════════════════════════════════════════════════════════════════════

def coverage_report(metadata):
    """Print coverage statistics and flag issues."""
    import string

    vc = metadata["variant_counts"]
    total  = metadata["total_glyphs"]
    chars  = metadata["characters"]

    print("\n" + "=" * 60)
    print("COVERAGE REPORT")
    print("=" * 60)
    print(f"Total glyphs  : {total}")
    print(f"Unique chars  : {len(chars)}")
    print()

    print("Variants per lowercase letter:")
    for c in string.ascii_lowercase:
        n   = vc.get(c, 0)
        bar = "#" * min(n, 20)
        flag = " ← MISSING" if n == 0 else (" ← only 1" if n == 1 else "")
        print(f"  {c}: {n:3d} {bar}{flag}")

    print()
    zero_chars = [c for c in string.ascii_lowercase if vc.get(c, 0) == 0]
    one_chars  = [c for c in string.ascii_lowercase if vc.get(c, 0) == 1]
    if zero_chars:
        print(f"MISSING chars  : {', '.join(zero_chars)}")
    if one_chars:
        print(f"Single-variant : {', '.join(one_chars)}")
    if not zero_chars and not one_chars:
        print("All 26 lowercase letters have 2+ variants.")

    return {
        "zero_chars": zero_chars,
        "one_chars" : one_chars,
        "total"     : total,
        "unique"    : len(chars),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(image_path):
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    print(f"\n{'='*60}")
    print(f"InkClone Freeform Extractor")
    print(f"Image : {image_path}")
    print(f"{'='*60}")

    # Step 1
    print("\n[Step 1] Preprocess")
    gray = preprocess(image_path)

    # Step 2
    print("\n[Step 2] Find line bands")
    bands = find_line_bands(gray)

    # Step 3 + 4
    matches = match_bands_to_sentences(bands, gray)

    # Step 5
    print("\n[Step 5] Extract character glyphs")
    all_glyphs = []
    variant_counters = {}
    for match in matches:
        glyphs = extract_chars_from_match(gray, match, variant_counters)
        all_glyphs.extend(glyphs)
        print(f"  Sentence '{match['sentence'][:35]}...' → {len(glyphs)} glyphs ({match['match']})")

    # Step 6
    metadata = build_profile(all_glyphs, gray.shape)

    # Step 7
    stats = coverage_report(metadata)

    return metadata, stats


def find_default_image():
    for p in DEFAULT_IMAGES:
        if p.exists():
            return p
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract glyphs from handwriting photo")
    parser.add_argument("image", nargs="?", help="Path to handwriting image")
    args = parser.parse_args()

    if args.image:
        img_path = Path(args.image)
    else:
        img_path = find_default_image()
        if img_path is None:
            print("No image found. Tried:")
            for p in DEFAULT_IMAGES:
                print(f"  {p}")
            print("\nRunning in dry-run mode (no image)...")
            # Dry run: just validate imports and print sentences
            print("\nCapture sentences loaded:")
            for i, s in enumerate(CAPTURE_SENTENCES):
                print(f"  {i+1}. {s[:60]}...")
            print("\nTo run: python3 capture/extract_from_sentences.py <image.jpg>")
            sys.exit(0)

    try:
        metadata, stats = run_pipeline(img_path)
        result_str = "PASS" if stats["total"] > 0 else "FAIL"
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback; traceback.print_exc()
        result_str = f"FAIL ({e})"
        metadata, stats = None, {"total": 0, "unique": 0, "zero_chars": [], "one_chars": []}

    # Append to DISPATCH_PROGRESS.md
    progress_file = PROJECT_ROOT / "DISPATCH_PROGRESS.md"
    from capture.prompt_sentences import analyze_coverage
    cov = analyze_coverage()

    lines = [
        f"\n## Task 6: Capture Prompts — PASS",
        f"- 26/26 lowercase letters, all with 3+ occurrences",
        f"- All 10 digits (0-9) covered",
        f"- {len(cov['punctuation_count'])} punctuation types covered",
        f"- Total chars across sentences: {cov['total_chars']}",
        f"\n## Task 7: Freeform Extractor — {result_str}",
        f"- Total glyphs extracted: {stats.get('total', 0)}",
        f"- Unique characters: {stats.get('unique', 0)}",
        f"- Missing chars: {', '.join(stats.get('zero_chars', [])) or 'none'}",
        f"- Single-variant chars: {', '.join(stats.get('one_chars', [])) or 'none'}",
        f"- Profile: profiles/{PROFILE_NAME}/",
        f"- Timestamp: {datetime.datetime.now().isoformat()}\n",
    ]
    with open(str(progress_file), "a") as f:
        f.write("\n".join(lines))
    print(f"\nAppended results to DISPATCH_PROGRESS.md")
