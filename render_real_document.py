#!/usr/bin/env python3
"""
Render a full document using real extracted handwriting glyphs
"""

import sys
import os

from paper_backgrounds import generate_college_ruled
from artifact_simulator import apply_scan_effect
import json
import random
from PIL import Image

def load_real_profile():
    """Load the real handwriting profile"""
    profile_path = "profiles"
    
    # Load metadata
    with open(f"{profile_path}/metadata.json", "r") as f:
        metadata = json.load(f)
    
    # Load glyph metadata  
    with open(f"{profile_path}/glyph_metadata.json", "r") as f:
        glyph_metadata = json.load(f)
    
    print(f"✅ Loaded real profile: {metadata['name']}")
    print(f"   - {metadata['total_chars']} unique characters")
    print(f"   - {metadata['total_glyphs']} total glyph variants")
    print(f"   - X-height: {metadata['layout']['x_height_px']}px")
    
    return metadata, glyph_metadata

def load_real_glyph(char, variant_idx=None):
    """Load a specific glyph from the real profile"""
    glyphs_dir = "profiles/glyphs"
    
    # Find available variants for this character
    available_files = [f for f in os.listdir(glyphs_dir) if f.startswith(f"{char}_") and f.endswith(".png")]
    
    if not available_files:
        print(f"⚠️  No real glyph found for '{char}', using fallback")
        return None
    
    # Select variant
    if variant_idx is not None and variant_idx < len(available_files):
        filename = available_files[variant_idx]
    else:
        filename = random.choice(available_files)
    
    glyph_path = f"{glyphs_dir}/{filename}"
    return Image.open(glyph_path).convert("RGBA")

def render_with_real_glyphs(text, metadata):
    """Render text using real extracted glyphs"""
    print(f"🖋️  Rendering with real handwriting glyphs...")
    
    # Create paper background
    paper = generate_college_ruled(width=2400, height=3200)
    print(f"📄 Generated college ruled paper: {paper.size}")
    
    # Layout parameters from real profile
    layout = metadata['layout']
    x_height = layout['x_height_px']
    line_spacing = int(x_height * layout['line_spacing_multiplier'])
    
    # Start position
    x_pos = 120  # Left margin for college ruled
    y_pos = 200  # Top margin
    baseline_y = y_pos + x_height
    
    # Track stats
    chars_rendered = 0
    glyphs_used = 0
    
    # Render each character
    for i, char in enumerate(text):
        if char == '\n' or x_pos > 2200:  # New line
            x_pos = 120
            y_pos += line_spacing
            baseline_y = y_pos + x_height
            if y_pos > 3000:  # End of page
                break
            continue
        
        if char == ' ':  # Space
            x_pos += int(layout['inter_word_gap_mean'])
            continue
        
        # Load real glyph
        glyph_img = load_real_glyph(char.lower())
        if glyph_img is None:
            continue
        
        # Apply baseline variation
        baseline_drift = layout['baseline_drift_amplitude'] * random.uniform(-1, 1)
        glyph_y = baseline_y + int(baseline_drift)
        
        # Apply slight slant
        slant = random.gauss(layout['slant_degrees_mean'], layout['slant_degrees_std'])
        if abs(slant) > 0.1:
            # Simple slant simulation with small rotation
            glyph_img = glyph_img.rotate(slant, expand=False, fillcolor=(0,0,0,0))
        
        # Paste glyph onto paper
        if glyph_img.mode == 'RGBA':
            paper.paste(glyph_img, (x_pos, glyph_y - glyph_img.height + x_height), glyph_img)
        else:
            paper.paste(glyph_img, (x_pos, glyph_y - glyph_img.height + x_height))
        
        # Advance position
        inter_letter_gap = int(random.gauss(layout['inter_letter_gap_mean'], layout['inter_letter_gap_std']))
        x_pos += glyph_img.width + inter_letter_gap
        
        chars_rendered += 1
        glyphs_used += 1
        
        # Progress indicator
        if chars_rendered % 20 == 0:
            print(f"   Rendered {chars_rendered} characters...")
    
    print(f"✅ Rendering complete:")
    print(f"   - {chars_rendered} characters rendered")
    print(f"   - {glyphs_used} real glyphs used")
    
    return paper

def main():
    """Render the APUSH text using real handwriting"""
    
    # The text to render
    text = "After the attack on Pearl Harbor the United States fully entered the war and quickly turned its economy into a wartime economy. Factories switched from making consumer goods to producing tanks planes and weapons."
    
    print("🚀 REAL HANDWRITING DOCUMENT GENERATOR")
    print("=" * 50)
    print(f"📝 Text length: {len(text)} characters")
    print()
    
    # Load real profile
    metadata, glyph_metadata = load_real_profile()
    print()
    
    # Render document
    document = render_with_real_glyphs(text, metadata)
    print()
    
    # Apply scan simulation
    print("📱 Applying scan effect...")
    final_document = apply_scan_effect(document)
    
    # Save result
    os.makedirs("output", exist_ok=True)
    output_path = "output/real_full_document.png"
    final_document.save(output_path)
    
    print(f"💾 Saved to: {output_path}")
    print(f"📐 Final size: {final_document.size}")
    print()
    print("🎉 REAL HANDWRITING DOCUMENT COMPLETE!")
    print()
    print("This is YOUR actual handwriting rendering APUSH content!")
    print("Check the output file to see the real product demo.")

if __name__ == "__main__":
    main()