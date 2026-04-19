"""
Glyph Bank Loader

Loads real glyphs from extracted images or falls back to dummy glyphs.
Provides seamless integration between dummy and real glyph banks.
"""

import json
import numpy as np
import cv2
from pathlib import Path
from PIL import Image, ImageDraw
from render_engine import create_dummy_glyph_bank


def _normalize_alpha(img, target_max=240):
    """Normalize alpha channel so the darkest pixel has alpha = target_max."""
    arr = np.array(img)
    alpha = arr[:, :, 3].astype(float)
    max_a = alpha.max()
    if max_a > 0:
        alpha = (alpha / max_a) * target_max
        arr[:, :, 3] = alpha.clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr, 'RGBA')


def _autocrop_glyph(img: Image.Image, padding: int = 3) -> Image.Image:
    """Crop to bounding box of actual letter ink, removing template guide marks.

    Template cells have guide lines/dots in the top portion followed by a large
    vertical gap before the actual handwritten letter. We detect this gap and
    crop to only the letter region.
    """
    arr = np.array(img)
    alpha = arr[:, :, 3]
    h, w = arr.shape[:2]

    ink_rows = np.where(np.any(alpha > 30, axis=1))[0]
    if len(ink_rows) == 0:
        return img

    # Find the largest vertical gap between consecutive ink rows.
    # Template marks → big empty gap → actual letter is the dominant pattern.
    start_row = 0
    if len(ink_rows) >= 2:
        gaps = [(int(ink_rows[i + 1]) - int(ink_rows[i]), i)
                for i in range(len(ink_rows) - 1)]
        max_gap, max_gap_i = max(gaps)
        # Only use the gap split if it's substantial and in the upper portion
        if max_gap > 8 and int(ink_rows[max_gap_i]) < h * 0.7:
            start_row = int(ink_rows[max_gap_i + 1])

    ink_below = alpha[start_row:, :]
    rows_with_ink = np.any(ink_below > 30, axis=1)
    cols_with_ink = np.any(ink_below > 30, axis=0)

    if not rows_with_ink.any() or not cols_with_ink.any():
        return img

    rmin = start_row + int(np.where(rows_with_ink)[0][0])
    rmax = start_row + int(np.where(rows_with_ink)[0][-1])
    cmin = int(np.where(cols_with_ink)[0][0])
    cmax = int(np.where(cols_with_ink)[0][-1])

    rmin = max(0, rmin - padding)
    rmax = min(h - 1, rmax + padding)
    cmin = max(0, cmin - padding)
    cmax = min(w - 1, cmax + padding)
    return Image.fromarray(arr[rmin:rmax + 1, cmin:cmax + 1], 'RGBA')


def _measure_stroke_width(img: Image.Image) -> float:
    """Estimate stroke width via distance transform on the alpha mask."""
    arr = np.array(img)
    binary = (arr[:, :, 3] > 10).astype(np.uint8)
    if binary.sum() == 0:
        return 0.0
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    nonzero = dist[dist > 0]
    if len(nonzero) == 0:
        return 0.0
    return float(np.median(nonzero)) * 2  # radius → diameter


def _normalize_stroke_widths(bank: dict) -> dict:
    """Dilate glyphs whose stroke width is <70% of median across lowercase chars."""
    lowercase = 'abcdefghijklmnopqrstuvwxyz'
    char_medians = {}
    for char in lowercase:
        if char not in bank:
            continue
        widths = [_measure_stroke_width(g) for g in bank[char]]
        widths = [w for w in widths if w > 0]
        if widths:
            char_medians[char] = float(np.median(widths))

    if not char_medians:
        return bank

    global_median = float(np.median(list(char_medians.values())))
    threshold = global_median * 0.70
    kernel = np.ones((2, 2), np.uint8)

    for char, char_median in char_medians.items():
        if char_median < threshold:
            new_variants = []
            for glyph in bank[char]:
                arr = np.array(glyph)
                arr[:, :, 3] = cv2.dilate(arr[:, :, 3], kernel, iterations=1)
                new_variants.append(Image.fromarray(arr, 'RGBA'))
            bank[char] = new_variants
            print(f"[glyph_loader] Dilated '{char}' (stroke {char_median:.1f}px < threshold {threshold:.1f}px)")

    return bank


def _apply_ink_pooling(img: Image.Image) -> Image.Image:
    """Boost alpha by 15% in a 3px radius around topmost and bottommost ink rows."""
    arr = np.array(img.copy())
    alpha = arr[:, :, 3].astype(float)

    if alpha.max() == 0:
        return img

    ink_rows = np.where(np.any(alpha > 10, axis=1))[0]
    if len(ink_rows) == 0:
        return img

    h, w = alpha.shape
    radius = 3

    for row in (ink_rows[0], ink_rows[-1]):
        ink_cols = np.where(alpha[row, :] > 10)[0]
        if len(ink_cols) == 0:
            continue
        center_col = int(np.median(ink_cols))
        y_lo = max(0, row - radius)
        y_hi = min(h, row + radius + 1)
        x_lo = max(0, center_col - radius)
        x_hi = min(w, center_col + radius + 1)
        ys, xs = np.mgrid[y_lo:y_hi, x_lo:x_hi]
        dist2 = (ys - row) ** 2 + (xs - center_col) ** 2
        mask = dist2 <= radius * radius
        alpha[y_lo:y_hi, x_lo:x_hi][mask] = np.clip(
            alpha[y_lo:y_hi, x_lo:x_hi][mask] * 1.15, 0, 255
        )

    arr[:, :, 3] = alpha.astype(np.uint8)
    return Image.fromarray(arr, 'RGBA')


WIDE_CHARS = set('mwMW') | {
    'th', 'he', 'in', 'an', 'er', 'on', 'ed', 're',
    'ou', 'es', 'ti', 'at', 'st', 'en', 'or', 'ng',
    'ing', 'the', 'and', 'tion',
}


def _is_valid_glyph(img: Image.Image, char: str) -> bool:
    w, h = img.size
    if w < 8 or h < 8:
        return False
    ar = w / h
    max_ar = 3.5 if char in WIDE_CHARS else 2.2
    if ar > max_ar or ar < 0.15:
        return False
    arr = np.array(img)
    if img.mode != 'RGBA':
        return True
    alpha = arr[:, :, 3]
    total_ink = int((alpha > 0).sum())
    if total_ink < 50:
        return False
    ink_rows = np.where(np.any(alpha > 0, axis=1))[0]
    if len(ink_rows) == 0 or (int(ink_rows[-1]) - int(ink_rows[0])) < 15:
        return False
    return True


def _ink_count(img: Image.Image) -> int:
    arr = np.array(img)
    if img.mode == 'RGBA':
        return int((arr[:, :, 3] > 0).sum())
    return int(np.any(arr > 0, axis=2).sum())


def _parse_glyph_stem(stem: str):
    """Parse glyph filename stem to character.
    Examples:
      'a_0'              -> 'a'
      'upper_P_0'        -> 'P'
      'digit_0_0'        -> '0'
      'period_0'         -> '.'
      'comma_0'          -> ','
      'exclaim_0'        -> '!'
      'question_0'       -> '?'
      'apostrophe_0'     -> "'"
      'hyphen_0'         -> '-'
      'colon_0'          -> ':'
      'semicolon_0'      -> ';'
      'lparen_0'         -> '('
      'rparen_0'         -> ')'
      'upper_A_fallback' -> 'A'
      'digit_5_fallback' -> '5'
    """
    # Strip _fallback suffix so the rest parses normally
    working = stem
    if working.endswith("_fallback"):
        working = working[: -len("_fallback")]

    # Punctuation aliases
    _PUNCT_MAP = {
        "period": ".",
        "comma": ",",
        "exclaim": "!",
        "question": "?",
        "apostrophe": "'",
        "hyphen": "-",
        "colon": ":",
        "semicolon": ";",
        "lparen": "(",
        "rparen": ")",
        "ampersand": "&",
        "hash": "#",
        "atsign": "@",
        "slash": "/",
        "quote": '"',
        "dollar": "$",
        "underscore": "_",
        "percent": "%",
        "caret": "^",
        "asterisk": "*",
        "plus": "+",
        "equals": "=",
        "less": "<",
        "greater": ">",
        "lbracket": "[",
        "rbracket": "]",
        "lbrace": "{",
        "rbrace": "}",
        "pipe": "|",
        "backtick": "`",
        "tilde": "~",
        "backslash": "\\",
    }
    for key, ch in _PUNCT_MAP.items():
        if working == key or working.startswith(key + "_"):
            return ch

    if working.startswith("upper_"):
        rest = working[len("upper_"):]
        parts = rest.split("_")
        if parts and len(parts[0]) == 1:
            return parts[0]
        return None
    if working.startswith("digit_"):
        rest = working[len("digit_"):]
        parts = rest.split("_")
        if parts and parts[0].isdigit():
            return parts[0]
        return None
    parts = working.split("_")
    if parts and len(parts[0]) == 1:
        return parts[0]
    # Multi-char bigram/trigram: lowercase alpha-only prefix before the _N suffix
    if len(parts) >= 2 and parts[-1].isdigit() and parts[0].isalpha() and parts[0].islower():
        return parts[0]
    return None


def load_profile_glyphs(profile_dir, fallback_dummy=False):
    """Load glyph PNGs from profiles/freeform_vishnu/glyphs/ directory.

    Filename conventions:
      a_0.png        -> 'a'
      upper_P_0.png  -> 'P'
      digit_0_0.png  -> '0'

    Args:
        profile_dir: Path to profile directory (e.g. 'profiles/freeform_vishnu')
        fallback_dummy: merge dummy bank for chars not in real set (default False)

    Returns:
        dict: {char: [PIL.Image (RGBA), ...]}
    """
    profile_dir = Path(profile_dir)
    glyphs_dir = profile_dir / "glyphs"

    bank = {}

    if not glyphs_dir.exists():
        print(f"[glyph_loader] WARNING: {glyphs_dir} not found")
    else:
        raw_bank: dict = {}
        for png_path in sorted(glyphs_dir.glob("*.png")):
            char = _parse_glyph_stem(png_path.stem)
            if char is None:
                continue
            try:
                img = Image.open(png_path)
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                img = _normalize_alpha(img.copy())
                img = _autocrop_glyph(img)
            except Exception as e:
                print(f"[glyph_loader] Failed to load {png_path.name}: {e}")
                continue
            raw_bank.setdefault(char, []).append(img)

        total_rejected = 0
        total_good_count = 0
        total_warnings_skipped = 0
        for char, variants in raw_bank.items():
            valid = [v for v in variants if _is_valid_glyph(v, char)]
            rejected = len(variants) - len(valid)
            total_rejected += rejected

            good = [v for v in valid if _ink_count(v) >= 150]
            warn = [v for v in valid if _ink_count(v) < 150]

            if good:
                bank[char] = good
                total_good_count += len(good)
                total_warnings_skipped += len(warn)
            elif warn:
                bank[char] = [max(warn, key=_ink_count)]
            elif variants:
                bank[char] = [max(variants, key=_ink_count)]

        print(f"[glyph_loader] Loaded {profile_dir.name}: {total_good_count} good, {total_warnings_skipped} skipped")

        for char in bank:
            bank[char] = [_apply_ink_pooling(g) for g in bank[char]]

        # Stroke-width normalization DISABLED — dilation makes thin glyphs
        # look artificial. The real fix is larger template cells (v5).
        # bank = _normalize_stroke_widths(bank)

        # Log missing standard characters so the renderer knows to skip them
        standard = (
            list('abcdefghijklmnopqrstuvwxyz') +
            list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') +
            list('0123456789') +
            list('.,!?\'"-(: ;/@&#$'.replace(' ', ''))
        )
        for ch in standard:
            if ch not in bank:
                print(f"[glyph_loader] Skipping character '{ch}' — no glyph available")

    if fallback_dummy:
        dummy = create_dummy_glyph_bank()
        for char, variants in dummy.items():
            if char not in bank:
                bank[char] = variants

    return bank


def generate_fallback_glyphs(profile_dir):
    """Generate fallback glyphs for missing uppercase letters, digits, and punctuation.

    Args:
        profile_dir: Path (or str) to profile directory, e.g. 'profiles/freeform_vishnu'
    """
    profile_dir = Path(profile_dir)
    glyphs_dir = profile_dir / "glyphs"
    glyphs_dir.mkdir(parents=True, exist_ok=True)

    # Discover what characters already exist
    existing_chars = set()
    for png_path in glyphs_dir.glob("*.png"):
        ch = _parse_glyph_stem(png_path.stem)
        if ch is not None:
            existing_chars.add(ch)

    print(f"[generate_fallback_glyphs] Existing chars: {sorted(existing_chars)}")

    # ------------------------------------------------------------------ #
    # 1. Uppercase letters: scale corresponding lowercase glyph to 130%   #
    # ------------------------------------------------------------------ #
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if letter in existing_chars:
            continue
        lower = letter.lower()
        # Find any lowercase variant
        candidates = sorted(glyphs_dir.glob(f"{lower}_*.png"))
        if not candidates:
            print(f"[generate_fallback_glyphs] No lowercase '{lower}' found, skipping '{letter}'")
            continue
        src_path = candidates[0]
        try:
            img = Image.open(src_path)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img = _normalize_alpha(img.copy())
            w, h = img.size
            new_h = int(h * 1.30)
            new_w = int(w * 1.30)
            scaled = img.resize((new_w, new_h), Image.LANCZOS)
            out_path = glyphs_dir / f"upper_{letter}_fallback.png"
            scaled.save(out_path)
            print(f"[generate_fallback_glyphs] Created {out_path.name}")
        except Exception as e:
            print(f"[generate_fallback_glyphs] Error creating fallback for '{letter}': {e}")

    # ------------------------------------------------------------------ #
    # 2. Digits 0-9: draw simple shapes                                   #
    # ------------------------------------------------------------------ #
    INK = (51, 51, 51, 220)   # dark gray, alpha 220  (#333333 a=220)
    W, H = 80, 128
    LW = 8  # line width for outlines

    def _new_canvas():
        return Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def _draw_digit(digit_char):
        img = _new_canvas()
        d = ImageDraw.Draw(img)
        pad = 10
        cx = W // 2
        n = digit_char

        if n == "0":
            d.ellipse([pad, pad, W - pad, H - pad], outline=INK, width=LW)

        elif n == "1":
            x = cx + 5
            d.line([(x, pad), (x, H - pad)], fill=INK, width=LW)

        elif n == "2":
            # Arc at top
            d.arc([pad, pad, W - pad, H // 2], start=200, end=360, fill=INK, width=LW)
            # Diagonal down-left
            d.line([(W - pad, H // 2), (pad, H - pad)], fill=INK, width=LW)
            # Horizontal bottom
            d.line([(pad, H - pad), (W - pad, H - pad)], fill=INK, width=LW)

        elif n == "3":
            # Top arc (right-opening)
            d.arc([pad, pad, W - pad, H // 2 + 5], start=210, end=510, fill=INK, width=LW)
            # Bottom arc (right-opening)
            d.arc([pad, H // 2 - 5, W - pad, H - pad], start=210, end=510, fill=INK, width=LW)

        elif n == "4":
            # Vertical right stroke
            d.line([(W - pad - 5, pad), (W - pad - 5, H - pad)], fill=INK, width=LW)
            # Horizontal bar at mid
            mid = H // 2
            d.line([(pad, mid), (W - pad, mid)], fill=INK, width=LW)
            # Left diagonal from upper-left down to bar
            d.line([(pad, pad + 10), (pad, mid)], fill=INK, width=LW)

        elif n == "5":
            # Horizontal top
            d.line([(pad, pad), (W - pad, pad)], fill=INK, width=LW)
            # Left vertical upper half
            mid = H // 2
            d.line([(pad, pad), (pad, mid)], fill=INK, width=LW)
            # Horizontal at mid
            d.line([(pad, mid), (W - pad - 5, mid)], fill=INK, width=LW)
            # Right arc lower half
            d.arc([pad, mid, W - pad, H - pad], start=270, end=90, fill=INK, width=LW)

        elif n == "6":
            # Arc open-right at top
            d.arc([pad, pad, W - pad, H // 2 + 10], start=0, end=270, fill=INK, width=LW)
            # Full circle at bottom
            d.ellipse([pad + 5, H // 2 - 5, W - pad - 5, H - pad], outline=INK, width=LW)

        elif n == "7":
            # Horizontal top
            d.line([(pad, pad), (W - pad, pad)], fill=INK, width=LW)
            # Diagonal down-right
            d.line([(W - pad, pad), (pad + 10, H - pad)], fill=INK, width=LW)

        elif n == "8":
            # Upper circle
            d.ellipse([pad + 5, pad, W - pad - 5, H // 2], outline=INK, width=LW)
            # Lower circle (slightly wider)
            d.ellipse([pad, H // 2, W - pad, H - pad], outline=INK, width=LW)

        elif n == "9":
            # Circle at top
            d.ellipse([pad, pad, W - pad, H // 2 + 10], outline=INK, width=LW)
            # Vertical line down from right
            d.line([(W - pad, H // 2), (W - pad, H - pad)], fill=INK, width=LW)

        return img

    for digit in "0123456789":
        if digit in existing_chars:
            continue
        img = _draw_digit(digit)
        out_path = glyphs_dir / f"digit_{digit}_fallback.png"
        img.save(out_path)
        print(f"[generate_fallback_glyphs] Created {out_path.name}")

    # ------------------------------------------------------------------ #
    # 3. Punctuation                                                       #
    # ------------------------------------------------------------------ #
    PUNCT_INK = (51, 51, 51, 220)

    def _draw_period():
        img = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx, cy = 15, 22
        r = 5
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PUNCT_INK)
        return img

    def _draw_comma():
        img = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx, cy = 15, 20
        r = 4
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PUNCT_INK)
        d.line([(cx, cy + r), (cx - 3, cy + r + 8)], fill=PUNCT_INK, width=3)
        return img

    def _draw_exclaim():
        img = Image.new("RGBA", (20, 80), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = 10
        d.rectangle([cx - 3, 5, cx + 3, 50], fill=PUNCT_INK)
        d.ellipse([cx - 4, 60, cx + 4, 68], fill=PUNCT_INK)
        return img

    def _draw_question():
        img = Image.new("RGBA", (50, 80), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.arc([5, 5, 45, 45], start=200, end=360, fill=PUNCT_INK, width=6)
        d.arc([5, 5, 45, 45], start=0, end=90, fill=PUNCT_INK, width=6)
        d.line([(25, 40), (25, 55)], fill=PUNCT_INK, width=6)
        d.ellipse([21, 62, 29, 70], fill=PUNCT_INK)
        return img

    def _draw_apostrophe():
        img = Image.new("RGBA", (20, 30), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([6, 3, 14, 15], fill=PUNCT_INK)
        return img

    def _draw_hyphen():
        img = Image.new("RGBA", (50, 20), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([5, 7, 45, 13], fill=PUNCT_INK)
        return img

    def _draw_colon():
        img = Image.new("RGBA", (20, 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = 4
        cy1 = 20
        d.ellipse([10 - r, cy1 - r, 10 + r, cy1 + r], fill=PUNCT_INK)
        cy2 = 40
        d.ellipse([10 - r, cy2 - r, 10 + r, cy2 + r], fill=PUNCT_INK)
        return img

    def _draw_semicolon():
        img = Image.new("RGBA", (20, 70), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = 4
        cy1 = 22
        d.ellipse([10 - r, cy1 - r, 10 + r, cy1 + r], fill=PUNCT_INK)
        cy2 = 46
        d.ellipse([10 - r, cy2 - r, 10 + r, cy2 + r], fill=PUNCT_INK)
        d.line([(10, cy2 + r), (7, cy2 + r + 7)], fill=PUNCT_INK, width=3)
        return img

    def _draw_lparen():
        img = Image.new("RGBA", (30, 80), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.arc([5, 5, 35, 75], start=300, end=60, fill=PUNCT_INK, width=5)
        return img

    def _draw_rparen():
        img = Image.new("RGBA", (30, 80), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.arc([-5, 5, 25, 75], start=120, end=240, fill=PUNCT_INK, width=5)
        return img

    _PUNCT_GENERATORS = {
        ".": ("period_0.png", _draw_period),
        ",": ("comma_0.png", _draw_comma),
        "!": ("exclaim_0.png", _draw_exclaim),
        "?": ("question_0.png", _draw_question),
        "'": ("apostrophe_0.png", _draw_apostrophe),
        "-": ("hyphen_0.png", _draw_hyphen),
        ":": ("colon_0.png", _draw_colon),
        ";": ("semicolon_0.png", _draw_semicolon),
        "(": ("lparen_0.png", _draw_lparen),
        ")": ("rparen_0.png", _draw_rparen),
    }

    for char, (filename, draw_fn) in _PUNCT_GENERATORS.items():
        if char in existing_chars:
            continue
        img = draw_fn()
        out_path = glyphs_dir / filename
        img.save(out_path)
        print(f"[generate_fallback_glyphs] Created {out_path.name}")

    print("[generate_fallback_glyphs] Done.")


class GlyphLoader:
    """Loads glyph banks - real or dummy."""

    def __init__(self, real_glyphs_dir="real_glyphs"):
        self.real_glyphs_dir = Path(real_glyphs_dir)
        self.bank = None
        self.glyph_type = None

    def load_real_glyphs(self):
        """Load real extracted glyphs."""
        json_path = self.real_glyphs_dir / "glyph_bank.json"

        if not json_path.exists():
            print(f"  {json_path} not found")
            return None

        try:
            with open(json_path, 'r') as f:
                glyph_map = json.load(f)

            bank = {}
            for char, paths in glyph_map.items():
                bank[char] = []
                for path in paths:
                    try:
                        img = Image.open(path).convert('RGBA')
                        bank[char].append(img)
                    except Exception as e:
                        print(f"  Failed to load {path}: {e}")

            print(f"Loaded {len(bank)} characters from real glyphs")
            self.bank = bank
            self.glyph_type = "real"
            return bank

        except Exception as e:
            print(f"  Error loading real glyphs: {e}")
            return None

    def load_dummy_glyphs(self):
        """Load dummy placeholder glyphs."""
        print("  Using dummy placeholder glyphs (rectangles)")
        self.bank = create_dummy_glyph_bank()
        self.glyph_type = "dummy"
        return self.bank

    def load_best_available(self):
        """Load best available glyph bank (real -> dummy)."""
        real = self.load_real_glyphs()
        if real:
            return real
        print("Falling back to dummy glyphs...")
        return self.load_dummy_glyphs()

    def get_info(self):
        """Get information about loaded glyph bank."""
        if not self.bank:
            return "No glyph bank loaded"

        total_variants = sum(len(v) for v in self.bank.values())
        return {
            'type': self.glyph_type,
            'characters': len(self.bank),
            'total_variants': total_variants,
            'characters_list': sorted(self.bank.keys())
        }

    def has_real_glyphs(self):
        """Check if real glyphs are available."""
        json_path = self.real_glyphs_dir / "glyph_bank.json"
        return json_path.exists()


def load_glyphs(prefer_real=True):
    """
    Convenience function to load glyphs.

    Args:
        prefer_real: If True, try real glyphs first; fallback to dummy

    Returns:
        Glyph bank dictionary
    """
    loader = GlyphLoader()

    if prefer_real:
        return loader.load_best_available()
    else:
        return loader.load_dummy_glyphs()


if __name__ == "__main__":
    from pathlib import Path

    # Generate fallback glyphs for freeform_vishnu profile
    print("=== Generating fallback glyphs ===")
    generate_fallback_glyphs('profiles/freeform_vishnu')

    # Test loader
    print("\n=== Glyph Bank Loader Test ===")
    loader = GlyphLoader()
    print(f"Real glyphs available: {loader.has_real_glyphs()}")
    print("Loading glyphs...")
    bank = loader.load_best_available()
    print("Glyph bank info:")
    info = loader.get_info()
    for key, value in info.items():
        if key != 'characters_list':
            print(f"  {key}: {value}")
    print("Character coverage:")
    print(f"  Lowercase: {sum(1 for c in info['characters_list'] if c.islower())}")
    print(f"  Uppercase: {sum(1 for c in info['characters_list'] if c.isupper())}")
    print(f"  Digits: {sum(1 for c in info['characters_list'] if c.isdigit())}")
    print(f"  Punctuation: {sum(1 for c in info['characters_list'] if not c.isalnum())}")
    print("Loader ready!")
