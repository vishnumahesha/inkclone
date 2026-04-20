#!/usr/bin/env python3
"""
tests/validate_extraction.py — Validate glyph extraction against synthetic manifest.

Usage:
    python tests/validate_extraction.py <profile_name>

Reads:
    tests/synthetic/manifest.json       — ground truth (238 content cells)
    profiles/<profile_name>/glyphs/     — extracted glyph PNGs

Per-glyph checks:
  1. File exists
  2. Ink pixels >= MIN_INK_PIXELS
  3. Not full-cell (ink ratio < 0.85)
  4. Sane aspect ratio (0.08 < w/h < 8.0)
  5. Content match via cross-correlation with reference render (>0.5 pass, <0.3 fail)

Prints structured report and SCORE: X/238.
Exits 0 if score > 230, else exits 1.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from template_config import MIN_INK_PIXELS, TOTAL_CONTENT_CELLS

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MANIFEST_PATH = ROOT / "tests" / "synthetic" / "manifest.json"
PROFILES_DIR  = ROOT / "profiles"

CROSS_CORR_PASS  = 0.50
CROSS_CORR_FAIL  = 0.30
INK_RATIO_MAX    = 0.85   # full-cell threshold
MIN_ASPECT       = 0.08
MAX_ASPECT       = 8.0


def load_manifest() -> list:
    return json.loads(MANIFEST_PATH.read_text())


def _find_font():
    candidates = [
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/ArialHB.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


_FONT_PATH = _find_font()


def render_reference(display: str, size: int = 64) -> np.ndarray:
    """Render display string to a grayscale numpy array (inverted: ink=255, bg=0)."""
    img = Image.new("L", (size * max(1, len(display)), size), 255)
    draw = ImageDraw.Draw(img)
    try:
        if _FONT_PATH:
            font = ImageFont.truetype(_FONT_PATH, int(size * 0.7))
        else:
            font = ImageFont.load_default()
        bb = font.getbbox(display)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        draw.text((-bb[0] + 2, -bb[1] + 2), display, fill=0, font=font)
    except Exception:
        draw.text((2, 2), display, fill=0)
    arr = np.array(img)
    return (255 - arr)   # invert: ink=255


def normalized_cross_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Compute NCC between two grayscale arrays after resizing b to a's shape."""
    if a.size == 0 or b.size == 0:
        return 0.0
    h, w = a.shape
    from PIL import Image as _I
    b_img = _I.fromarray(b.astype(np.uint8))
    b_resized = np.array(b_img.resize((w, h), _I.LANCZOS)).astype(float)
    a_f = a.astype(float)

    a_norm = a_f - a_f.mean()
    b_norm = b_resized - b_resized.mean()
    denom = (np.linalg.norm(a_norm) * np.linalg.norm(b_norm))
    if denom < 1e-6:
        return 0.0
    return float(np.dot(a_norm.ravel(), b_norm.ravel()) / denom)


def glyph_to_ink_array(glyph_path: Path) -> np.ndarray | None:
    """Load RGBA glyph, return alpha channel as grayscale array (ink=255)."""
    try:
        img = Image.open(glyph_path)
        if img.mode == "RGBA":
            arr = np.array(img)
            return arr[:, :, 3]   # alpha channel
        else:
            arr = np.array(img.convert("L"))
            return (255 - arr)    # assume black-on-white
    except Exception:
        return None


def validate_profile(profile_name: str) -> dict:
    manifest = load_manifest()
    glyphs_dir = PROFILES_DIR / profile_name / "glyphs"

    if not glyphs_dir.exists():
        print(f"ERROR: {glyphs_dir} does not exist")
        sys.exit(1)

    results = []
    categories = {
        "lowercase": {"pass": 0, "fail": 0, "total": 0},
        "uppercase": {"pass": 0, "fail": 0, "total": 0},
        "digits":    {"pass": 0, "fail": 0, "total": 0},
        "punct":     {"pass": 0, "fail": 0, "total": 0},
        "bigrams":   {"pass": 0, "fail": 0, "total": 0},
    }

    _PUNCT_LABELS = {
        'period','comma','exclaim','question','apostrophe','quote',
        'hyphen','colon','semicolon','lparen','rparen','slash',
        'atsign','ampersand','hash','dollar',
    }

    def get_category(label: str) -> str:
        if label.startswith("upper_"):  return "uppercase"
        if label.startswith("digit_"):  return "digits"
        if label in _PUNCT_LABELS:      return "punct"
        if len(label) > 1:              return "bigrams"
        return "lowercase"

    for entry in manifest:
        label   = entry["label"]
        variant = entry["variant"]
        display = entry["display"]
        page    = entry["page"]

        cat = get_category(label)
        categories[cat]["total"] += 1

        fname = f"{label}_{variant}.png"
        glyph_path = glyphs_dir / fname

        errors = []

        # 1. File exists
        if not glyph_path.exists():
            errors.append("MISSING")
            results.append({"label": label, "variant": variant, "pass": False,
                            "errors": errors, "category": cat})
            categories[cat]["fail"] += 1
            continue

        # Load glyph
        ink_arr = glyph_to_ink_array(glyph_path)
        if ink_arr is None:
            errors.append("LOAD_FAIL")
            results.append({"label": label, "variant": variant, "pass": False,
                            "errors": errors, "category": cat})
            categories[cat]["fail"] += 1
            continue

        h, w = ink_arr.shape
        ink_px = int((ink_arr > 0).sum())
        total_px = h * w

        # 2. Ink pixels
        if ink_px < MIN_INK_PIXELS:
            errors.append(f"LOW_INK({ink_px}<{MIN_INK_PIXELS})")

        # 3. Not full-cell
        if total_px > 0 and ink_px / total_px > INK_RATIO_MAX:
            errors.append(f"FULL_CELL({ink_px/total_px:.2f})")

        # 4. Aspect ratio
        if h > 0:
            ar = w / h
            if ar < MIN_ASPECT or ar > MAX_ASPECT:
                errors.append(f"BAD_AR({ar:.2f})")

        # 5. Content match via cross-correlation
        ref = render_reference(display, size=max(h, 32))
        ncc = normalized_cross_correlation(ink_arr, ref)
        if ncc < CROSS_CORR_FAIL:
            errors.append(f"MISMATCH(ncc={ncc:.2f})")
        elif ncc < CROSS_CORR_PASS:
            pass  # uncertain — don't penalize if other checks pass

        passed = len(errors) == 0
        results.append({
            "label":   label,
            "variant": variant,
            "display": display,
            "pass":    passed,
            "errors":  errors,
            "ncc":     round(ncc, 3),
            "ink_px":  ink_px,
            "size":    (w, h),
            "category": cat,
        })
        if passed:
            categories[cat]["pass"] += 1
        else:
            categories[cat]["fail"] += 1

    return {"results": results, "categories": categories}


def main():
    if len(sys.argv) < 2:
        print("Usage: python tests/validate_extraction.py <profile_name>")
        sys.exit(1)

    profile_name = sys.argv[1]
    print(f"\n{'='*60}")
    print(f"Validating profile: {profile_name}")
    print(f"{'='*60}")

    data = validate_profile(profile_name)
    results    = data["results"]
    categories = data["categories"]

    # Print failures
    failures = [r for r in results if not r["pass"]]
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for r in failures[:40]:   # cap at 40 lines
            print(f"  [{r['category']:10s}] {r['label']:20s} v{r['variant']}  {', '.join(r['errors'])}")
        if len(failures) > 40:
            print(f"  ... and {len(failures)-40} more")

    # Per-category summary
    print(f"\nPER-CATEGORY RESULTS:")
    cat_order = ["lowercase", "uppercase", "digits", "punct", "bigrams"]
    for cat in cat_order:
        c = categories[cat]
        pct = round(c["pass"] / max(1, c["total"]) * 100, 1)
        print(f"  {cat:10s}: {c['pass']:3d}/{c['total']:3d}  ({pct}%)")

    # Overall score
    score = sum(1 for r in results if r["pass"])
    total = TOTAL_CONTENT_CELLS
    verdict = "PASS" if score > 230 else "FAIL"

    print(f"\nSCORE: {score}/{total}")
    print(f"VERDICT: {verdict}")
    print(f"{'='*60}\n")

    sys.exit(0 if score > 230 else 1)


if __name__ == "__main__":
    main()
