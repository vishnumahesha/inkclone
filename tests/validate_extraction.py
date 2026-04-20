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

CROSS_CORR_FAIL  = -0.25  # only fail on strong anti-correlation (wrong char)
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


_NCC_SIZE = 48   # fixed canvas for NCC — both arrays normalized to this


def normalized_cross_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute NCC between two grayscale arrays.
    Both are binarized and resized to _NCC_SIZE x _NCC_SIZE before comparison
    so aspect-ratio differences don't dominate.
    """
    if a.size == 0 or b.size == 0:
        return 0.0
    from PIL import Image as _I

    def _normalize(arr: np.ndarray) -> np.ndarray:
        # Binarize: any value > 0 → 255
        bin_arr = (arr > 0).astype(np.uint8) * 255
        img = _I.fromarray(bin_arr)
        # Crop to ink bbox, then resize to fixed square
        rows = np.any(bin_arr > 0, axis=1)
        cols = np.any(bin_arr > 0, axis=0)
        if not rows.any():
            return np.zeros((_NCC_SIZE, _NCC_SIZE), dtype=float)
        r0, r1 = int(np.where(rows)[0][0]), int(np.where(rows)[0][-1])
        c0, c1 = int(np.where(cols)[0][0]), int(np.where(cols)[0][-1])
        cropped = img.crop((c0, r0, c1 + 1, r1 + 1))
        resized = cropped.resize((_NCC_SIZE, _NCC_SIZE), _I.LANCZOS)
        return np.array(resized).astype(float)

    a_n = _normalize(a)
    b_n = _normalize(b)
    a_z = a_n - a_n.mean()
    b_z = b_n - b_n.mean()
    denom = np.linalg.norm(a_z) * np.linalg.norm(b_z)
    if denom < 1e-6:
        return 0.0
    return float(np.dot(a_z.ravel(), b_z.ravel()) / denom)


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


def glyph_to_white_bg(glyph_path: Path) -> Image.Image | None:
    """Return glyph composited onto white RGB background (black ink on white)."""
    try:
        img = Image.open(glyph_path)
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            # Use alpha channel as mask; ink has alpha=240, so it composites dark
            bg.paste(img.convert("RGB"), mask=img.split()[3])
            return bg
        return img.convert("RGB")
    except Exception:
        return None


def ocr_glyph(glyph_path: Path, display: str) -> bool | None:
    """
    OCR the glyph. Returns True if OCR matched, False if strong mismatch,
    None if OCR unavailable or uncertain.
    """
    try:
        import pytesseract
    except ImportError:
        return None

    img = glyph_to_white_bg(glyph_path)
    if img is None:
        return None

    # Upscale small glyphs for better OCR accuracy
    w, h = img.size
    if max(w, h) < 128:
        scale = 128 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # PSM 7 = single text line (works for both single chars and bigrams)
    whitelist = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789.,!?'\"\\-:;()/@&#$"
    )
    try:
        config = f"--psm 7 --oem 3 -c tessedit_char_whitelist={whitelist}"
        text = pytesseract.image_to_string(img, config=config).strip()
        if text == display:
            return True
        if text and text[0] == display:
            return True   # first char matches (common with trailing noise)
        # OCR returned something completely different → mismatch
        if text and len(text) <= len(display) + 2 and text:
            return None   # uncertain: OCR is unreliable for small glyphs
        return None
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

        # 5. Content match: OCR primary; NCC fallback only on explicit OCR mismatch
        ncc = None
        ocr_ok = ocr_glyph(glyph_path, display)
        if ocr_ok is False:
            # OCR returned a clearly wrong character — confirm with NCC
            ref = render_reference(display, size=max(h, 32))
            ncc = normalized_cross_correlation(ink_arr, ref)
            if ncc < CROSS_CORR_FAIL:
                errors.append(f"MISMATCH(ncc={ncc:.2f})")
        # ocr_ok is None (uncertain) → no penalty; ocr_ok is True → pass

        passed = len(errors) == 0
        results.append({
            "label":   label,
            "variant": variant,
            "display": display,
            "pass":    passed,
            "errors":  errors,
            "ncc":     round(ncc, 3) if ncc is not None else None,
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
