#!/usr/bin/env python3
"""
Natural Writing Analyzer

Analyzes layout and spacing parameters from natural handwriting photos
WITHOUT extracting individual characters.

Measures:
- Inter-word gaps (average and variance)
- Line height
- Line spacing
- Left margin position
- Baseline angle/drift per line
- Overall slant angle from vertical strokes
"""

import cv2
import numpy as np
import json
from pathlib import Path
from scipy import stats

class NaturalWritingAnalyzer:
    """Analyzes handwriting layout parameters."""
    
    def __init__(self, image_path, output_json="output/layout_params.json"):
        self.image_path = image_path
        self.output_json = Path(output_json)
        self.output_json.parent.mkdir(exist_ok=True)
        
        self.measurements = {}
    
    def load_image(self):
        """Load image and convert to grayscale."""
        img = cv2.imread(self.image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"⚠️  Failed to load: {self.image_path}")
            return None
        
        print(f"✅ Loaded image: {img.shape}")
        return img
    
    def find_text_lines(self, img):
        """Find text lines using horizontal projection."""
        _, binary = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY_INV)
        
        # Horizontal projection
        horizontal = binary.sum(axis=1)
        
        # Find text regions
        threshold = np.max(horizontal) * 0.1
        text_rows = np.where(horizontal > threshold)[0]
        
        if len(text_rows) == 0:
            return []
        
        # Find line boundaries
        gaps = np.diff(text_rows)
        gap_threshold = np.mean(gaps) * 3
        
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
    
    def measure_line_height(self, lines):
        """Measure average line height in pixels."""
        heights = [end - start for start, end in lines]
        avg_height = np.mean(heights)
        std_height = np.std(heights)
        
        self.measurements['line_height_avg'] = float(avg_height)
        self.measurements['line_height_std'] = float(std_height)
        
        print(f"✅ Line height: {avg_height:.1f}px ± {std_height:.1f}px")
    
    def measure_line_spacing(self, lines):
        """Measure spacing between lines."""
        if len(lines) < 2:
            print("⚠️  Not enough lines for spacing measurement")
            return
        
        spacings = []
        for i in range(len(lines) - 1):
            gap = lines[i+1][0] - lines[i][1]
            spacings.append(gap)
        
        avg_spacing = np.mean(spacings)
        std_spacing = np.std(spacings)
        
        self.measurements['line_spacing_avg'] = float(avg_spacing)
        self.measurements['line_spacing_std'] = float(std_spacing)
        
        print(f"✅ Line spacing: {avg_spacing:.1f}px ± {std_spacing:.1f}px")
    
    def find_word_boundaries(self, img, line_bounds):
        """Find word boundaries using vertical projection."""
        y_start, y_end = line_bounds
        line_region = img[y_start:y_end+1, :]
        
        _, binary = cv2.threshold(line_region, 150, 255, cv2.THRESH_BINARY_INV)
        
        # Vertical projection
        vertical = binary.sum(axis=0)
        
        # Find text columns
        threshold = np.max(vertical) * 0.1
        text_cols = np.where(vertical > threshold)[0]
        
        if len(text_cols) == 0:
            return []
        
        # Find word boundaries
        gaps = np.diff(text_cols)
        gap_threshold = np.mean(gaps) * 2
        
        word_breaks = np.where(gaps > gap_threshold)[0]
        words = []
        
        start = text_cols[0]
        for break_idx in word_breaks:
            end = text_cols[break_idx]
            words.append((start, end))
            start = text_cols[break_idx + 1]
        words.append((start, text_cols[-1]))
        
        return words
    
    def measure_inter_word_gaps(self, img, lines):
        """Measure spacing between words."""
        all_gaps = []
        
        for line_bounds in lines:
            words = self.find_word_boundaries(img, line_bounds)
            if len(words) < 2:
                continue
            
            for i in range(len(words) - 1):
                gap = words[i+1][0] - words[i][1]
                all_gaps.append(gap)
        
        if all_gaps:
            avg_gap = np.mean(all_gaps)
            std_gap = np.std(all_gaps)
            
            self.measurements['inter_word_gap_avg'] = float(avg_gap)
            self.measurements['inter_word_gap_std'] = float(std_gap)
            
            print(f"✅ Inter-word gap: {avg_gap:.1f}px ± {std_gap:.1f}px")
    
    def measure_left_margin(self, img, lines):
        """Measure left margin position."""
        margins = []
        
        for y_start, y_end in lines:
            line_region = img[y_start:y_end+1, :]
            _, binary = cv2.threshold(line_region, 150, 255, cv2.THRESH_BINARY_INV)
            
            # Find leftmost text column
            vertical = binary.sum(axis=0)
            text_cols = np.where(vertical > 0)[0]
            
            if len(text_cols) > 0:
                margins.append(text_cols[0])
        
        if margins:
            avg_margin = np.mean(margins)
            std_margin = np.std(margins)
            
            self.measurements['left_margin_avg'] = float(avg_margin)
            self.measurements['left_margin_std'] = float(std_margin)
            
            print(f"✅ Left margin: {avg_margin:.1f}px ± {std_margin:.1f}px")
    
    def measure_baseline_drift(self, img, lines):
        """Measure baseline angle/drift within each line."""
        drifts = []
        
        for y_start, y_end in lines:
            line_region = img[y_start:y_end+1, :]
            _, binary = cv2.threshold(line_region, 150, 255, cv2.THRESH_BINARY_INV)
            
            # Find text centers per column section
            section_width = 50
            centers = []
            
            for x in range(0, binary.shape[1], section_width):
                x_end = min(x + section_width, binary.shape[1])
                col_region = binary[:, x:x_end]
                
                vertical = col_region.sum(axis=1)
                if vertical.max() > 0:
                    indices = np.where(vertical > 0)[0]
                    weights = vertical[indices]
                    center = np.average(indices, weights=weights)
                    centers.append((x + x_end//2, center))
            
            if len(centers) > 1:
                xs = np.array([c[0] for c in centers])
                ys = np.array([c[1] for c in centers])
                
                # Linear fit to get baseline drift
                slope = np.polyfit(xs, ys, 1)[0]
                drift_angle = np.arctan(slope) * 180 / np.pi
                drifts.append(drift_angle)
        
        if drifts:
            avg_drift = np.mean(drifts)
            std_drift = np.std(drifts)
            
            self.measurements['baseline_drift_avg_deg'] = float(avg_drift)
            self.measurements['baseline_drift_std_deg'] = float(std_drift)
            
            print(f"✅ Baseline drift: {avg_drift:.2f}° ± {std_drift:.2f}°")
    
    def measure_slant_angle(self, img):
        """Estimate overall slant angle from vertical strokes."""
        _, binary = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY_INV)
        
        # Use Hough line transform to find vertical/near-vertical strokes
        edges = cv2.Canny(binary, 50, 150)
        lines = cv2.HoughLines(edges, 1, np.pi/180, 50)
        
        if lines is None:
            print("⚠️  Could not measure slant angle")
            return
        
        angles = []
        for line in lines:
            rho, theta = line[0]
            angle_deg = theta * 180 / np.pi
            
            # Focus on near-vertical lines (70-110 degrees)
            if 70 < angle_deg < 110:
                angles.append(angle_deg - 90)  # Offset from vertical
        
        if angles:
            avg_slant = np.mean(angles)
            std_slant = np.std(angles)
            
            self.measurements['slant_angle_avg_deg'] = float(avg_slant)
            self.measurements['slant_angle_std_deg'] = float(std_slant)
            
            print(f"✅ Slant angle: {avg_slant:.2f}° ± {std_slant:.2f}°")
    
    def analyze(self):
        """Run full analysis."""
        print("\n" + "="*50)
        print("NATURAL WRITING ANALYZER")
        print("="*50)
        
        img = self.load_image()
        if img is None:
            return False
        
        print("\n[1/6] Finding text lines...")
        lines = self.find_text_lines(img)
        if not lines:
            return False
        
        print("[2/6] Measuring line heights...")
        self.measure_line_height(lines)
        
        print("[3/6] Measuring line spacing...")
        self.measure_line_spacing(lines)
        
        print("[4/6] Measuring inter-word gaps...")
        self.measure_inter_word_gaps(img, lines)
        
        print("[5/6] Measuring left margin...")
        self.measure_left_margin(img, lines)
        
        print("[6/6] Measuring baseline drift and slant...")
        self.measure_baseline_drift(img, lines)
        self.measure_slant_angle(img)
        
        # Save measurements
        with open(self.output_json, 'w') as f:
            json.dump(self.measurements, f, indent=2)
        
        print(f"\n✅ Saved measurements to: {self.output_json}")
        return True


def test_with_synthetic_image():
    """Test analyzer with synthetic image at known positions."""
    print("\n" + "="*50)
    print("TESTING WITH SYNTHETIC IMAGE")
    print("="*50)
    
    # Create synthetic image
    img = np.ones((400, 800), dtype=np.uint8) * 255
    
    # Draw lines of black rectangles at known positions
    line_height = 30
    line_spacing = 50
    inter_word_gap = 40
    left_margin = 50
    
    y = 50
    for line_idx in range(3):
        x = left_margin
        for word_idx in range(5):
            # Draw rectangle (word)
            cv2.rectangle(img, (x, y), (x+50, y+line_height), 0, -1)
            x += 50 + inter_word_gap
        y += line_height + line_spacing
    
    # Save synthetic image
    cv2.imwrite("output/synthetic_test.png", img)
    print("✅ Created synthetic test image")
    
    # Analyze it
    analyzer = NaturalWritingAnalyzer("output/synthetic_test.png", 
                                      "output/layout_params_synthetic.json")
    analyzer.analyze()
    
    # Check measurements
    print("\n📊 Ground truth vs measured:")
    print(f"   Line height: {line_height}px vs {analyzer.measurements.get('line_height_avg', '?'):.1f}px")
    print(f"   Line spacing: {line_spacing}px vs {analyzer.measurements.get('line_spacing_avg', '?'):.1f}px")
    print(f"   Inter-word gap: {inter_word_gap}px vs {analyzer.measurements.get('inter_word_gap_avg', '?'):.1f}px")
    print(f"   Left margin: {left_margin}px vs {analyzer.measurements.get('left_margin_avg', '?'):.1f}px")


if __name__ == "__main__":
    # Test with synthetic image
    test_with_synthetic_image()
    
    print("\n✅ Natural writing analyzer ready!")
