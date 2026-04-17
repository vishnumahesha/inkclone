#!/usr/bin/env python3
"""
clean_glyphs.py — Hard-threshold glyph cleaner for InkClone.

Problem: extracted glyphs have soft gray backgrounds (gradients, noise) because
the extraction preserved grayscale alpha values. This makes OCR fail badly.

Fix: composite each glyph over white, threshold at 180 grayscale for a hard
black-on-transparent cutoff, then crop tight, resize to 128px height, and
discard glyphs whose ink area is < 5% of the image (pure noise).

After cleaning, runs a mini eval (OCR score via pytesseract) and generates
a homework demo on college-ruled paper.
"""

import os
import sys
import difflib
from pathlib import Path

import numpy as np
from PIL import Image

# ── paths ──────────────────────────────────────────────────────────────────────
INKCLONE_DIR = Path(__file__).parent
GLYPHS_DIR = INKCLONE_DIR / "profiles" / "freeform_vishnu" / "glyphs"
OUTPUT_DEMO_PATH = INKCLONE_DIR / "output" / "demos" / "homework_cleaned.png"

sys.path.insert(0, str(INKCLONE_DIR))


# ── cleaning ───────────────────────────────────────────────────────────────────

def clean_glyph(img: Image.Image, threshold: int = 180, pad: int = 3,
                min_ink_fraction: float = 0.05) -> Image.Image | None:
    """
    Clean a single RGBA glyph image.

    Steps:
    1. Composite over white to get a flat grayscale luminance.
    2. Hard cutoff: luminance < threshold → ink (alpha 240), else transparent.
    3. Crop tight to ink bounding box with `pad` pixels padding.
    4. Return None if ink area < min_ink_fraction of the cropped image.
    5. Resize to 128 px height preserving aspect ratio.
    """
    # Step 1 — grayscale composite over white
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    arr = np.array(img, dtype=np.float32)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    a_norm = a / 255.0

    # Composite: pixel * alpha + white * (1 - alpha)
    gray = (r * a_norm + 255.0 * (1.0 - a_norm) * 0.299 +
            g * a_norm + 255.0 * (1.0 - a_norm) * 0.587 +
            b * a_norm + 255.0 * (1.0 - a_norm) * 0.114)
    # Simpler correct composite to grayscale:
    comp_r = r * a_norm + 255.0 * (1.0 - a_norm)
    comp_g = g * a_norm + 255.0 * (1.0 - a_norm)
    comp_b = b * a_norm + 255.0 * (1.0 - a_norm)
    gray = 0.299 * comp_r + 0.587 * comp_g + 0.114 * comp_b  # shape (H, W)

    # Step 2 — hard threshold
    ink_mask = gray < threshold  # True where pixel is dark (ink)

    H, W = ink_mask.shape
    total_pixels = H * W
    ink_pixels = ink_mask.sum()

    # Step 4 — discard if < 5% ink (check before cropping)
    if ink_pixels < min_ink_fraction * total_pixels:
        return None

    # Step 3 — find bounding box
    rows = np.any(ink_mask, axis=1)
    cols = np.any(ink_mask, axis=0)
    if not rows.any():
        return None
    rmin, rmax = int(np.where(rows)[0][0]), int(np.where(rows)[0][-1])
    cmin, cmax = int(np.where(cols)[0][0]), int(np.where(cols)[0][-1])

    # Add padding, clamp to image bounds
    rmin = max(0, rmin - pad)
    rmax = min(H - 1, rmax + pad)
    cmin = max(0, cmin - pad)
    cmax = min(W - 1, cmax + pad)

    # Crop the ink_mask
    cropped_mask = ink_mask[rmin:rmax + 1, cmin:cmax + 1]
    ch, cw = cropped_mask.shape

    # Re-check ink fraction on cropped area
    if cropped_mask.sum() < min_ink_fraction * ch * cw:
        return None

    # Build clean RGBA: ink pixels → (0, 0, 0, 240), else → (0, 0, 0, 0)
    out_arr = np.zeros((ch, cw, 4), dtype=np.uint8)
    out_arr[cropped_mask] = (0, 0, 0, 240)

    clean_img = Image.fromarray(out_arr, "RGBA")

    # Step 5 — resize to 128px height preserving aspect ratio
    target_h = 128
    scale = target_h / ch
    target_w = max(1, int(round(cw * scale)))
    clean_img = clean_img.resize((target_w, target_h), Image.LANCZOS)

    return clean_img


def clean_all_glyphs(glyphs_dir: Path, threshold: int = 180) -> dict:
    """
    Process every PNG in glyphs_dir in-place.
    Returns stats: {total, cleaned, discarded, errors}.
    """
    pngs = sorted(glyphs_dir.glob("*.png"))
    if not pngs:
        print(f"[clean_glyphs] No PNGs found in {glyphs_dir}")
        return {}

    stats = {"total": len(pngs), "cleaned": 0, "discarded": 0, "errors": 0}
    print(f"[clean_glyphs] Processing {len(pngs)} glyphs in {glyphs_dir} …")

    for png_path in pngs:
        try:
            img = Image.open(png_path)
            result = clean_glyph(img, threshold=threshold)
            if result is None:
                print(f"  DISCARD  {png_path.name}  (ink area < 5% — noise)")
                png_path.unlink()
                stats["discarded"] += 1
            else:
                result.save(str(png_path))
                stats["cleaned"] += 1
        except Exception as exc:
            print(f"  ERROR    {png_path.name}: {exc}")
            stats["errors"] += 1

    print(f"[clean_glyphs] Done — cleaned={stats['cleaned']}, "
          f"discarded={stats['discarded']}, errors={stats['errors']}")
    return stats


# ── mini eval ──────────────────────────────────────────────────────────────────

EVAL_PHRASES = [
    "Hello world",
    "the quick brown fox",
    "extraordinary",
    "nevertheless",
    "she said hello",
    "InkClone test",
    "handwriting",
    "pack my box",
]


def run_mini_eval(glyph_bank: dict) -> float:
    """Render each eval phrase and OCR it. Returns mean accuracy 0-1."""
    try:
        import pytesseract
    except ImportError:
        print("[eval] pytesseract not installed — skipping OCR eval")
        return None

    from render_engine import HandwritingRenderer
    from paper_backgrounds import generate_college_ruled
    from compositor import composite, INK_COLORS
    import difflib

    scores = []
    for phrase in EVAL_PHRASES:
        try:
            renderer = HandwritingRenderer(glyph_bank, seed=42)
            text_img = renderer.render(phrase, page_width=2400, page_height=3200, neatness=0.7)
            paper = generate_college_ruled(width=2400, height=3200)
            comp = composite(text_img, paper, ink_color=INK_COLORS["blue"])

            ocr_raw = pytesseract.image_to_string(comp, config="--psm 6")
            expected = phrase.lower().replace(" ", "")
            got = ocr_raw.lower().replace(" ", "").replace("\n", "")
            ratio = difflib.SequenceMatcher(None, expected, got).ratio()
            scores.append(ratio)
            print(f"  [{round(ratio*100,1):5.1f}%] '{phrase}'  →  OCR: '{ocr_raw.strip()[:60]}'")
        except Exception as exc:
            print(f"  [ERROR] '{phrase}': {exc}")

    if not scores:
        return None
    mean_score = sum(scores) / len(scores)
    return mean_score


# ── homework demo ──────────────────────────────────────────────────────────────

DEMO_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "Pack my box with five dozen liquid jugs. "
    "She explained that nothing was impossible if you worked hard. "
    "The history of the west was shaped by expansion. "
    "After years of practice, handwriting became natural."
)


def generate_homework_demo(glyph_bank: dict, output_path: Path):
    """Render a homework page on college-ruled paper and save it."""
    from render_engine import HandwritingRenderer
    from paper_backgrounds import generate_college_ruled
    from compositor import composite, INK_COLORS

    output_path.parent.mkdir(parents=True, exist_ok=True)

    renderer = HandwritingRenderer(glyph_bank, seed=7)
    text_img = renderer.render(DEMO_TEXT, page_width=2400, page_height=3200, neatness=0.7)
    paper = generate_college_ruled(width=2400, height=3200)
    result = composite(text_img, paper, ink_color=INK_COLORS["blue"])
    result.save(str(output_path))
    print(f"[demo] Saved homework demo → {output_path}")
    return result


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("InkClone Glyph Cleaner")
    print("=" * 60)

    # ── 1. Clean glyphs ────────────────────────────────────────────────────────
    print(f"\n[1/3] Cleaning glyphs in {GLYPHS_DIR}")
    stats = clean_all_glyphs(GLYPHS_DIR, threshold=180)

    # ── 2. Run eval ────────────────────────────────────────────────────────────
    print("\n[2/3] Running OCR eval with cleaned glyphs …")
    from glyph_loader import load_profile_glyphs
    glyph_bank = load_profile_glyphs(INKCLONE_DIR / "profiles" / "freeform_vishnu",
                                     fallback_dummy=True)
    print(f"  Loaded {len(glyph_bank)} chars, "
          f"{sum(len(v) for v in glyph_bank.values())} variants")

    # Try running the full eval harness if available
    eval_script = INKCLONE_DIR / "eval" / "run_eval.py"
    if eval_script.exists():
        import subprocess
        print(f"\n  Running full eval: {eval_script}")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(INKCLONE_DIR)
        result = subprocess.run(
            [sys.executable, str(eval_script)],
            cwd=str(INKCLONE_DIR),
            capture_output=False,
            env=env,
        )
        if result.returncode != 0:
            print("  Full eval failed, falling back to mini eval …")
            score = run_mini_eval(glyph_bank)
        else:
            score = None  # reported by run_eval.py itself
    else:
        print(f"  eval/run_eval.py not found — running mini eval …")
        score = run_mini_eval(glyph_bank)

    if score is not None:
        print(f"\n  OCR mean accuracy: {round(score * 100, 1)}%")

    # ── 3. Generate homework demo ──────────────────────────────────────────────
    print(f"\n[3/3] Generating homework demo → {OUTPUT_DEMO_PATH}")
    generate_homework_demo(glyph_bank, OUTPUT_DEMO_PATH)

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Glyphs processed : {stats.get('total', 0)}")
    print(f"  Glyphs cleaned   : {stats.get('cleaned', 0)}")
    print(f"  Glyphs discarded : {stats.get('discarded', 0)} (noise)")
    if score is not None:
        print(f"  OCR accuracy     : {round(score * 100, 1)}%  (mini eval, {len(EVAL_PHRASES)} phrases)")
    print(f"  Demo saved       : {OUTPUT_DEMO_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
