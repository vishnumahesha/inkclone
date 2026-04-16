"""
Task 1: Fix Glyph Alpha Channel
Scan all PNGs in profiles/freeform_vishnu/glyphs/
Scale alpha so max alpha = 240 (if not already)
"""
from pathlib import Path
from PIL import Image
import numpy as np

GLYPH_DIR = Path(__file__).parent / "profiles" / "freeform_vishnu" / "glyphs"


def fix_alpha():
    png_files = sorted(GLYPH_DIR.glob("*.png"))
    if not png_files:
        print(f"No PNG files found in {GLYPH_DIR}")
        return

    print(f"Scanning {len(png_files)} glyphs in {GLYPH_DIR}\n")
    print(f"{'Filename':<35} {'OldMax':>7} {'NewMax':>7} {'Action':<12}")
    print("-" * 65)

    processed = 0
    skipped = 0

    for png_path in png_files:
        img = Image.open(png_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        arr = np.array(img, dtype=np.float64)
        alpha = arr[:, :, 3]
        old_max = int(alpha.max())

        if old_max == 0:
            print(f"{png_path.name:<35} {old_max:>7} {'---':>7} {'SKIP (blank)':<12}")
            skipped += 1
            continue

        if old_max == 240:
            print(f"{png_path.name:<35} {old_max:>7} {240:>7} {'already ok':<12}")
            skipped += 1
            continue

        # Scale alpha so max becomes 240
        new_alpha = (alpha / old_max) * 240.0
        arr[:, :, 3] = np.clip(new_alpha, 0, 255)
        out = Image.fromarray(arr.astype(np.uint8), "RGBA")
        out.save(png_path)
        new_max = int(np.clip(new_alpha, 0, 255).max())
        print(f"{png_path.name:<35} {old_max:>7} {new_max:>7} {'FIXED':<12}")
        processed += 1

    print("-" * 65)
    print(f"\nTotal: {len(png_files)} files | Fixed: {processed} | Skipped: {skipped}")


if __name__ == "__main__":
    fix_alpha()
