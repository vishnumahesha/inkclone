"""
InkClone Template Generator
Generates a printable PDF template with a grid of labeled cells for handwriting samples.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm, inch
from reportlab.lib.colors import HexColor, black, gray

# Page dimensions (US Letter)
PAGE_W, PAGE_H = letter  # 612 x 792 points

# Margins
MARGIN = 0.5 * inch  # 36pt

# Cell dimensions
CELL_W = 34   # points
CELL_H = 42   # points
CELL_BORDER = 0.5  # pt
CELL_BORDER_COLOR = HexColor('#CCCCCC')
BASELINE_COLOR = HexColor('#E0E0E0')
BASELINE_WIDTH = 0.3
LABEL_COLOR = HexColor('#BBBBBB')
LABEL_FONT_SIZE = 6

# Gap between cells
H_GAP = 4   # horizontal gap between cells
V_GAP = 14  # vertical gap between cells

# Registration mark dimensions
REG_MARK_SIZE = 8 * mm   # 8mm total length
REG_MARK_OFFSET = 15 * mm  # 15mm from each edge
REG_MARK_LINE_W = 0.5

# Colors
TITLE_COLOR = HexColor('#999999')
FOOTER_COLOR = gray


def draw_registration_marks(c, page_w=PAGE_W, page_h=PAGE_H):
    """Draw four crosshair registration marks in corners."""
    half = REG_MARK_SIZE / 2
    positions = [
        (REG_MARK_OFFSET, page_h - REG_MARK_OFFSET),           # TL
        (page_w - REG_MARK_OFFSET, page_h - REG_MARK_OFFSET),  # TR
        (page_w - REG_MARK_OFFSET, REG_MARK_OFFSET),           # BR
        (REG_MARK_OFFSET, REG_MARK_OFFSET),                    # BL
    ]
    c.setStrokeColor(black)
    c.setLineWidth(REG_MARK_LINE_W)
    for (x, y) in positions:
        # Horizontal bar
        c.line(x - half, y, x + half, y)
        # Vertical bar
        c.line(x, y - half, x, y + half)
        # Center dot circle (tiny)
        c.circle(x, y, 0.5, fill=1, stroke=0)


def draw_cell(c, x, y, char, dashes=True):
    """Draw a single cell at (x,y) bottom-left with border, baseline, and label."""
    # Cell border
    c.setStrokeColor(CELL_BORDER_COLOR)
    c.setLineWidth(CELL_BORDER)
    c.setFillColor(CELL_BORDER_COLOR)
    c.rect(x, y, CELL_W, CELL_H, stroke=1, fill=0)

    # Baseline at 60% height (dashed)
    baseline_y = y + CELL_H * 0.60
    c.setStrokeColor(BASELINE_COLOR)
    c.setLineWidth(BASELINE_WIDTH)
    if dashes:
        c.setDash([2, 2], 0)
    c.line(x, baseline_y, x + CELL_W, baseline_y)
    c.setDash([], 0)  # reset dash

    # Character label below baseline (inside cell, near bottom)
    label_y = y + 2
    c.setFillColor(LABEL_COLOR)
    c.setFont('Helvetica', LABEL_FONT_SIZE)
    c.drawCentredString(x + CELL_W / 2, label_y, char)


def draw_grid(c, cells, title, page_w=PAGE_W, page_h=PAGE_H):
    """Draw a full page of cells with title and footer."""
    # Title
    c.setFillColor(TITLE_COLOR)
    c.setFont('Helvetica', 10)
    c.drawString(MARGIN, page_h - MARGIN + 8, title)

    # Cells: each cell is (x, y, char) where y is bottom-left in PDF coords
    for (x, y, char) in cells:
        draw_cell(c, x, y, char)

    # Footer
    footer_text = "InkClone v1 | Print at 100% scale | Do not resize"
    c.setFillColor(FOOTER_COLOR)
    c.setFont('Helvetica', 7)
    c.drawCentredString(page_w / 2, MARGIN / 2, footer_text)

    draw_registration_marks(c)


def compute_grid_positions(col_count, char_list, page_w=PAGE_W, page_h=PAGE_H):
    """
    Given a flat list of characters and a column count, compute cell positions.
    Returns list of (x, y, char).
    Characters are laid out left-to-right, top-to-bottom.
    """
    # Available drawing area
    draw_w = page_w - 2 * MARGIN
    draw_h = page_h - 2 * MARGIN - 20  # leave 20pt for title

    # Starting position: top-left cell bottom-left corner
    # We go top-to-bottom so first row is near the top
    cells = []
    for i, char in enumerate(char_list):
        col = i % col_count
        row = i // col_count
        x = MARGIN + col * (CELL_W + H_GAP)
        # y in PDF coords: top of grid - row*(CELL_H+V_GAP) - CELL_H
        top_y = page_h - MARGIN - 20  # below title
        y = top_y - (row + 1) * CELL_H - row * V_GAP
        cells.append((x, y, char))
    return cells


def build_page1_chars():
    """
    Page 1 — Lowercase: 8 columns × 13 rows.
    Each letter a-z appears 4 times (4 variants).
    Row 0: a,a,a,a,b,b,b,b
    Row 1: c,c,c,c,d,d,d,d  ...etc
    Row 12: y,y,y,y,z,z,z,z
    """
    chars = []
    letters = 'abcdefghijklmnopqrstuvwxyz'
    # 13 rows, 2 letters per row (pairs), 4 variants each = 8 per row
    for i in range(0, 26, 2):
        pair = letters[i:i+2]  # e.g. 'ab', 'cd', ...
        for ch in pair:
            chars.extend([ch, ch, ch, ch])
    return chars  # 26*4 = 104 chars, 13 rows * 8 cols


def build_page2_chars():
    """
    Page 2 — Uppercase + Digits: 9 columns.
    Uppercase A-Z with 3 variants each (rows 0-8)
    Digits 0-9 with 2 variants each (rows 9-11)
    Row 0: A,A,A,B,B,B,C,C,C
    Row 1: D,D,D,E,E,E,F,F,F  ...etc
    Row 8: Y,Y,Y,Z,Z,Z,(3 empty)
    Row 9: 0,0,1,1,2,2,3,3,4
    Row 10: 4,5,5,6,6,7,7,8,8
    Row 11: 9,9,(rest empty)
    """
    chars = []
    # Uppercase: 9 per row (3 letters × 3 variants), 9 rows
    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    # Groups of 3 letters per row
    for i in range(0, 27, 3):
        group = letters[i:i+3]
        for ch in group:
            chars.extend([ch, ch, ch])
    # Row 8 partial: Y,Y,Y,Z,Z,Z + 3 empty
    # Wait - 26 uppercase letters, groups of 3 = 8 full rows (24 letters) + 1 partial row (Y,Z)
    # Let me recalculate:
    # letters[0:3] = ABC -> row 0: A,A,A,B,B,B,C,C,C (9 chars)
    # letters[3:6] = DEF -> row 1: D,D,D,E,E,E,F,F,F (9 chars)
    # ...
    # letters[21:24] = VWX -> row 7: V,V,V,W,W,W,X,X,X (9 chars)
    # letters[24:26] = YZ  -> row 8: Y,Y,Y,Z,Z,Z,(empty,empty,empty)
    # The above loop goes to i=24 (letters[24:27] = 'YZ') adding YY,ZZ but not a 3rd letter
    # Need to rebuild more carefully
    chars = []
    for i in range(0, 24, 3):
        group = letters[i:i+3]  # Full groups of 3
        for ch in group:
            chars.extend([ch, ch, ch])
    # Row 8: Y,Y,Y,Z,Z,Z + 3 empty
    chars.extend(['Y', 'Y', 'Y', 'Z', 'Z', 'Z', '', '', ''])

    # Digits 0-9, 2 variants each = 20 chars across 3 rows of 9
    # Row 9:  0,0,1,1,2,2,3,3,4
    # Row 10: 4,5,5,6,6,7,7,8,8
    # Row 11: 9,9,(rest empty)
    digit_chars = []
    for d in '0123456789':
        digit_chars.extend([d, d])
    # digit_chars = 0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9  (20 chars)
    # Pad to 3 rows of 9 = 27 with empty
    while len(digit_chars) < 27:
        digit_chars.append('')
    chars.extend(digit_chars[:27])

    return chars


def build_page3_chars():
    """
    Page 3 — Punctuation: 8 columns.
    Characters . , ! ? ' " - : ; ( ) / @ & # + = * each with 2 variants (34 cells).
    Pad to fill rows of 8.
    """
    punct = ['.', ',', '!', '?', "'", '"', '-', ':', ';', '(', ')', '/', '@', '&', '#', '+', '=', '*']
    chars = []
    for ch in punct:
        chars.extend([ch, ch])
    # 18 * 2 = 36 chars. Pad to next multiple of 8
    while len(chars) % 8 != 0:
        chars.append('')
    return chars


def generate_template(output_path='output/template_v1.pdf'):
    """Generate the full 3-page template PDF."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    c = canvas.Canvas(output_path, pagesize=letter)
    c.setTitle("InkClone Handwriting Template v1")

    # ── Page 1: Lowercase ──────────────────────────────────────────────
    p1_chars = build_page1_chars()
    p1_cells = compute_grid_positions(8, p1_chars)
    draw_grid(c, p1_cells, "InkClone Template — Lowercase (a–z, 4 variants each)")
    c.showPage()

    # ── Page 2: Uppercase + Digits ─────────────────────────────────────
    p2_chars = build_page2_chars()
    p2_cells = compute_grid_positions(9, p2_chars)
    draw_grid(c, p2_cells, "InkClone Template — Uppercase (A–Z) + Digits (0–9)")
    c.showPage()

    # ── Page 3: Punctuation ────────────────────────────────────────────
    p3_chars = build_page3_chars()
    p3_cells = compute_grid_positions(8, p3_chars)
    draw_grid(c, p3_cells, "InkClone Template — Punctuation")
    c.showPage()

    c.save()
    print(f"Template saved to: {output_path}")
    return output_path


if __name__ == '__main__':
    import sys
    output = 'output/template_v1.pdf'
    path = generate_template(output)

    # Verify
    if not os.path.exists(path):
        print("ERROR: PDF not created!")
        sys.exit(1)

    size = os.path.getsize(path)
    print(f"File size: {size} bytes")

    # Count pages via reportlab reader
    try:
        from reportlab.lib.utils import open_for_read
        with open(path, 'rb') as f:
            data = f.read()
        page_count = data.count(b'/Type /Page\n') + data.count(b'/Type /Page\r') + data.count(b'/Type /Page ')
        # Simple approach: count showPage markers in raw PDF
        # Better: use pdfreader if available
        pages_token = data.count(b'%%Page:')
        print(f"PDF tokens found (rough page count check): {pages_token}")
    except Exception:
        pass

    # Simple binary check: count /Page dictionary entries
    with open(path, 'rb') as f:
        raw = f.read()
    # Count Type /Page occurrences
    import re
    page_matches = len(re.findall(rb'/Type\s*/Page\b', raw))
    print(f"Detected page objects: {page_matches} (expected 3)")

    if size < 1000:
        print("ERROR: File too small!")
        sys.exit(1)

    print("Template generation: PASSED")
