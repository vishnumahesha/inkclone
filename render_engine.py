import numpy as np
from PIL import Image, ImageDraw
import math
import random

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

    def __init__(self, glyph_bank: dict, seed: int = None):
        self.glyph_bank = glyph_bank
        self.selector = VariantSelector()
        self.rng = random.Random(seed)
        self.np_rng = np.random.RandomState(seed)

    def _get_glyph(self, char: str) -> Image.Image:
        if char == ' ':
            return None

        variants = self.glyph_bank.get(char, [])
        if not variants:
            alt = char.upper() if char.islower() else char.lower()
            variants = self.glyph_bank.get(alt, [])
            if not variants:
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
        """Determine if we should break to next line (avoid orphans)"""
        usable_width = page_width - margin_left - margin_right
        
        # Estimate width of remaining words on this line
        remaining_text = " ".join(words[word_idx:])
        remaining_width = len(remaining_text) * (char_height * 0.6 + inter_letter_mean)
        
        # Break if next word won't fit
        if cursor_x + remaining_width > page_width - margin_right:
            return True
        
        # Avoid single word orphans on new line (break earlier if needed)
        if word_idx + 1 < len(words):
            next_word_width = len(words[word_idx + 1]) * (char_height * 0.6 + inter_letter_mean)
            if next_word_width > usable_width * 0.4:  # Next word takes >40% of line
                # Check if current line is getting crowded
                if cursor_x > margin_left + usable_width * 0.7:
                    return True
        
        return False

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
               neatness: float = 0.5) -> Image.Image:
        """Render text as handwriting with improved features."""
        
        self.selector.reset()
        jitter_factor = 1.5 - neatness
        canvas = Image.new('RGBA', (page_width, page_height), (0, 0, 0, 0))
        words = text.split()
        
        cursor_x = margin_left
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
                    cursor_x = margin_left + self.rng.gauss(0, 3 * jitter_factor)
                    cursor_y += line_height
                    line_idx += 1
            
            if cursor_y + char_height > page_height - 100:
                break
            
            prog = self._page_progression(line_idx, total_lines)
            
            char_idx = 0
            while char_idx < len(word):
                char = word[char_idx]
                
                # Check for ligatures
                ligature, ligature_spacing = self._check_ligature(word, char_idx)
                
                if ligature:
                    # Skip the ligature pair and apply tighter spacing
                    cursor_x += ligature_spacing * prog["spacing_scale"]
                    char_idx += len(ligature)
                    continue
                
                glyph = self._get_glyph(char)
                if glyph is None:
                    cursor_x += char_height * 0.3
                    char_idx += 1
                    continue
                
                # Scale glyph
                scale = (char_height / max(glyph.height, 1)) * prog["size_scale"]
                scale *= (1.0 + self.rng.uniform(-scale_variance, scale_variance) * jitter_factor)
                new_w = max(1, int(glyph.width * scale))
                new_h = max(1, int(glyph.height * scale))
                glyph = glyph.resize((new_w, new_h), Image.LANCZOS)
                
                # Apply ink darkness
                arr = np.array(glyph)
                arr[:, :, 3] = (arr[:, :, 3] * ink_darkness).astype(np.uint8)
                glyph = Image.fromarray(arr)
                
                # Position with jitter and baseline drift
                jx = self.rng.gauss(0, inter_letter_std * jitter_factor) if char_idx > 0 else 0
                jy = self.rng.gauss(0, 1.0 * jitter_factor)
                baseline = self._baseline_drift(cursor_x, line_idx, baseline_amplitude * jitter_factor)
                
                x = int(cursor_x + jx)
                y = int(cursor_y + baseline + jy)
                
                # Apply rotation
                angle = self.rng.uniform(-rotation_max_deg, rotation_max_deg) * jitter_factor
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
                
                # Advance cursor
                cursor_x += new_w + inter_letter_mean * prog["spacing_scale"]
                cursor_x += self.rng.gauss(0, inter_letter_std * jitter_factor * 0.5)
                
                char_idx += 1
            
            # Word spacing
            word_gap = self.rng.gauss(inter_word_mean, inter_word_std * jitter_factor)
            cursor_x += max(5, word_gap) * prog["spacing_scale"]
        
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
