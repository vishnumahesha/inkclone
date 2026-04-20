import numpy as np
from PIL import Image, ImageDraw
import math
import random
import os
import warnings

try:
    from variant_selector import QualityWeightedVariantSelector, find_bigram
    from kerning import get_kern_adjustment
    _HAS_ADVANCED_MODULES = True
except ImportError:
    _HAS_ADVANCED_MODULES = False

# Common ligatures and their spacing adjustments
LIGATURES = {
    "th": -3,  # Tighter spacing
    "he": -2,
    "in": -2,
    "an": -1,
    "on": -1,
    "en": -1,
    "er": -1,
    "re": -2,
    "ed": -1,
}

class VariantSelector:
    """Tracks which variant to use next for each character."""

    def __init__(self):
        self.counters = {}
        self.last_used = {}

    def select(self, char: str, num_variants: int) -> int:
        if num_variants <= 0:
            return 0
        if num_variants == 1:
            return 0

        if char not in self.counters:
            self.counters[char] = 0

        idx = self.counters[char] % num_variants

        if char in self.last_used and idx == self.last_used[char] and num_variants > 1:
            idx = (idx + 1) % num_variants

        self.last_used[char] = idx
        self.counters[char] = idx + 1
        return idx

    def reset(self):
        self.counters.clear()
        self.last_used.clear()


class HandwritingRenderer:
    """Renders typed text as a handwriting image using a glyph bank."""

    @classmethod
    def from_profile(cls, profile_id: str, seed: int = None,
                     fallback_dummy: bool = True) -> "HandwritingRenderer":
        """
        Create a HandwritingRenderer from a named profile.

        Loads the canonical profile.json, validates it, extracts style_metrics
        for default render parameters, and builds the glyph bank.

        Args:
            profile_id: Profile directory name, e.g. "freeform_vishnu".
            seed: Random seed for reproducible rendering.
            fallback_dummy: If True, missing glyphs fall back to dummy shapes.

        Returns:
            HandwritingRenderer with glyph_bank and profile_style populated.

        Raises:
            FileNotFoundError: If profile does not exist or lacks profile.json.
            ValueError: If profile fails schema validation.
        """
        try:
            from profiles.loader import load_profile, load_profile_glyphs_from_schema
        except ImportError:
            raise ImportError(
                "profiles.loader not importable. Ensure the project root is in "
                "sys.path and profiles/loader.py exists."
            )

        print(f"[HandwritingRenderer] Loading profile: {profile_id}")
        profile = load_profile(profile_id)   # raises loudly on invalid

        bank = load_profile_glyphs_from_schema(profile)
        if not bank:
            raise ValueError(
                f"Profile '{profile_id}' loaded but produced an empty glyph bank. "
                f"Check that variant paths in profile.json resolve to existing files."
            )

        n_chars = len(bank)
        n_variants = sum(len(v) for v in bank.values())
        print(f"[HandwritingRenderer] Loaded {n_chars} chars, {n_variants} variants "
              f"from profile '{profile_id}'")

        if fallback_dummy:
            dummy = create_dummy_glyph_bank()
            n_added = 0
            for ch, variants in dummy.items():
                if ch not in bank:
                    bank[ch] = variants
                    n_added += 1
            if n_added:
                print(f"[HandwritingRenderer] Added {n_added} dummy fallback chars")

        renderer = cls(bank, seed=seed)
        renderer.profile_id = profile_id
        renderer.profile_style = profile.get("style_metrics", {})
        renderer.profile = profile

        usable = profile.get("usable", False)
        if not usable:
            warnings.warn(
                f"Profile '{profile_id}' is marked usable=False "
                f"(character coverage below threshold). Rendering may have gaps.",
                UserWarning,
                stacklevel=2,
            )

        return renderer

    def _render_kwargs_from_profile(self, **overrides) -> dict:
        """
        Build render() keyword arguments seeded from profile style_metrics.
        Any explicit override keyword takes priority.

        Returns dict suitable for **kwargs in render().
        """
        sm = getattr(self, "profile_style", {})
        meta_layout = {}
        if hasattr(self, "profile"):
            old_meta_path = (
                __import__("pathlib").Path(__file__).parent
                / "profiles" / self.profile_id / "metadata.json"
            )
            if old_meta_path.exists():
                import json as _json
                try:
                    old = _json.loads(old_meta_path.read_text())
                    meta_layout = old.get("layout", {})
                except Exception:
                    pass

        kwargs = {}

        # char_height from median x_height (scaled to render canvas)
        x_height = sm.get("median_x_height") or meta_layout.get("x_height_px") or 50
        # x_height in profiles is at 128px canonical; scale to ~50px render height
        if x_height > 80:
            x_height = round(x_height * 50 / 128)
        kwargs["char_height"] = int(x_height) or 50

        # inter-letter spacing
        kwargs["inter_letter_mean"] = meta_layout.get("inter_letter_gap_mean", 3.0)
        kwargs["inter_letter_std"]  = meta_layout.get("inter_letter_gap_std",  2.0)

        # inter-word spacing
        kwargs["inter_word_mean"] = meta_layout.get("inter_word_gap_mean", 22.0)
        kwargs["inter_word_std"]  = meta_layout.get("inter_word_gap_std",  5.0)

        # baseline drift
        kwargs["baseline_amplitude"] = meta_layout.get("baseline_drift_amplitude", 2.0)

        # slant → rotation
        slant = sm.get("slant_estimate_degrees", 0.0)
        kwargs["rotation_max_deg"] = min(3.0, max(0.5, abs(slant) + 1.0))

        # Apply any caller overrides
        kwargs.update(overrides)
        return kwargs

    def __init__(self, glyph_bank: dict, seed: int = None):
        self.glyph_bank = glyph_bank
        if _HAS_ADVANCED_MODULES:
            self.selector = QualityWeightedVariantSelector(seed=seed)
        else:
            self.selector = VariantSelector()
        self.rng = random.Random(seed)
        self.np_rng = np.random.RandomState(seed)

    def _get_ink_bbox(self, img: Image.Image):
        """Return tight bounding box (x0,y0,x1,y1) around non-transparent pixels, or None."""
        arr = np.array(img)
        alpha = arr[:, :, 3]
        rows = np.any(alpha > 10, axis=1)
        cols = np.any(alpha > 10, axis=0)
        if not rows.any():
            return None
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        return (int(cmin), int(rmin), int(cmax + 1), int(rmax + 1))

    def _compute_norm_scale(self, char_height: int) -> float:
        """Compute scale factor so median ink height matches char_height."""
        ink_heights = []
        for variants in self.glyph_bank.values():
            for g in variants[:1]:
                bbox = self._get_ink_bbox(g)
                if bbox:
                    ink_heights.append(bbox[3] - bbox[1])
        if not ink_heights:
            return 1.0
        median_ink_h = float(np.median(ink_heights))
        return char_height / median_ink_h if median_ink_h > 0 else 1.0

    def _get_glyph(self, char: str) -> Image.Image:
        if char == ' ':
            return None

        variants = self.glyph_bank.get(char, [])
        if not variants:
            alt = char.upper() if char.islower() else char.lower()
            variants = self.glyph_bank.get(alt, [])
            if not variants:
                # Log missing glyph at most once per character per renderer
                if not hasattr(self, "_missing_logged"):
                    self._missing_logged = set()
                if char not in self._missing_logged:
                    print(f"[HandwritingRenderer] FALLBACK: no glyph for '{char}' "
                          f"(profile={getattr(self, 'profile_id', 'unknown')})")
                    self._missing_logged.add(char)
                return None

        idx = self.selector.select(char, len(variants))
        return variants[idx].copy()

    def _baseline_drift(self, x: float, line_idx: int,
                        amplitude: float = 2.0, frequency: float = 0.003) -> float:
        phase1 = line_idx * 1.7
        phase2 = line_idx * 3.1
        drift = amplitude * math.sin(2 * math.pi * frequency * x + phase1)
        drift += amplitude * 0.5 * math.sin(2 * math.pi * frequency * 1.7 * x + phase2)
        return drift

    def _page_progression(self, line_idx: int, total_lines: int) -> dict:
        progress = line_idx / max(total_lines, 1)
        return {
            "jitter_scale": 1.0 + progress * 0.3,
            "spacing_scale": 1.0 - progress * 0.05,
            "size_scale": 1.0 - progress * 0.03,
        }

    def _check_ligature(self, text: str, pos: int) -> tuple:
        """Check if current position starts a ligature. Returns (ligature_str, spacing_adjustment) or (None, 0)"""
        for ligature_pair in sorted(LIGATURES.keys(), key=len, reverse=True):
            if pos + len(ligature_pair) <= len(text):
                substring = text[pos:pos+len(ligature_pair)].lower()
                if substring == ligature_pair:
                    return ligature_pair, LIGATURES[ligature_pair]
        return None, 0

    def _add_i_dot(self, canvas: Image.Image, x: int, y: int, char_height: int, jitter_factor: float):
        """Add i-dot or t-cross with random offset for realism"""
        if char_height < 30:
            return
        
        dot_size = max(2, char_height // 20)
        dot_x = int(x + self.rng.uniform(-1, 1) * jitter_factor)
        dot_y = int(y - char_height * 0.7 + self.rng.uniform(-1.5, 1.5) * jitter_factor)
        
        draw = ImageDraw.Draw(canvas)
        draw.ellipse(
            [(dot_x - dot_size, dot_y - dot_size),
             (dot_x + dot_size, dot_y + dot_size)],
            fill=(0, 0, 0, 180)
        )

    def _compute_avg_ink_width(self, norm_scale: float) -> float:
        """Compute average scaled ink width across the glyph bank."""
        widths = []
        for variants in self.glyph_bank.values():
            for g in variants[:1]:
                bbox = self._get_ink_bbox(g)
                if bbox:
                    widths.append(bbox[2] - bbox[0])
        if not widths:
            return 0.0
        return float(np.median(widths)) * norm_scale

    def _peek_word_width(self, word: str, char_height: int, inter_letter_mean: float) -> int:
        """Estimate word pixel width without advancing the variant selector."""
        total_w = 0
        for char in word:
            variants = self.glyph_bank.get(char, [])
            if not variants:
                alt = char.upper() if char.islower() else char.lower()
                variants = self.glyph_bank.get(alt, [])
            if variants:
                target_h = char_height
                if char.isupper() or char in 'bdfhklt':
                    target_h = int(char_height * 1.4)
                max_w = max(
                    min(max(1, int(g.width * (target_h / max(g.height, 1)))), char_height * 3)
                    for g in variants
                )
                total_w += max_w + int(inter_letter_mean)
            else:
                total_w += int(char_height * 0.3)
        return total_w

    def _smart_line_break(self, words: list, word_idx: int, cursor_x: int,
                         page_width: int, margin_right: int, margin_left: int,
                         char_height: int, inter_letter_mean: float,
                         avg_char_width: float = None) -> bool:
        """Break to next line when the current word won't fit."""
        if avg_char_width is None:
            avg_char_width = char_height * 0.55
        word_width = len(words[word_idx]) * (avg_char_width + 2) + avg_char_width * 2.0
        return cursor_x + word_width > page_width - margin_right

    def render(self, text: str,
               page_width: int = 2400,
               page_height: int = 3200,
               margin_left: int = 206,
               margin_right: int = 100,
               margin_top: int = 150,
               line_height: int = 42,
               char_height: int = 25,
               inter_letter_mean: float = 1.0,
               inter_letter_std: float = 2.0,
               inter_word_mean: float = 17.0,
               inter_word_std: float = 5.0,
               baseline_amplitude: float = 2.0,
               rotation_max_deg: float = 1.5,
               scale_variance: float = 0.03,
               ink_darkness: float = 0.85,
               neatness: float = 0.5,
               baseline_y_positions: list = None,
               margin_left_x: int = None,
               # realism_v2 params — None means fall back to legacy equivalents
               slant_deg: float = 0.0,
               baseline_wander_px: float = None,
               margin_drift_px: float = 0.0,
               line_end_cramming: float = 1.0,
               size_jitter: float = None,
               spacing_jitter: float = None,
               angle_jitter_deg: float = None,
               pressure_range: float = 0.0,
               fatigue_factor: float = 0.0,
               ink_fade: float = 0.0,
               bleed_radius: float = 0.0,
               line_spacing_mult: float = 1.0,
               stroke_thickness: int = 0) -> Image.Image:
        """Render text as handwriting."""
        if margin_left_x is not None:
            margin_left = margin_left_x

        self.selector.reset()
        jitter_factor = 1.0 - neatness

        # Use realism_v2 params if provided, else fall back to legacy equivalents
        _bwander  = baseline_wander_px if baseline_wander_px is not None else baseline_amplitude
        _szjitter = size_jitter        if size_jitter        is not None else scale_variance
        _spjitter = spacing_jitter     if spacing_jitter     is not None else inter_letter_std
        _ajitter  = angle_jitter_deg   if angle_jitter_deg   is not None else rotation_max_deg

        canvas = Image.new('RGBA', (page_width, page_height), (0, 0, 0, 0))
        words = text.split()

        norm_scale    = self._compute_norm_scale(char_height)
        avg_ink_width = int(self._compute_avg_ink_width(norm_scale)) or int(char_height * 0.55)

        cursor_x = margin_left
        cursor_y = baseline_y_positions[0] if baseline_y_positions else margin_top
        line_idx = 0
        usable_width = page_width - margin_left - margin_right

        chars_per_line = usable_width / (avg_ink_width + 2)
        total_lines    = max(1, len(text) / chars_per_line)
        right_edge     = page_width - margin_left
        crammed_start  = margin_left + 0.65 * (right_edge - margin_left)

        for word_i, word in enumerate(words):
            # Estimate word pixel width without advancing the variant selector
            word_pixel_width = self._peek_word_width(word, char_height, inter_letter_mean)

            # Wrap BEFORE placing this word if it won't fit on the current line
            if cursor_x + word_pixel_width > right_edge and cursor_x > margin_left + 50:
                margin_jitter = self.rng.uniform(-margin_drift_px, margin_drift_px) if margin_drift_px > 0 else 0
                cursor_x   = margin_left + margin_jitter + self.rng.gauss(0, 2.0 * jitter_factor)
                line_idx  += 1
                if baseline_y_positions and line_idx < len(baseline_y_positions):
                    cursor_y = baseline_y_positions[line_idx]
                else:
                    cursor_y += int(line_height * line_spacing_mult)

            # Stop if we've gone past the bottom of the page
            if cursor_y + char_height > page_height - margin_top:
                break

            prog = self._page_progression(line_idx, total_lines)

            char_idx = 0
            while char_idx < len(word):
                if _HAS_ADVANCED_MODULES:
                    bigram_match = find_bigram(word, char_idx, self.glyph_bank)
                    if bigram_match is not None:
                        char, char_step = bigram_match
                    else:
                        char, char_step = word[char_idx], 1
                else:
                    char, char_step = word[char_idx], 1

                _, ligature_spacing = self._check_ligature(word, char_idx)
                if ligature_spacing != 0:
                    cursor_x += ligature_spacing * prog["spacing_scale"]

                glyph = self._get_glyph(char)
                if glyph is None:
                    cursor_x += char_height * 0.3
                    char_idx += char_step
                    continue

                # Scale to target height: ascenders/uppercase 40% taller
                target_h = char_height
                if char.isupper() or char in 'bdfhklt':
                    target_h = int(char_height * 1.4)
                scale = target_h / max(glyph.height, 1)
                new_w = max(1, min(int(glyph.width * scale), char_height * 3))
                glyph = glyph.resize((new_w, target_h), Image.LANCZOS)
                new_h = target_h

                # Fatigue scale increases toward bottom of page
                fatigue_scale = 1.0 + fatigue_factor * min(1.0, cursor_y / max(page_height, 1))

                # Optional size jitter: uniform scale per glyph
                if _szjitter > 0:
                    sj    = 1.0 + self.rng.uniform(-_szjitter, _szjitter) * fatigue_scale
                    new_w = max(1, int(new_w * sj))
                    new_h = max(1, int(new_h * sj))
                    glyph = glyph.resize((new_w, new_h), Image.LANCZOS)

                # Alpha: ink darkness + pressure variation + fade
                arr        = np.array(glyph)
                alpha_mult = ink_darkness
                if pressure_range > 0:
                    alpha_mult *= max(0.35, 1.0 - self.rng.uniform(0, pressure_range) * fatigue_scale)
                if ink_fade > 0:
                    alpha_mult *= max(0.25, 1.0 - ink_fade * cursor_y / max(page_height, 1))
                arr[:, :, 3] = np.clip(arr[:, :, 3] * alpha_mult, 0, 255).astype(np.uint8)

                if stroke_thickness != 0:
                    import cv2 as _cv2
                    kernel = np.ones((2, 2), np.uint8)
                    alpha_ch = arr[:, :, 3]
                    if stroke_thickness > 0:
                        alpha_ch = _cv2.dilate(alpha_ch, kernel, iterations=stroke_thickness)
                    else:
                        alpha_ch = _cv2.erode(alpha_ch, kernel, iterations=abs(stroke_thickness))
                    arr[:, :, 3] = alpha_ch

                glyph = Image.fromarray(arr)

                jx       = self.rng.gauss(0, 2.0 * jitter_factor) if char_idx > 0 else 0
                jy       = self.rng.gauss(0, 2.0 * jitter_factor)
                baseline = self._baseline_drift(cursor_x, line_idx, _bwander * fatigue_scale)

                # Baseline: glyph bottom sits ON ruled line; descenders hang below
                if char in 'gjpqy':
                    y = int(cursor_y - new_h + int(char_height * 0.22) + baseline + jy)
                else:
                    y = int(cursor_y - new_h + baseline + jy)

                x     = int(cursor_x + jx)
                angle = self.rng.uniform(-_ajitter, _ajitter) * fatigue_scale + slant_deg
                if abs(angle) > 0.1:
                    glyph = glyph.rotate(angle, expand=True, resample=Image.BICUBIC,
                                       fillcolor=(0, 0, 0, 0))

                if 0 <= x < page_width and 0 <= y < page_height:
                    paste_x = max(0, x)
                    paste_y = max(0, y)
                    canvas.paste(glyph, (paste_x, paste_y), glyph)
                    if char.lower() in 'it':
                        self._add_i_dot(canvas, paste_x + new_w // 2, paste_y, char_height, jitter_factor)

                # Advance cursor: ink width + letter gap with cramming near right margin
                next_char  = word[char_idx + char_step] if (char_idx + char_step) < len(word) else None
                kern_adj   = (get_kern_adjustment(char[-1], next_char)
                              if (_HAS_ADVANCED_MODULES and next_char) else 1.0)
                letter_gap = (inter_letter_mean + self.rng.gauss(0, _spjitter * fatigue_scale)) * kern_adj
                if cursor_x > crammed_start and line_end_cramming < 1.0:
                    cramp      = min(1.0, (cursor_x - crammed_start) / max(1, right_edge - crammed_start))
                    letter_gap *= 1.0 - (1.0 - line_end_cramming) * cramp
                adv_bbox   = self._get_ink_bbox(glyph)
                advance_w  = (adv_bbox[2] - adv_bbox[0]) if adv_bbox else new_w
                cursor_x  += advance_w + letter_gap
                char_idx  += char_step

            # Word spacing
            word_gap = inter_word_mean + self.rng.gauss(0, inter_word_std * jitter_factor)
            if cursor_x > crammed_start and line_end_cramming < 1.0:
                cramp     = min(1.0, (cursor_x - crammed_start) / max(1, right_edge - crammed_start))
                word_gap *= 1.0 - (1.0 - line_end_cramming) * cramp
            cursor_x += word_gap * prog["spacing_scale"]

        # Ink bleed: Gaussian blur on alpha channel
        if bleed_radius > 0:
            from PIL import ImageFilter
            arr       = np.array(canvas)
            alpha_img = Image.fromarray(arr[:, :, 3])
            alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=bleed_radius))
            arr[:, :, 3] = np.array(alpha_img)
            canvas    = Image.fromarray(arr, 'RGBA')

        return canvas


def create_dummy_glyph_bank():
    """Create a bank of dummy glyphs for testing."""
    bank = {}

    for i, char in enumerate("abcdefghijklmnopqrstuvwxyz"):
        variants = []
        for v in range(3):
            w = 25 + v * 3 + (i % 5)
            h = 40 + v * 2
            arr = np.zeros((h, w, 4), dtype=np.uint8)
            shade = 30 + v * 15
            arr[3:-3, 3:-3, 0] = shade
            arr[3:-3, 3:-3, 1] = shade
            arr[3:-3, 3:-3, 2] = shade
            arr[3:-3, 3:-3, 3] = 200 + v * 15
            mark_y = 5 + v * 8
            arr[mark_y:mark_y+3, 5:8, :3] = 0
            arr[mark_y:mark_y+3, 5:8, 3] = 255
            variants.append(Image.fromarray(arr, 'RGBA'))
        bank[char] = variants

    for i, char in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        variants = []
        for v in range(2):
            w = 35 + v * 3
            h = 55 + v * 2
            arr = np.zeros((h, w, 4), dtype=np.uint8)
            arr[3:-3, 3:-3, :3] = 25 + v * 10
            arr[3:-3, 3:-3, 3] = 210
            variants.append(Image.fromarray(arr, 'RGBA'))
        bank[char] = variants

    for char in ".,!?'-:;":
        arr = np.zeros((15, 8, 4), dtype=np.uint8)
        arr[3:-3, 2:-2, :3] = 20
        arr[3:-3, 2:-2, 3] = 230
        bank[char] = [Image.fromarray(arr, 'RGBA')]

    return bank


if __name__ == "__main__":
    print("Testing improved HandwritingRenderer...")

    bank = create_dummy_glyph_bank()
    
    # Test with ligature-rich text
    renderer = HandwritingRenderer(bank, seed=42)
    text = "the quick brown fox jumps over the lazy dog"
    img = renderer.render(text)
    img.save("output/improvements/render_improved.png")
    print(f"✅ Rendered improved: {img.size}")
    
    alpha = np.array(img)[:, :, 3]
    assert alpha.sum() > 0, "Should have rendered some ink"
    print(f"   Ink pixels: {(alpha > 0).sum()}")
    
    print("\n✅ All render improvements tested!")
