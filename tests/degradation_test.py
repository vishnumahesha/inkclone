#!/usr/bin/env python3
"""
tests/degradation_test.py — 7-dimension extraction degradation test.

Imports extraction functions directly from web/app.py (no HTTP).
Applies degradations to synthetic pages, runs direct extraction
(bypassing _find_corners + _perspective_warp: synthetic pages have no corner
markers, so the warp would misalign the grid anyway).
Records {score, correct_labels, blank} per level.
Writes tests/degradation_results.json and prints a breakpoint table.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

# Import extraction internals.  Importing app.py starts the FastAPI module
# (but does not start uvicorn), loading the default glyph bank.
from app import _extract_glyph_cell, _page_cells, _page_grid   # noqa: E402
from template_config import MIN_INK_PIXELS                       # noqa: E402

MANIFEST_PATH = ROOT / "tests" / "synthetic" / "manifest.json"
SYNTHETIC_DIR = ROOT / "tests" / "synthetic"

_PAGES = [
    (SYNTHETIC_DIR / "page1_lowercase_ao.png", 1),
    (SYNTHETIC_DIR / "page2_lowercase_pz.png", 2),
    (SYNTHETIC_DIR / "page3_uppercase.png",    3),
    (SYNTHETIC_DIR / "page4_digits_punct.png", 4),
]

_MANIFEST = json.loads(MANIFEST_PATH.read_text())


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_pages() -> list[tuple[np.ndarray, int]]:
    pages = []
    for path, pg in _PAGES:
        img = cv2.imread(str(path))
        if img is None:
            raise FileNotFoundError(f"Cannot load {path}")
        pages.append((img, pg))
    return pages


def extract_direct(pages: list[tuple[np.ndarray, int]]) -> dict:
    """
    Extract glyphs directly from BGR images that are already at 2550×3300.
    Bypasses _find_corners + _perspective_warp.
    Returns bank: {display_char: [count of extracted variants]}.
    """
    bank: dict[str, list] = {}
    for img_bgr, pg in pages:
        cols, rows, ml, mt, cw, ch = _page_grid(pg)
        cells = _page_cells(pg)
        for idx, char in enumerate(cells):
            col = idx % cols
            row = idx // cols
            if row >= rows:
                break
            glyph = _extract_glyph_cell(img_bgr, col, row, ml, mt, cw, ch,
                                         char_name=char)
            if glyph is not None:
                bank.setdefault(char, []).append(glyph)
    return bank


def score_bank(bank: dict) -> tuple[int, int]:
    """
    Score bank against manifest.
    Returns (score, blank) where blank = expected glyphs not found / too small.
    """
    score = 0
    blank = 0
    for entry in _MANIFEST:
        display = entry["display"]
        variant = entry["variant"]
        glyphs = bank.get(display, [])
        if variant < len(glyphs):
            arr = np.array(glyphs[variant])
            ink_px = int((arr[:, :, 3] > 0).sum())
            if ink_px >= MIN_INK_PIXELS:
                score += 1
                continue
        blank += 1
    return score, blank


# ── Degradation functions ──────────────────────────────────────────────────────

def _degrade_resolution(img: np.ndarray, target_width: int) -> np.ndarray:
    h, w = img.shape[:2]
    if target_width >= w:
        return img
    small = cv2.resize(img, (target_width, int(h * target_width / w)),
                       interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


def _degrade_rotation(img: np.ndarray, angle_deg: float) -> np.ndarray:
    if angle_deg == 0:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=(255, 255, 255))


def _degrade_lighting(img: np.ndarray, factor: float) -> np.ndarray:
    if factor == 1.0:
        return img
    return (img.astype(np.float32) * factor).clip(0, 255).astype(np.uint8)


def _degrade_noise(img: np.ndarray, std: float) -> np.ndarray:
    if std == 0:
        return img
    noise = np.random.normal(0, std, img.shape).astype(np.float32)
    return (img.astype(np.float32) + noise).clip(0, 255).astype(np.uint8)


def _degrade_jpeg(img: np.ndarray, quality: int) -> np.ndarray:
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _degrade_ink_lightness(img: np.ndarray, fraction: float) -> np.ndarray:
    """
    Lighten ink pixels by fraction (0=unchanged, 0.9=90% lighter).
    Ink detected by red channel < 128 (black ink has R≈30).
    """
    if fraction == 0:
        return img
    result = img.astype(np.float32)
    ink_mask = result[:, :, 2] < 128  # BGR: index 2 = red
    for c in range(3):
        ch = result[:, :, c]
        ch[ink_mask] = ch[ink_mask] + fraction * (255.0 - ch[ink_mask])
        result[:, :, c] = ch
    return result.clip(0, 255).astype(np.uint8)


def _apply(pages, fn) -> list[tuple[np.ndarray, int]]:
    return [(fn(img), pg) for img, pg in pages]


# ── Dimension definitions ──────────────────────────────────────────────────────

DIMENSIONS: dict[str, dict] = {
    "A_resolution": {
        "label": "Resolution (px wide)",
        "levels": [2550, 2000, 1600, 1200, 800, 400],
        "fn": lambda v: (lambda img: _degrade_resolution(img, v)),
    },
    "B_rotation": {
        "label": "Rotation (degrees)",
        "levels": [0, 0.5, 1, 2, 4, 8],
        "fn": lambda v: (lambda img: _degrade_rotation(img, v)),
    },
    "C_lighting": {
        "label": "Brightness factor",
        "levels": [1.0, 0.85, 0.7, 0.55, 0.4, 0.25],
        "fn": lambda v: (lambda img: _degrade_lighting(img, v)),
    },
    "D_noise": {
        "label": "Gaussian noise std",
        "levels": [0, 5, 10, 20, 40, 80],
        "fn": lambda v: (lambda img: _degrade_noise(img, v)),
    },
    "E_jpeg": {
        "label": "JPEG quality",
        "levels": [100, 90, 80, 70, 60, 50],
        "fn": lambda v: (lambda img: _degrade_jpeg(img, v)),
    },
    "F_ink_lightness": {
        "label": "Ink lightness fraction",
        "levels": [0.0, 0.1, 0.3, 0.5, 0.7, 0.9],
        "fn": lambda v: (lambda img: _degrade_ink_lightness(img, v)),
    },
}


def _run_combined(pages):
    """G: apply A-level-3 + B-level-3 + D-level-3 + F-level-3."""
    imgs = _apply(pages, lambda img: _degrade_resolution(img, 1200))  # A lv3
    imgs = _apply(imgs,  lambda img: _degrade_rotation(img, 2))        # B lv3
    imgs = _apply(imgs,  lambda img: _degrade_noise(img, 20))           # D lv3
    imgs = _apply(imgs,  lambda img: _degrade_ink_lightness(img, 0.5))  # F lv3
    return imgs


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_all() -> dict:
    np.random.seed(42)
    base_pages = load_pages()

    # Verify baseline
    base_bank = extract_direct(base_pages)
    base_score, base_blank = score_bank(base_bank)
    print(f"Baseline: {base_score}/238  blank={base_blank}")
    if base_score != 238:
        print(f"ERROR: baseline must be 238/238, got {base_score}/238 — aborting")
        sys.exit(1)

    results: dict = {}

    for dim_key, dim in DIMENSIONS.items():
        print(f"\n{dim_key}: {dim['label']}")
        dim_results = []
        for lv_idx, lv_val in enumerate(dim["levels"]):
            degraded = _apply(base_pages, dim["fn"](lv_val))
            bank = extract_direct(degraded)
            sc, bl = score_bank(bank)
            print(f"  [{lv_idx}] {lv_val!s:>6}: {sc:3d}/238  blank={bl}")
            dim_results.append({
                "level_idx":      lv_idx,
                "level_value":    lv_val,
                "score":          sc,
                "correct_labels": sc,
                "blank":          bl,
            })
        results[dim_key] = dim_results

    # Combined
    print("\nG_combined (A3+B3+D3+F3):")
    comb_pages = _run_combined(base_pages)
    comb_bank  = extract_direct(comb_pages)
    sc, bl = score_bank(comb_bank)
    print(f"  {sc}/238  blank={bl}")
    results["G_combined"] = [{
        "level_idx":      0,
        "level_value":    "A3+B3+D3+F3",
        "score":          sc,
        "correct_labels": sc,
        "blank":          bl,
    }]

    # Write results
    out_path = ROOT / "tests" / "degradation_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")

    # Breakpoint table
    print("\n=== BREAKPOINT TABLE (first level < 200/238) ===")
    for dim_key, dim_results in results.items():
        if dim_key == "G_combined":
            continue
        bp = next((r for r in dim_results if r["score"] < 200), None)
        label = DIMENSIONS[dim_key]["label"]
        if bp:
            print(f"  {dim_key:20s}  lv{bp['level_idx']} ({bp['level_value']!s:<6}) → {bp['score']}/238")
        else:
            print(f"  {dim_key:20s}  no breakpoint (all ≥ 200/238)")
    cg = results["G_combined"][0]
    print(f"  G_combined            combined     → {cg['score']}/238")

    return results


if __name__ == "__main__":
    run_all()
