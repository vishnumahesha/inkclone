#!/usr/bin/env python3
"""
generate_synthetic.py — Produce 4 synthetic InkClone template PNGs for pipeline testing.

Each page is 2550×3300 (white background) with:
  - 1px blue grid lines at cell boundaries
  - 1px blue baseline at BASELINE_RATIO of cell height
  - Small blue cell-label text (top-left of cell)
  - Black character centered on baseline at 55–65% of cell height
  - Empty cells: grid + baseline only

Saves to tests/synthetic/page{1-4}.png and manifest.json.
Also saves a thumbnail contact-sheet at tests/synthetic/contact_sheet_thumb.png.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from template_config import (
    WARP_W, WARP_H,
    MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM,
    PAGE_GRIDS, BLUE_LINE_COLOR, BASELINE_RATIO,
    cell_dims, label_to_display, PAGE_MAPS,
)

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = ROOT / "tests" / "synthetic"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Character height as fraction of cell height
CHAR_HEIGHT_FRAC = 0.58   # 58% → between 55% and 65%


def find_font():
    candidates = [
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/ArialHB.ttc",
        "/System/Library/Fonts/Avenir Next.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/Library/Fonts/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def fit_font(font_path, text, target_px, max_tries=30):
    """Return an ImageFont sized so the rendered text height ≈ target_px."""
    size = max(8, int(target_px * 0.8))
    if font_path is None:
        return ImageFont.load_default()
    for _ in range(max_tries):
        try:
            f = ImageFont.truetype(font_path, size)
        except Exception:
            return ImageFont.load_default()
        # Use getbbox for accurate height measurement
        try:
            bb = f.getbbox(text)
            h = bb[3] - bb[1]
        except Exception:
            h = size
        if h >= target_px:
            break
        size = int(size * (target_px / max(1, h)) * 1.05)
    return f


def draw_page(page: int, cells: list, font_path: str | None) -> tuple[Image.Image, list]:
    """
    Draw a single template page. Returns (image, manifest_entries).
    manifest_entries: list of dicts per non-empty cell.
    """
    cols, rows = PAGE_GRIDS[page]
    cw, ch = cell_dims(page)

    img = Image.new("RGB", (WARP_W, WARP_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Target char height in pixels
    char_h_px = int(ch * CHAR_HEIGHT_FRAC)

    # Small label font (top-left of each cell)
    try:
        label_font = (ImageFont.truetype(font_path, 16) if font_path
                      else ImageFont.load_default())
    except Exception:
        label_font = ImageFont.load_default()

    manifest = []

    for idx, cell in enumerate(cells):
        col = idx % cols
        row = idx // cols
        if row >= rows:
            break

        # Cell bounding box in image coordinates
        x0 = MARGIN_LEFT + int(col * cw)
        y0 = MARGIN_TOP  + int(row * ch)
        x1 = MARGIN_LEFT + int((col + 1) * cw)
        y1 = MARGIN_TOP  + int((row + 1) * ch)

        # Draw cell border (1px blue)
        draw.rectangle([x0, y0, x1, y1], outline=BLUE_LINE_COLOR, width=1)

        # Baseline y
        baseline_y = y0 + int(ch * BASELINE_RATIO)
        draw.line([(x0 + 1, baseline_y), (x1 - 1, baseline_y)],
                  fill=BLUE_LINE_COLOR, width=1)

        label = cell['label']
        variant = cell['variant']

        if label is None:
            continue   # empty cell — grid + baseline only

        display = label_to_display(label)

        # Draw small label (top-left, blue)
        draw.text((x0 + 4, y0 + 2), label[:6], fill=BLUE_LINE_COLOR, font=label_font)

        # Render character in black, centered horizontally, bottom on baseline
        char_font = fit_font(font_path, display, char_h_px)

        try:
            bb = char_font.getbbox(display)
            tw = bb[2] - bb[0]
            th = bb[3] - bb[1]
        except Exception:
            tw, th = char_h_px // 2, char_h_px

        # Center horizontally in cell; baseline = bottom of glyph
        cx = x0 + int(cw // 2) - tw // 2 - bb[0]
        # Position so text bottom aligns with baseline
        cy = baseline_y - th - bb[1]

        draw.text((cx, cy), display, fill=(0, 0, 0), font=char_font)

        manifest.append({
            "page":    page,
            "cell":    idx,
            "row":     row,
            "col":     col,
            "label":   label,
            "variant": variant,
            "display": display,
        })

    return img, manifest


def make_thumbnail(img: Image.Image, max_w: int = 700) -> Image.Image:
    """Resize image maintaining aspect ratio so width ≤ max_w."""
    w, h = img.size
    scale = max_w / w
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def main():
    font_path = find_font()
    print(f"Font: {font_path or '(PIL default)'}")

    all_manifest = []
    thumbs = []

    for page in [1, 2, 3, 4]:
        cells = PAGE_MAPS[page]()
        img, entries = draw_page(page, cells, font_path)

        out_path = OUT_DIR / f"page{page}.png"
        img.save(str(out_path))
        content_count = len(entries)
        print(f"Page {page}: saved {out_path.name}  ({content_count} content cells)")

        all_manifest.extend(entries)
        thumbs.append(make_thumbnail(img, max_w=600))

    # Save manifest
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(all_manifest, indent=2))
    print(f"Manifest: {manifest_path}  ({len(all_manifest)} entries)")

    # Contact-sheet thumbnail (2×2 grid of page thumbnails)
    tw, th = thumbs[0].size
    sheet = Image.new("RGB", (tw * 2 + 4, th * 2 + 4), (200, 200, 200))
    positions = [(0, 0), (tw + 4, 0), (0, th + 4), (tw + 4, th + 4)]
    for thumb, pos in zip(thumbs, positions):
        sheet.paste(thumb, pos)

    sheet_path = OUT_DIR / "contact_sheet_thumb.png"
    sheet.save(str(sheet_path))
    print(f"Thumbnail contact sheet: {sheet_path}  size={sheet.size}")

    # Verify no image loaded >2000px (thumbnails are ~600×780)
    print(f"\nAll done. Synthetic images at {OUT_DIR}")
    print(f"Total manifest entries: {len(all_manifest)}  (expected 238)")


if __name__ == "__main__":
    main()
