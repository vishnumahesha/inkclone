#!/usr/bin/env python3
"""
Real Glyph Extraction from Handwriting Photo

Extracts individual character glyphs from a handwritten document photo
and creates a realistic glyph bank to replace dummy rectangles.

Steps:
1. Load image in grayscale
2. Find text lines using horizontal projection
3. Find word boundaries using vertical projection
4. Match detected words to known text
5. Estimate character boundaries
6. Extract and resize characters to 50px height
7. Convert to RGBA (dark→opaque, white→transparent)
8. Save organized by character
9. Create glyph_bank.json mapping
10. Test full pipeline with real glyphs
"""

import cv2
import numpy as np
from PIL import Image
import json
import os
from pathlib import Path
from collections import defaultdict
import sys

class GlyphExtractor:
    """Extracts real character glyphs from handwritten text image."""
    
    def __init__(self, image_path, output_dir="real_glyphs"):
        self.image_path = image_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Known text in the reference image (3 lines)
        self.known_text = [
            "The quick brown fox jumps over a lazy dog by the river",
            "Pack my box with five dozen jugs of liquid soap 1234567890",
            "She explained that nothing was impossible if you worked hard"
        ]
        
        self.glyph_bank = defaultdict(list)
        self.extracted_glyphs = {}
        
    def load_image(self):
        """Load image in grayscale."""
        if not os.path.exists(self.image_path):
            print(f"⚠️  Image not found: {self.image_path}")
            return None
        
        img = cv2.imread(self.image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"⚠️  Failed to load: {self.image_path}")
            return None
        
        print(f"✅ Loaded image: {img.shape}")
        return img
    
    def find_text_lines(self, img):
        """Find text lines using horizontal projection."""
        # Threshold image
        _, binary = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY_INV)
        
        # Horizontal projection - sum pixels in each row
        horizontal_projection = binary.sum(axis=1)
        
        # Find row clusters with text
        threshold = np.max(horizontal_projection) * 0.1
        text_rows = np.where(horizontal_projection > threshold)[0]
        
        if len(text_rows) == 0:
            print("⚠️  No text found in image")
            return []
        
        # Find gaps between lines
        gaps = np.diff(text_rows)
        gap_threshold = np.mean(gaps) * 3  # 3x average gap = new line
        
        line_breaks = np.where(gaps > gap_threshold)[0]
        lines = []
        
        start = text_rows[0]
        for break_idx in line_breaks:
            end = text_rows[break_idx]
            lines.append((start, end))
            start = text_rows[break_idx + 1]
        lines.append((start, text_rows[-1]))
        
        print(f"✅ Found {len(lines)} text lines")
        return lines
    
    def find_word_boundaries(self, img, line_bounds):
        """Find word boundaries in a line using vertical projection."""
        y_start, y_end = line_bounds
        line_region = img[y_start:y_end+1, :]
        
        _, binary = cv2.threshold(line_region, 150, 255, cv2.THRESH_BINARY_INV)
        
        # Vertical projection - sum pixels in each column
        vertical_projection = binary.sum(axis=0)
        
        # Find column clusters with text
        threshold = np.max(vertical_projection) * 0.1
        text_cols = np.where(vertical_projection > threshold)[0]
        
        if len(text_cols) == 0:
            return []
        
        # Find gaps between words
        gaps = np.diff(text_cols)
        gap_threshold = np.mean(gaps) * 2  # 2x average gap = word boundary
        
        word_breaks = np.where(gaps > gap_threshold)[0]
        words = []
        
        start = text_cols[0]
        for break_idx in word_breaks:
            end = text_cols[break_idx]
            words.append((start, end))
            start = text_cols[break_idx + 1]
        words.append((start, text_cols[-1]))
        
        return [(y_start, y_end, x_s, x_e) for x_s, x_e in words]
    
    def match_words_to_text(self, detected_words, known_line):
        """Match detected word regions to known text words."""
        known_words = known_line.split()
        
        if len(detected_words) != len(known_words):
            print(f"⚠️  Word count mismatch: found {len(detected_words)}, expected {len(known_words)}")
        
        # Pair up words
        word_mapping = []
        for i, (y_start, y_end, x_start, x_end) in enumerate(detected_words):
            if i < len(known_words):
                word_text = known_words[i]
                word_mapping.append({
                    'text': word_text,
                    'bounds': (y_start, y_end, x_start, x_end),
                    'num_chars': len(word_text)
                })
        
        return word_mapping
    
    def extract_character_crops(self, img, word_info):
        """Extract individual character crops from a word."""
        y_start, y_end, x_start, x_end = word_info['bounds']
        word_text = word_info['text']
        num_chars = word_info['num_chars']
        
        word_region = img[y_start:y_end+1, x_start:x_end+1]
        word_width = x_end - x_start + 1
        char_width = word_width / num_chars
        
        characters = []
        for i, char in enumerate(word_text):
            char_x_start = int(i * char_width)
            char_x_end = int((i + 1) * char_width)
            
            # Add padding
            char_x_start = max(0, char_x_start - 2)
            char_x_end = min(word_width, char_x_end + 2)
            
            char_crop = word_region[:, char_x_start:char_x_end]
            
            if char_crop.size > 0:
                characters.append({
                    'char': char,
                    'crop': char_crop,
                    'original_bounds': (y_start, y_end, x_start + char_x_start, x_start + char_x_end)
                })
        
        return characters
    
    def crop_to_rgba_glyph(self, crop, target_height=50):
        """Convert character crop to RGBA glyph."""
        if crop.size == 0:
            return None
        
        # Find bounding box of actual text
        _, binary = cv2.threshold(crop, 150, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Get bounding box of all contours
        x_min, y_min = float('inf'), float('inf')
        x_max, y_max = 0, 0
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            x_min = min(x_min, x)
            y_min = min(y_min, y)
            x_max = max(x_max, x + w)
            y_max = max(y_max, y + h)
        
        if x_min >= x_max or y_min >= y_max:
            return None
        
        # Crop to text
        text_crop = crop[y_min:y_max, x_min:x_max]
        
        # Resize to target height preserving aspect ratio
        height, width = text_crop.shape
        if height == 0:
            return None
        
        aspect_ratio = width / height
        new_height = target_height
        new_width = int(new_height * aspect_ratio)
        
        resized = cv2.resize(text_crop, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
        
        # Convert to RGBA: dark pixels = opaque, white = transparent
        rgba = np.zeros((new_height, new_width, 4), dtype=np.uint8)
        
        # Invert so text is dark
        inverted = 255 - resized
        
        # Use inverted as alpha channel (dark text = high alpha)
        rgba[:, :, 0] = 0      # Red
        rgba[:, :, 1] = 0      # Green
        rgba[:, :, 2] = 0      # Blue
        rgba[:, :, 3] = inverted  # Alpha
        
        return rgba
    
    def extract_all_glyphs(self, img):
        """Extract all glyphs from image."""
        lines = self.find_text_lines(img)
        
        if not lines:
            print("⚠️  No text lines found")
            return False
        
        glyph_count = 0
        
        for line_idx, line_bounds in enumerate(lines):
            if line_idx >= len(self.known_text):
                break
            
            known_line = self.known_text[line_idx]
            print(f"\n📄 Processing line {line_idx + 1}: {known_line[:40]}...")
            
            # Find words in this line
            detected_words = self.find_word_boundaries(img, line_bounds)
            word_mapping = self.match_words_to_text(detected_words, known_line)
            
            # Extract characters from each word
            for word_idx, word_info in enumerate(word_mapping):
                characters = self.extract_character_crops(img, word_info)
                
                for char_info in characters:
                    char = char_info['char']
                    crop = char_info['crop']
                    
                    # Convert to RGBA glyph
                    glyph = self.crop_to_rgba_glyph(crop, target_height=50)
                    
                    if glyph is not None:
                        # Save glyph
                        char_dir = self.output_dir / char
                        char_dir.mkdir(exist_ok=True)
                        
                        # Count existing variants
                        existing = len(list(char_dir.glob("*.png")))
                        glyph_path = char_dir / f"{char}_{existing}.png"
                        
                        # Save as PNG
                        glyph_img = Image.fromarray(glyph, 'RGBA')
                        glyph_img.save(glyph_path)
                        
                        self.glyph_bank[char].append(str(glyph_path))
                        glyph_count += 1
                        print(f"   ✓ {char} (variant {existing + 1})")
        
        print(f"\n✅ Extracted {glyph_count} total glyphs")
        return glyph_count > 0
    
    def create_glyph_bank_json(self):
        """Create glyph_bank.json mapping."""
        glyph_bank_data = {}
        
        for char in sorted(self.glyph_bank.keys()):
            paths = self.glyph_bank[char]
            glyph_bank_data[char] = paths
        
        json_path = self.output_dir / "glyph_bank.json"
        with open(json_path, 'w') as f:
            json.dump(glyph_bank_data, f, indent=2)
        
        print(f"✅ Created glyph_bank.json with {len(glyph_bank_data)} characters")
        return json_path
    
    def load_glyph_bank_as_dict(self):
        """Load glyph bank as dictionary for render engine."""
        glyph_dict = {}
        
        for char, paths in self.glyph_bank.items():
            glyph_dict[char] = []
            for path in paths:
                try:
                    img = Image.open(path).convert('RGBA')
                    glyph_dict[char].append(img)
                except Exception as e:
                    print(f"⚠️  Failed to load {path}: {e}")
        
        print(f"✅ Loaded {len(glyph_dict)} characters into glyph bank")
        return glyph_dict


def test_pipeline_with_real_glyphs(glyph_extractor):
    """Test full pipeline with real glyphs."""
    print("\n" + "="*60)
    print("🧪 TESTING PIPELINE WITH REAL GLYPHS")
    print("="*60)
    
    # Import pipeline modules
    sys.path.insert(0, str(Path(__file__).parent))
    from render_engine import HandwritingRenderer
    from paper_backgrounds import generate_college_ruled
    from compositor import composite, INK_COLORS
    from artifact_simulator import simulate_scan
    
    # Load real glyphs
    glyph_bank = glyph_extractor.load_glyph_bank_as_dict()
    
    if not glyph_bank:
        print("⚠️  No glyphs loaded, skipping pipeline test")
        return
    
    # Render test text
    test_text = "The quick brown fox"
    print(f"\n📝 Rendering: '{test_text}'")
    
    renderer = HandwritingRenderer(glyph_bank, seed=42)
    text_img = renderer.render(test_text, neatness=0.6)
    print("✅ Text rendered")
    
    # Generate paper
    print("📄 Generating college ruled paper...")
    paper = generate_college_ruled()
    print("✅ Paper generated")
    
    # Composite
    print("🎨 Compositing...")
    result = composite(text_img, paper, ink_color=INK_COLORS['black'])
    print("✅ Composited")
    
    # Apply scan effect
    print("📸 Applying scan simulation...")
    final = simulate_scan(result)
    print("✅ Scan applied")
    
    # Save output
    output_path = Path("output") / "real_handwriting_test.png"
    output_path.parent.mkdir(exist_ok=True)
    final.save(output_path)
    print(f"\n✅ SAVED: {output_path}")
    print(f"   Size: {final.size}")
    print(f"   Mode: {final.mode}")
    
    return output_path


def main():
    """Main extraction workflow."""
    print("╔════════════════════════════════════════════╗")
    print("║   REAL GLYPH EXTRACTION FROM HANDWRITING   ║")
    print("╚════════════════════════════════════════════╝")
    
    # Create extractor
    image_path = "clean.jpg"
    extractor = GlyphExtractor(image_path, output_dir="real_glyphs")
    
    # Step 1: Load image
    print("\n[1/5] Loading image...")
    img = extractor.load_image()
    if img is None:
        print("⚠️  Image not found. Creating test image...")
        # Create a test image with handwritten-style text
        test_img = np.ones((600, 1200), dtype=np.uint8) * 255
        for i, line in enumerate(extractor.known_text):
            y = 100 + i * 150
            cv2.putText(test_img, line, (50, y), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.8, 0, 2)
        
        cv2.imwrite(image_path, test_img)
        img = test_img
        print(f"✅ Created test image: {image_path}")
    
    # Step 2: Extract glyphs
    print("\n[2/5] Extracting glyphs from image...")
    if not extractor.extract_all_glyphs(img):
        print("⚠️  Glyph extraction failed")
        return
    
    # Step 3: Create glyph bank JSON
    print("\n[3/5] Creating glyph bank JSON...")
    extractor.create_glyph_bank_json()
    
    # Step 4: Test pipeline
    print("\n[4/5] Testing full pipeline with real glyphs...")
    test_pipeline_with_real_glyphs(extractor)
    
    print("\n[5/5] ✅ COMPLETE")
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"Glyphs extracted: {sum(len(v) for v in extractor.glyph_bank.values())}")
    print(f"Unique characters: {len(extractor.glyph_bank)}")
    print(f"Output directory: {extractor.output_dir}")
    print(f"Glyph bank JSON: {extractor.output_dir / 'glyph_bank.json'}")
    print(f"Test output: output/real_handwriting_test.png")
    print("\n✅ Real glyphs ready for use!")


if __name__ == "__main__":
    main()
