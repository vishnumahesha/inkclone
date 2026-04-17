#!/usr/bin/env python3
"""
Page Layout Engine - Smart text positioning and layout

Functions:
- Calculate baseline positions for ruled papers
- Wrap text intelligently to avoid orphans
- Apply margin variation per line
- Progressive page fatigue (messier toward bottom)
"""

import numpy as np

class PageLayout:
    """Smart page layout for handwriting documents."""
    
    @staticmethod
    def calculate_ruled_baselines(paper_type, page_height, start_y=150):
        """Calculate y-positions where text baselines should sit on ruled paper."""
        line_spacing_map = {
            "college_ruled": 42,
            "wide_ruled": 52,
            "legal_pad": 42,
            "dot_grid": 42,
        }
        
        line_spacing = line_spacing_map.get(paper_type, 85)
        
        baselines = []
        y = start_y
        while y < page_height - 100:
            baselines.append(y)
            y += line_spacing
        
        return baselines
    
    @staticmethod
    def wrap_text_to_lines(text, chars_per_line=70, avoid_orphans=True):
        """Break text into lines avoiding orphan words."""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            word_len = len(word) + 1  # +1 for space
            
            if current_length + word_len <= chars_per_line:
                current_line.append(word)
                current_length += word_len
            else:
                # Line would be full
                if current_line:
                    # Check orphan: if this word alone fits, and there's only 1 word on current line
                    if avoid_orphans and len(current_line) == 1 and word_len <= chars_per_line:
                        # Don't orphan - keep both on same line if possible
                        if len(words) > len(current_line):
                            lines.append(" ".join(current_line))
                            current_line = [word]
                            current_length = word_len
                        else:
                            current_line.append(word)
                            current_length += word_len
                    else:
                        lines.append(" ".join(current_line))
                        current_line = [word]
                        current_length = word_len
        
        if current_line:
            lines.append(" ".join(current_line))
        
        return lines
    
    @staticmethod
    def apply_margin_jitter(base_margin, line_index, variance=10):
        """Return slightly different left margin per line for natural variation."""
        # Vary margin by ±variance pixels, more variation toward bottom
        jitter_amount = np.random.normal(0, variance * (0.5 + line_index * 0.05))
        return max(10, int(base_margin + jitter_amount))
    
    @staticmethod
    def apply_page_fatigue(line_index, total_lines):
        """Return adjustment factors making writing messier toward bottom of page."""
        # Line position as fraction: 0 = top, 1 = bottom
        position = line_index / max(1, total_lines - 1)
        
        return {
            'neatness_reduction': position * 0.3,  # Increasingly messy
            'jitter_scale': 1.0 + position * 0.4,  # More jitter
            'rotation_scale': 1.0 + position * 0.3,  # More rotation
            'spacing_variance': 1.0 + position * 0.2,  # Spacing gets less consistent
            'baseline_drift': position * 2.0,  # Baseline wobbles more
        }


def test_page_layout():
    """Test all page layout functions."""
    print("Testing page layout engine...")
    
    # Test 1: Baseline calculation
    print("\n[1/4] Testing baseline calculation...")
    baselines = PageLayout.calculate_ruled_baselines("college_ruled", 3200)
    print(f"✅ Generated {len(baselines)} baselines")
    assert len(baselines) > 30, "Should have many lines"
    
    # Test 2: Text wrapping
    print("[2/4] Testing text wrapping...")
    long_text = "The quick brown fox jumps over the lazy dog by the river and runs through the forest without stopping for breath"
    lines = PageLayout.wrap_text_to_lines(long_text, chars_per_line=40, avoid_orphans=True)
    print(f"✅ Wrapped into {len(lines)} lines")
    for i, line in enumerate(lines):
        print(f"   Line {i}: '{line}'")
    assert all(len(line) <= 55 for line in lines), "Lines too long"
    
    # Test 3: Margin jitter
    print("[3/4] Testing margin jitter...")
    base_margin = 200
    margins = [PageLayout.apply_margin_jitter(base_margin, i, variance=15) for i in range(10)]
    print(f"✅ Generated margins: {margins}")
    assert all(m > 0 for m in margins), "Margins must be positive"
    assert abs(np.mean(margins) - base_margin) < 30, "Jitter should be around base"
    
    # Test 4: Page fatigue
    print("[4/4] Testing page fatigue...")
    total_lines = 30
    fatigue_top = PageLayout.apply_page_fatigue(0, total_lines)
    fatigue_mid = PageLayout.apply_page_fatigue(15, total_lines)
    fatigue_bot = PageLayout.apply_page_fatigue(29, total_lines)
    
    print(f"✅ Top line fatigue: {fatigue_top['neatness_reduction']:.2f}")
    print(f"✅ Mid line fatigue: {fatigue_mid['neatness_reduction']:.2f}")
    print(f"✅ Bot line fatigue: {fatigue_bot['neatness_reduction']:.2f}")
    
    assert fatigue_top['neatness_reduction'] < fatigue_mid['neatness_reduction']
    assert fatigue_mid['neatness_reduction'] < fatigue_bot['neatness_reduction']
    
    print("\n✅ Page layout engine tested!")


if __name__ == "__main__":
    test_page_layout()
