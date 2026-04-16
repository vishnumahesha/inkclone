import numpy as np
from PIL import Image, ImageDraw
import math
import random
import os
import warnings

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

    def _smart_line_break(self, words: list, word_idx: int, cursor_x: int,
                         page_width: int, margin_right: int, margin_left: int,
                         char_height: int, inter_letter_mean: float) -> bool:
        """Break to next line when the current word won't fit."""
        avg_char_w = char_height * 0.55 * 1.1 + inter_letter_mean
        avg_word_gap = char_height * 0.55 * 2.5
        word_width = len(words[word_idx]) * avg_char_w + avg_word_gap
        return cursor_x + word_width > page_width - margin_right

    def render(self, text: str,
               page_width: int = 2400,
               page_height: int = 3200,
               margin_left: int = 220,
               margin_right: int = 100,
               margin_top: int = 150,
               line_height: int = 85,
               char_height: int = 50,
               inter_letter_mean: float = 3.0,
               inter_letter_std: float = 2.0,
               inter_word_mean: float = 22.0,
               inter_word_std: float = 5.0,
               baseline_amplitude: float = 2.0,
               rotation_max_deg: float = 1.5,
               scale_variance: float = 0.03,
               ink_darkness: float = 0.85,
               neatness: float = 0.5,
               baseline_y_positions: list = None,
               margin_left_x: int = None) -> Image.Image:
        """Render text as handwriting with improved features."""
        if margin_left_x is not None:
            margin_left = margin_left_x

        self.selector.reset()
        jitter_factor = 1.0 - neatness  # 0.0 = perfectly neat, 1.0 = maximum mess
        canvas = Image.new('RGBA', (page_width, page_height), (0, 0, 0, 0))
        words = text.split()

        # 3a: compute normalization scale from median ink height
        norm_scale = self._compute_norm_scale(char_height)

        # Estimate avg ink width for word spacing
        avg_ink_width = int(char_height * 0.55)

        cursor_x = margin_left
        # 3e: snap starting y to first rule line if provided
        if baseline_y_positions:
            cursor_y = baseline_y_positions[0] if baseline_y_positions else margin_top
        else:
            cursor_y = margin_top
        line_idx = 0
        usable_width = page_width - margin_left - margin_right

        avg_char_width = char_height * 0.6
        chars_per_line = usable_width / (avg_char_width + inter_letter_mean)
        total_lines = max(1, len(text) / chars_per_line)
        
        for word_i, word in enumerate(words):
            word_width = len(word) * (char_height * 0.6 + inter_letter_mean)
            
            # Smart line breaking
            if self._smart_line_break(words, word_i, cursor_x, page_width, margin_right,
                                     margin_left, char_height, inter_letter_mean):
                if cursor_x > margin_left + 50:
                    cursor_x = margin_left + self.rng.gauss(0, 8.0 * jitter_factor)
                    line_idx += 1
                    # 3e: snap to rule line
                    if baseline_y_positions and line_idx < len(baseline_y_positions):
                        cursor_y = baseline_y_positions[line_idx]
                    else:
                        cursor_y += line_height
            
            if cursor_y + char_height > page_height - 100:
                break
            
            prog = self._page_progression(line_idx, total_lines)
            
            char_idx = 0
            while char_idx < len(word):
                char = word[char_idx]
                
                # Check for ligatures — tighten spacing but still render both chars
                _, ligature_spacing = self._check_ligature(word, char_idx)
                if ligature_spacing != 0:
                    cursor_x += ligature_spacing * prog["spacing_scale"]

                glyph = self._get_glyph(char)
                if glyph is None:
                    cursor_x += char_height * 0.3
                    char_idx += 1
                    continue
                
                # 3a: Scale using normalized scale (ink-height-based)
                scale = norm_scale * prog["size_scale"]
                scale *= (1.0 + self.rng.uniform(-0.15, 0.15) * jitter_factor)
                new_w = max(1, int(glyph.width * scale))
                new_h = max(1, int(glyph.height * scale))
                glyph = glyph.resize((new_w, new_h), Image.LANCZOS)

                # Apply ink darkness
                arr = np.array(glyph)
                arr[:, :, 3] = (arr[:, :, 3] * ink_darkness).astype(np.uint8)
                glyph = Image.fromarray(arr)

                jx = self.rng.gauss(0, 5.0 * jitter_factor) if char_idx > 0 else 0
                jy = self.rng.gauss(0, 4.0 * jitter_factor)
                baseline = self._baseline_drift(cursor_x, line_idx, 6.0 * jitter_factor)

                # 3c: Align ink bottom to cursor_y (baseline alignment)
                bbox = self._get_ink_bbox(glyph)
                if bbox:
                    ink_bottom = bbox[3]
                    descender = char.lower() in 'gjpqy'
                    descend_offset = int(char_height * 0.25) if descender else 0
                    y_offset = new_h - ink_bottom + descend_offset
                    y = int(cursor_y - y_offset + baseline + jy)
                else:
                    y = int(cursor_y + baseline + jy)

                x = int(cursor_x + jx)

                angle = self.rng.uniform(-8.0, 8.0) * jitter_factor
                if abs(angle) > 0.1:
                    glyph = glyph.rotate(angle, expand=True, resample=Image.BICUBIC,
                                       fillcolor=(0, 0, 0, 0))

                # Paste glyph
                if 0 <= x < page_width and 0 <= y < page_height:
                    paste_x = max(0, x)
                    paste_y = max(0, y)
                    canvas.paste(glyph, (paste_x, paste_y), glyph)

                    # Add i-dot/t-cross for specific characters
                    if char.lower() in 'it':
                        self._add_i_dot(canvas, paste_x + new_w // 2, paste_y, char_height, jitter_factor)

                cursor_x += new_w * 1.1 + self.rng.gauss(0, 4.0 * jitter_factor)
                
                char_idx += 1
            
            # 3b: Word spacing proportional to avg ink width
            word_gap = avg_ink_width * 2.5 + self.rng.gauss(0, 4.0 * jitter_factor)
            cursor_x += max(avg_ink_width, word_gap) * prog["spacing_scale"]
        
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
