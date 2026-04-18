"""
Post-process vishnu_v3_clean glyphs → vishnu_v3_final.
Uses ink-fraction-aware gap detection: only cut at gap if ink-before < 15% of total.
Falls back to pure tight bbox crop when no clean gap exists.
"""
import shutil
import sys
import numpy as np
from pathlib import Path
from PIL import Image

SRC_DIR = Path("profiles/vishnu_v3_clean/glyphs")
OUT_DIR = Path("profiles/vishnu_v3_final/glyphs")
PAD         = 4
MIN_INK     = 15
GAP_MIN_PX  = 12          # minimum gap size in rows
MAX_GAP_ROW = 0.62        # gap must start before this fraction of image height
MAX_BEFORE  = 0.15        # ink above gap must be < 15% of total (it's just a label)


def _label_gap_row(alpha: np.ndarray) -> int:
    """
    Find the row where the actual letter starts after a label gap.
    Returns 0 if no clean gap is found.
    """
    h = alpha.shape[0]
    total_ink = int((alpha > 10).sum())
    if total_ink == 0:
        return 0

    ink_rows = np.where(np.any(alpha > 10, axis=1))[0]
    if len(ink_rows) < 2:
        return 0

    for i in range(len(ink_rows) - 1):
        gap_size = int(ink_rows[i + 1]) - int(ink_rows[i])
        gap_row  = int(ink_rows[i])
        if gap_size < GAP_MIN_PX:
            continue
        if gap_row >= h * MAX_GAP_ROW:
            continue
        ink_before = int((alpha[:gap_row] > 10).sum())
        if ink_before / total_ink < MAX_BEFORE:
            return int(ink_rows[i + 1])   # start of letter region

    return 0


def process_glyph(img: Image.Image) -> Image.Image | None:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    arr   = np.array(img)
    alpha = arr[:, :, 3]
    h_raw, w_raw = alpha.shape

    start_row = _label_gap_row(alpha)
    sub_alpha  = alpha[start_row:]
    sub_arr    = arr[start_row:]

    coords = np.argwhere(sub_alpha > 10)
    if len(coords) < MIN_INK:
        return None

    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)
    y_min = max(0, y_min - PAD)
    x_min = max(0, x_min - PAD)
    y_max = min(sub_arr.shape[0] - 1, y_max + PAD)
    x_max = min(w_raw - 1, x_max + PAD)

    crop = sub_arr[y_min : y_max + 1, x_min : x_max + 1]
    new_h, new_w = crop.shape[:2]
    if new_w < 8 or new_h < 8:
        return None
    return Image.fromarray(crop, "RGBA")


def main():
    if not SRC_DIR.exists():
        print(f"Source not found: {SRC_DIR}")
        sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    saved = skipped = gap_cuts = 0
    heights = []

    for png in sorted(SRC_DIR.glob("*.png")):
        try:
            img = Image.open(png)
        except Exception as e:
            print(f"  skip {png.name}: {e}")
            skipped += 1
            continue

        # Track whether gap detection fires
        alpha_raw  = np.array(img.convert("RGBA") if img.mode != "RGBA" else img)[:, :, 3]
        start_row  = _label_gap_row(alpha_raw)
        if start_row > 0:
            gap_cuts += 1

        result = process_glyph(img)
        if result is None:
            skipped += 1
            continue

        result.save(OUT_DIR / png.name)
        heights.append(result.size[1])
        saved += 1

    src_json = SRC_DIR.parent / "profile.json"
    if src_json.exists():
        shutil.copy(src_json, OUT_DIR.parent / "profile.json")

    print(f"Saved {saved}, skipped {skipped}, gap-cuts {gap_cuts}")
    if heights:
        print(f"Height range: {min(heights)}–{max(heights)}px  mean={sum(heights)//len(heights)}px")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
