#!/usr/bin/env python3
"""
Template Generator v2 - Professional multi-page PDF templates

4-page professional template for handwriting capture:
- Page 1: Lowercase a-z (5 cells per letter)
- Page 2: Uppercase A-Z (4 cells per letter)
- Page 3: Digits and punctuation (2-3 cells each)
- Page 4: Ligatures and common word pairs (3 cells each)

Features:
- Grid layout with 1.2cm x 1.5cm cells
- Gray baseline at 60% height
- Character labels in light gray
- Crosshair registration marks (15mm from corners)
- Page titles and numbers
"""

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import Color
from pathlib import Path

class TemplateGeneratorV2:
    """Professional multi-page handwriting capture template."""
    
    def __init__(self, output_path="output/template_v2.pdf"):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(exist_ok=True)
        
        # Page setup
        self.page_width, self.page_height = letter
        self.margin = 1.5 * cm
        self.cell_width = 1.2 * cm
        self.cell_height = 1.5 * cm
        
        # Colors
        self.black = Color(0, 0, 0)
        self.gray_light = Color(0.8, 0.8, 0.8)
        self.gray_dark = Color(0.5, 0.5, 0.5)
        
    def draw_crosshairs(self, c, page_num):
        """Draw registration marks at all 4 corners."""
        crosshair_size = 15 * mm
        offset = 15 * mm
        
        positions = [
            (offset, offset),
            (self.page_width - offset, offset),
            (offset, self.page_height - offset),
            (self.page_width - offset, self.page_height - offset),
        ]
        
        for x, y in positions:
            # Horizontal line
            c.setLineWidth(0.5)
            c.setStrokeColor(self.gray_light)
            c.line(x - crosshair_size/2, y, x + crosshair_size/2, y)
            # Vertical line
            c.line(x, y - crosshair_size/2, x, y + crosshair_size/2)
            # Center dot
            c.setFillColor(self.gray_dark)
            c.circle(x, y, 1.5, fill=1)
    
    def draw_cell_grid(self, c, characters, cells_per_char, title, page_num):
        """Draw a grid of cells for character capture."""
        # Title
        c.setFont("Helvetica-Bold", 14)
        c.drawString(self.margin, self.page_height - self.margin, title)
        
        # Page number
        c.setFont("Helvetica", 10)
        c.drawString(self.page_width - self.margin - 2*cm, 0.5*cm, f"Page {page_num}")
        
        # Draw crosshairs
        self.draw_crosshairs(c, page_num)
        
        # Calculate grid layout
        cells_per_row = int((self.page_width - 2*self.margin) / self.cell_width)
        
        x = self.margin
        y = self.page_height - 2*self.margin
        
        for char in characters:
            for cell_num in range(cells_per_char):
                # Cell border
                c.setLineWidth(0.5)
                c.setStrokeColor(self.gray_light)
                c.rect(x, y - self.cell_height, self.cell_width, self.cell_height)
                
                # Baseline at 60% height
                baseline_y = y - (self.cell_height * 0.6)
                c.setLineWidth(0.25)
                c.setStrokeColor(self.gray_light)
                c.line(x, baseline_y, x + self.cell_width, baseline_y)
                
                # Character label (below cell)
                if cell_num == 0:
                    c.setFont("Helvetica", 8)
                    c.setFillColor(self.gray_dark)
                    c.drawString(x + 0.1*cm, y - self.cell_height - 0.3*cm, char)
                
                # Move to next cell
                x += self.cell_width
                if x + self.cell_width > self.page_width - self.margin:
                    x = self.margin
                    y -= self.cell_height
                    if y < self.margin:
                        return  # Page full
    
    def generate(self):
        """Generate 4-page template PDF."""
        c = canvas.Canvas(str(self.output_path), pagesize=letter)
        
        # Page 1: Lowercase a-z
        print("[1/4] Generating lowercase page...")
        chars_lower = "abcdefghijklmnopqrstuvwxyz"
        self.draw_cell_grid(c, chars_lower, 5, "Lowercase Letters (a-z)", 1)
        c.showPage()
        
        # Page 2: Uppercase A-Z
        print("[2/4] Generating uppercase page...")
        chars_upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        self.draw_cell_grid(c, chars_upper, 4, "Uppercase Letters (A-Z)", 2)
        c.showPage()
        
        # Page 3: Digits and punctuation
        print("[3/4] Generating digits and punctuation page...")
        digits_and_punct = "0123456789.,!?'\"\\-:;()/#&"
        self.draw_cell_grid(c, digits_and_punct, 2, "Digits & Punctuation", 3)
        c.showPage()
        
        # Page 4: Ligatures and common pairs
        print("[4/4] Generating ligatures page...")
        ligatures = ["th", "he", "in", "an", "on", "er", "re", "ed", "ing", "tion"]
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(self.margin, self.page_height - self.margin, "Common Ligatures & Pairs")
        
        c.setFont("Helvetica", 10)
        c.drawString(self.page_width - self.margin - 2*cm, 0.5*cm, "Page 4")
        
        self.draw_crosshairs(c, 4)
        
        x = self.margin
        y = self.page_height - 2*self.margin
        cells_per_row = int((self.page_width - 2*self.margin) / self.cell_width)
        
        for pair in ligatures:
            for cell_num in range(3):
                # Cell border
                c.setLineWidth(0.5)
                c.setStrokeColor(self.gray_light)
                c.rect(x, y - self.cell_height, self.cell_width, self.cell_height)
                
                # Baseline
                baseline_y = y - (self.cell_height * 0.6)
                c.setLineWidth(0.25)
                c.setStrokeColor(self.gray_light)
                c.line(x, baseline_y, x + self.cell_width, baseline_y)
                
                # Label (below cell)
                if cell_num == 0:
                    c.setFont("Helvetica", 8)
                    c.setFillColor(self.gray_dark)
                    c.drawString(x + 0.05*cm, y - self.cell_height - 0.3*cm, pair)
                
                x += self.cell_width
                if x + self.cell_width > self.page_width - self.margin:
                    x = self.margin
                    y -= self.cell_height
        
        c.showPage()
        c.save()
        
        print(f"\n✅ Generated: {self.output_path}")
        print(f"   Size: {self.output_path.stat().st_size / 1024:.1f} KB")
        print(f"   Pages: 4")
        print(f"   Features: Grid layout, baselines, registration marks")


if __name__ == "__main__":
    generator = TemplateGeneratorV2()
    generator.generate()
    print("\n✅ Template v2 ready for use!")
