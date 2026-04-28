"""
generate_filled_test_pages.py — Generate filled synthetic test pages for InkClone.

Produces test_page1.png … test_page4.png in tests/synthetic/.
Each page is 2550×3300 (letter @ 300 Dpi), showing:
  - Blue grid lines / baselines (matching template_config.py)
  - Blue corner markers
  - Blue cell labels (top-left of each cell, tiny)
  - BLACK Helvetica-style characters drawn in each cell at ~60% cell height

Usage:
    python3 tests/generate_filled_test_pages.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import template_config as tc

# ── Output dir ────────────────────────────────────────────────────────────────
OUT_DIR = os.path.join(os.path.dirname(__file__), 'synthetic')
os.makedirs(OUT_DIR, exist_ok=True)

# ── Colors ────────────────────────────────────────────────────────────────────
WHITE        = (255, 255, 255)
BLUE_GRID    = (170, 210, 255)   # same as template_config.BLUE_LINE_COLOR
BLUE_LABEL   = (120, 160, 230)   # slightly darker blue for cell labels
BLACK_INK    = (20, 20, 20)      # near-black for character strokes
BLUE_CORNER  = (100, 140, 210)   # corner marker fill

GRID_LINE_W  = 3   # pixels
BASELINE_W   = 2

def get_font(size):
    """Try to load a system monospace/sans font; fall back to default."""
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
        '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf',
        '/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf',
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def get_display_char(label):
    """Convert internal label to display character."""
    if label is None:
        return ''
    if label.startswith('upper_'):
        return label[6:]
    if label.startswith('digit_'):
        return label[6:]
    return tc.label_to_display(label)


def draw_page(page_num, cell_map):
    """Draw one filled test page and return as PIL Image."""
    W, H = tc.WARP_W, tc.WARP_H
    ml, mr = tc.MARGIN_LEFT, tc.MARGIN_RIGHT
    mt, mb = tc.MARGIN_TOP, tc.MARGIN_BOTTOM
    cols, rows = tc.PAGE_GRIDS[page_num]
    cell_w, cell_h = tc.cell_dims(page_num)
    inset = tc.CELL_INSET

    img = Image.new('RGB', (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    usable_w = W - ml - mr   # 2250
    usable_h = H - mt - mb   # 2880

    # ── Draw horizontal grid lines ────────────────────────────────────────────
    for r in range(rows + 1):
        y = int(mt + r * cell_h)
        draw.line([(ml, y), (W - mr, y)], fill=BLUE_GRID, width=GRID_LINE_W)

    # ── Draw vertical grid lines ──────────────────────────────────────────────
    for c in range(cols + 1):
        x = int(ml + c * cell_w)
        draw.line([(x, mt), (x, H - mb)], fill=BLUE_GRID, width=GRID_LINE_W)

    # ── Draw baselines (70% down each cell) ───────────────────────────────────
    bl_ratio = tc.BASELINE_RATIO
    for r in range(rows):
        y_top = mt + r * cell_h
        y_bl  = int(y_top + bl_ratio * cell_h)
        draw.line([(ml, y_bl), (W - mr, y_bl)], fill=BLUE_GRID, width=BASELINE_W)

    # ── Corner markers (10×10 blue squares) ──────────────────────────────────
    marker_sz = 18
    for cx, cy in [(ml, mt), (W - mr, mt), (ml, H - mb), (W - mr, H - mb)]:
        draw.rectangle([cx - marker_sz, cy - marker_sz,
                        cx + marker_sz, cy + marker_sz], fill=BLUE_CORNER)

    # ── Page title ────────────────────────────────────────────────────────────
    title_font = get_font(36)
    draw.text((ml, 30), f'InkClone — FILLED TEST  (Page {page_num})',
              fill=BLUE_GRID, font=title_font)

    # ── Character font sizes ──────────────────────────────────────────────────
    char_h_target = int(cell_h * 0.55)   # characters fill ~55% of cell height
    char_font = get_font(max(12, char_h_target))
    label_font = get_font(max(8, int(cell_h * 0.12)))

    # ── Draw characters in each cell ─────────────────────────────────────────
    for idx, cell_info in enumerate(cell_map):
        row = idx // cols
        col = idx % cols
        label   = cell_info['label']
        display = get_display_char(label)
        if not display:
            continue

        # Cell bounding box
        x0 = ml + col * cell_w
        y0 = mt + row * cell_h
        x1 = x0 + cell_w
        y1 = y0 + cell_h

        # Inner area (after inset)
        ix0 = x0 + inset * cell_w
        iy0 = y0 + inset * cell_h
        ix1 = x1 - inset * cell_w
        iy1 = y1 - inset * cell_h
        inner_w = ix1 - ix0
        inner_h = iy1 - iy0

        # Baseline y (70% down)
        baseline_y = y0 + bl_ratio * cell_h

        # Draw main character centered horizontally, sitting on baseline
        try:
            bbox = draw.textbbox((0, 0), display, font=char_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except AttributeError:
            tw, th = draw.textsize(display, font=char_font)

        # Center horizontally; anchor glyph BOTTOM to baseline using bbox[3]
        # bbox = (left, top, right, bottom) relative to draw origin
        # Setting ty = baseline_y - bbox[3] puts glyph bottom exactly on baseline
        tx = int(ix0 + (inner_w - (bbox[2] - bbox[0])) / 2 - bbox[0])
        ty = int(baseline_y - bbox[3])

        draw.text((tx, ty), display, fill=BLACK_INK, font=char_font)

        # Draw tiny blue label in top-left of cell (variant number)
        variant_label = f'{display}{cell_info["variant"]}'
        draw.text((int(x0 + 3), int(y0 + 3)), variant_label,
                  fill=BLUE_LABEL, font=label_font)

    return img


def main():
    page_maps = {
        1: tc.build_page1_map(),
        2: tc.build_page2_map(),
        3: tc.build_page3_map(),
        4: tc.build_page4_map(),
    }

    for page_num, cell_map in page_maps.items():
        print(f'Generating page {page_num}...', end=' ', flush=True)
        img = draw_page(page_num, cell_map)
        out_path = os.path.join(OUT_DIR, f'test_page{page_num}.png')
        img.save(out_path, 'PNG')
        print(f'saved → {out_path}  ({img.size[0]}×{img.size[1]})')

    print('\nAll 4 test pages generated.')


if __name__ == '__main__':
    main()
