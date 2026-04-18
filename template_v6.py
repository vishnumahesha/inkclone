#!/usr/bin/env python3
"""
InkClone Handwriting Template v6 — Calligraphr Style
-----------------------------------------------------
Minimal design. Nothing in the cells except a tiny label.
No guide lines. No writing zone backgrounds. No bullseyes.
Simple square corner markers. Maximum empty space for writing.

4 pages, 238 characters total.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import Color, black, white
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = letter

MARGIN_TOP = 0.95 * inch
MARGIN_BOTTOM = 0.45 * inch
MARGIN_LEFT = 0.5 * inch
MARGIN_RIGHT = 0.5 * inch

GRID_X = MARGIN_LEFT
GRID_Y_TOP = PAGE_H - MARGIN_TOP
GRID_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT
GRID_H = GRID_Y_TOP - MARGIN_BOTTOM

CELL_BORDER = Color(0.6, 0.6, 0.6)
LABEL_COLOR = Color(0.55, 0.55, 0.55)
MARKER_COLOR = Color(0.0, 0.0, 0.0)
HEADER_COLOR = Color(0.15, 0.15, 0.15)
FOOTER_COLOR = Color(0.5, 0.5, 0.5)

PAGE_CONFIGS = [
    {"cols": 6, "rows": 10,
     "title": "Lowercase a-o  (4 variants each)",
     "subtitle": "Write naturally. Each variant slightly different. Use a BLACK pen."},
    {"cols": 6, "rows": 10,
     "title": "Lowercase p-z  (4 variants each)",
     "subtitle": "Same rules. Write naturally, don't try to be perfect."},
    {"cols": 6, "rows": 10,
     "title": "Uppercase A-Z  (2 variants each)",
     "subtitle": "Write uppercase letters. Each variant slightly different."},
    {"cols": 8, "rows": 11,
     "title": "Digits + Punctuation + Letter Combos",
     "subtitle": "Digits and punctuation clearly. Combos (th, he, ing) connected naturally."},
]


def get_page_cells(page_num):
    if page_num == 1:
        cells = []
        for ch in "abcdefghijklmno":
            cells.extend([ch, ch, ch, ch])
        return cells
    elif page_num == 2:
        cells = []
        for ch in "pqrstuvwxyz":
            cells.extend([ch, ch, ch, ch])
        return cells
    elif page_num == 3:
        cells = []
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            cells.extend([ch, ch])
        return cells
    elif page_num == 4:
        cells = []
        for d in "0123456789":
            cells.extend([d, d, d])
        punct = [".", ",", "!", "?", "'", '"', "-", ":", ";", "(", ")", "/", "@", "&", "#", "$"]
        for p in punct:
            cells.extend([p, p])
        bigrams = ["th", "he", "in", "an", "er", "on", "ed", "re", "ou", "es",
                    "ti", "at", "st", "en", "or", "ng", "ing", "the", "and", "tion"]
        cells.extend(bigrams)
        return cells
    return []


def draw_square_marker(c, x, y, size=14):
    """Simple filled square with inner white square — like Calligraphr."""
    c.setFillColor(MARKER_COLOR)
    c.rect(x - size/2, y - size/2, size, size, fill=1, stroke=0)
    inner = size * 0.5
    c.setFillColor(white)
    c.rect(x - inner/2, y - inner/2, inner, inner, fill=1, stroke=0)
    c.setFillColor(MARKER_COLOR)
    dot = size * 0.18
    c.rect(x - dot/2, y - dot/2, dot, dot, fill=1, stroke=0)


def draw_page(c, page_num, total_pages, config, cells):
    cols = config["cols"]
    rows = config["rows"]
    cell_w = GRID_W / cols
    cell_h = GRID_H / rows

    # Corner markers
    m = 0.28 * inch
    draw_square_marker(c, m, PAGE_H - m)
    draw_square_marker(c, PAGE_W - m, PAGE_H - m)
    draw_square_marker(c, m, m)
    draw_square_marker(c, PAGE_W - m, m)

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(HEADER_COLOR)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 0.38 * inch, "InkClone")

    c.setFont("Helvetica", 9)
    c.setFillColor(Color(0.35, 0.35, 0.35))
    c.drawCentredString(PAGE_W / 2, PAGE_H - 0.55 * inch, config["title"])

    c.setFont("Helvetica", 7)
    c.setFillColor(Color(0.45, 0.45, 0.45))
    c.drawCentredString(PAGE_W / 2, PAGE_H - 0.7 * inch, config["subtitle"])

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(HEADER_COLOR)
    c.drawRightString(PAGE_W - 0.55 * inch, PAGE_H - 0.38 * inch, f"{page_num}/{total_pages}")

    # Grid lines
    c.setStrokeColor(CELL_BORDER)
    c.setLineWidth(0.4)

    for row in range(rows + 1):
        y = GRID_Y_TOP - row * cell_h
        c.line(GRID_X, y, GRID_X + cols * cell_w, y)

    for col in range(cols + 1):
        x = GRID_X + col * cell_w
        c.line(x, GRID_Y_TOP, x, GRID_Y_TOP - rows * cell_h)

    # Cell labels — tiny, top-left corner only
    for idx, label in enumerate(cells):
        col = idx % cols
        row = idx // cols
        if row >= rows:
            break

        x = GRID_X + col * cell_w
        y_top = GRID_Y_TOP - row * cell_h

        c.setFont("Helvetica", 5.5)
        c.setFillColor(LABEL_COLOR)
        c.drawString(x + 2.5, y_top - 8, label)

    # Gray out empty cells
    total_used = len(cells)
    total_cells = cols * rows
    if total_used < total_cells:
        c.setFillColor(Color(0.93, 0.93, 0.93))
        for idx in range(total_used, total_cells):
            col = idx % cols
            row = idx // cols
            x = GRID_X + col * cell_w
            y_bot = GRID_Y_TOP - (row + 1) * cell_h
            c.rect(x + 0.5, y_bot + 0.5, cell_w - 1, cell_h - 1, fill=1, stroke=0)

    # Footer
    c.setFont("Helvetica", 5.5)
    c.setFillColor(FOOTER_COLOR)
    c.drawCentredString(PAGE_W / 2, 0.2 * inch,
        "InkClone Template v6  |  BLACK ballpoint pen  |  "
        "Write BIG in the center of each cell  |  Don't touch borders  |  "
        "Photograph flat with native camera, NOT CamScanner")


def build_template(output_path):
    c = canvas.Canvas(output_path, pagesize=letter)
    c.setTitle("InkClone Handwriting Template v6")
    c.setAuthor("InkClone")

    total_pages = len(PAGE_CONFIGS)
    total_cells = 0

    for i, config in enumerate(PAGE_CONFIGS):
        cells = get_page_cells(i + 1)
        total_cells += len(cells)
        draw_page(c, i + 1, total_pages, config, cells)
        c.showPage()

    c.save()

    print(f"Template v6 saved to: {output_path}")
    for i, config in enumerate(PAGE_CONFIGS):
        cols, rows = config["cols"], config["rows"]
        cw = GRID_W / cols
        ch = GRID_H / rows
        cells = get_page_cells(i + 1)
        print(f"  Page {i+1}: {cols}x{rows}, cell {cw/inch:.2f}\" x {ch/inch:.2f}\", {len(cells)} cells")
    print(f"  Total: {total_cells} cells")
    print(f"  Style: Calligraphr-minimal (no guides, no zones, tiny labels)")


if __name__ == "__main__":
    build_template("inkclone_template_v6.pdf")
