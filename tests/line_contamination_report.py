#!/usr/bin/env python3
"""
tests/line_contamination_report.py — Step 1 + Step 2 of contamination audit.

For each profile in profiles/, detect glyphs containing straight horizontal
or vertical lines spanning >60% of the glyph width/height (grid/baseline
artifacts).  Counts contamination per category and builds a contact sheet.

Writes:
  tests/line_contamination_report.json
  tests/audit_screenshots/<profile>_contamination_sheet.png  (≤1500px wide)
"""

import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PROFILES = ["vishnu_blue_v1", "vishnu_v6"]
LINE_SPAN_THRESHOLD = 0.60   # >60% width/height = contaminated
THUMB = 80                   # contact-sheet thumbnail size
SHEET_MAX_PX = 1400          # keep contact sheet ≤ 1500px wide
RANDOM_SEED  = 42


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_category(stem: str) -> str:
    if stem.startswith("upper_"):  return "uppercase"
    if stem.startswith("digit_"):  return "digits"
    punct_stems = {"period","comma","exclaim","question","apostrophe","quote",
                   "hyphen","colon","semicolon","lparen","rparen","slash",
                   "atsign","ampersand","hash","dollar"}
    bare = stem.rsplit("_", 1)[0] if "_" in stem else stem
    if bare in punct_stems:        return "punct"
    if len(bare) > 1:              return "bigrams"
    return "lowercase"


def load_ink_alpha(path: Path) -> np.ndarray | None:
    """Return alpha (ink) channel as 2-D uint8 array, or None on failure."""
    try:
        img = Image.open(path)
        if img.mode == "RGBA":
            return np.array(img)[:, :, 3]
        arr = np.array(img.convert("L"))
        return (255 - arr)          # black-on-white → ink=255
    except Exception:
        return None


def detect_lines(alpha: np.ndarray) -> dict:
    """
    Detect dominant horizontal/vertical lines in a binarized ink array.

    Returns:
        h_span     – max fraction of width covered by a single horizontal run
        v_span     – max fraction of height covered by a single vertical run
        h_line_row – row index of worst horizontal line (-1 if none)
        v_line_col – col index of worst vertical line (-1 if none)
        ink_total  – total ink pixels
        line_ink   – ink pixels attributable to the dominant line(s)
        line_ratio – line_ink / max(1, ink_total)
    """
    if alpha is None or alpha.size == 0:
        return {"h_span": 0, "v_span": 0, "h_line_row": -1, "v_line_col": -1,
                "ink_total": 0, "line_ink": 0, "line_ratio": 0.0,
                "contaminated": False}

    h, w = alpha.shape
    binary = (alpha > 0).astype(np.uint8)

    # Row-wise ink coverage
    row_ink = binary.sum(axis=1)          # (h,) — ink pixels per row
    col_ink = binary.sum(axis=0)          # (w,) — ink pixels per col

    h_span = float(row_ink.max()) / w
    v_span = float(col_ink.max()) / h

    h_line_row = int(row_ink.argmax()) if h_span > LINE_SPAN_THRESHOLD else -1
    v_line_col = int(col_ink.argmax()) if v_span > LINE_SPAN_THRESHOLD else -1

    ink_total = int(binary.sum())

    # Estimate ink that IS the line (rows/cols with near-full coverage)
    line_ink = 0
    if h_span > LINE_SPAN_THRESHOLD:
        # Count all rows with coverage > LINE_SPAN_THRESHOLD
        line_ink += int((row_ink[row_ink > w * LINE_SPAN_THRESHOLD]).sum())
    if v_span > LINE_SPAN_THRESHOLD:
        line_ink += int((col_ink[col_ink > h * LINE_SPAN_THRESHOLD]).sum())
    line_ink = min(line_ink, ink_total)

    contaminated = h_span > LINE_SPAN_THRESHOLD or v_span > LINE_SPAN_THRESHOLD

    return {
        "h_span":      round(h_span, 3),
        "v_span":      round(v_span, 3),
        "h_line_row":  h_line_row,
        "v_line_col":  v_line_col,
        "ink_total":   ink_total,
        "line_ink":    line_ink,
        "line_ratio":  round(line_ink / max(1, ink_total), 3),
        "contaminated": contaminated,
    }


# ── Per-profile analysis ───────────────────────────────────────────────────────

def analyze_profile(profile_name: str) -> dict:
    glyphs_dir = ROOT / "profiles" / profile_name / "glyphs"
    if not glyphs_dir.exists():
        return {"error": f"{glyphs_dir} not found"}

    pngs = sorted(glyphs_dir.glob("*.png"))

    cats = {c: {"total": 0, "contaminated": 0, "files": []}
            for c in ["lowercase", "uppercase", "digits", "punct", "bigrams"]}
    results = []
    worst = []   # top-10 contaminated by h_span or v_span

    for p in pngs:
        alpha = load_ink_alpha(p)
        info = detect_lines(alpha)
        cat = get_category(p.stem)
        cats[cat]["total"] += 1
        if info["contaminated"]:
            cats[cat]["contaminated"] += 1
            cats[cat]["files"].append(p.name)
        span = max(info["h_span"], info["v_span"])
        worst.append((span, p.name, info))
        results.append({"file": p.name, "category": cat, **info})

    worst.sort(key=lambda x: -x[0])
    worst10 = [{"file": w[1], "h_span": w[2]["h_span"], "v_span": w[2]["v_span"],
                "line_ratio": w[2]["line_ratio"]} for w in worst[:10]]

    total = len(pngs)
    n_contaminated = sum(c["contaminated"] for c in cats.values())

    return {
        "profile": profile_name,
        "total_glyphs": total,
        "contaminated": n_contaminated,
        "contamination_pct": round(n_contaminated / max(1, total) * 100, 1),
        "by_category": {c: {"total": d["total"],
                             "contaminated": d["contaminated"],
                             "pct": round(d["contaminated"] / max(1, d["total"]) * 100, 1),
                             "worst_files": d["files"][:5]}
                        for c, d in cats.items()},
        "worst_10": worst10,
        "all_results": results,
    }


# ── Contact sheet ──────────────────────────────────────────────────────────────

def _glyph_thumb(path: Path, size: int) -> Image.Image:
    """Return a white-background thumbnail with red outline if contaminated."""
    try:
        img = Image.open(path)
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        else:
            img = img.convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        out = Image.new("RGB", (size, size), (240, 240, 240))
        ox = (size - img.width) // 2
        oy = (size - img.height) // 2
        out.paste(img, (ox, oy))
        return out
    except Exception:
        return Image.new("RGB", (size, size), (200, 200, 200))


def build_contact_sheet(profile_name: str, results: list[dict],
                        n_samples: int = 40) -> Path:
    """
    Build a ≤1400px wide contact sheet with N random glyphs.
    Contaminated glyphs get a red border; clean ones get a green border.
    """
    rng = random.Random(RANDOM_SEED)
    glyphs_dir = ROOT / "profiles" / profile_name / "glyphs"
    out_dir = ROOT / "tests" / "audit_screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Sample: half contaminated, half clean (if enough exist)
    contam = [r for r in results if r["contaminated"]]
    clean  = [r for r in results if not r["contaminated"]]
    n_c = min(len(contam), n_samples // 2)
    n_cl = min(len(clean), n_samples - n_c)
    sample = rng.sample(contam, n_c) + rng.sample(clean, n_cl)
    rng.shuffle(sample)

    cols = SHEET_MAX_PX // (THUMB + 4)
    rows = (len(sample) + cols - 1) // cols
    sheet_w = cols * (THUMB + 4)
    sheet_h = rows * (THUMB + 20)    # +20 for label

    sheet = Image.new("RGB", (sheet_w, sheet_h), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 9)
    except Exception:
        font = ImageFont.load_default()

    for i, r in enumerate(sample):
        cx = (i % cols) * (THUMB + 4) + 2
        cy = (i // cols) * (THUMB + 20) + 2
        path = glyphs_dir / r["file"]
        thumb = _glyph_thumb(path, THUMB)
        sheet.paste(thumb, (cx, cy))

        # Border: red = contaminated, green = clean
        color = (220, 60, 60) if r["contaminated"] else (60, 180, 60)
        draw.rectangle([cx - 1, cy - 1, cx + THUMB, cy + THUMB], outline=color, width=2)

        # Label: filename stem (truncated) + span %
        stem = r["file"].replace(".png", "")[:8]
        span = max(r["h_span"], r["v_span"])
        label = f"{stem} {span:.0%}" if r["contaminated"] else stem
        draw.text((cx + 1, cy + THUMB + 2), label, fill=(200, 200, 200), font=font)

    out_path = out_dir / f"{profile_name}_contamination_sheet.png"
    sheet.save(str(out_path))
    print(f"  Saved contact sheet: {out_path} ({sheet_w}×{sheet_h})")
    return out_path


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    report = {}
    for profile in PROFILES:
        print(f"\nAnalyzing {profile} ...")
        data = analyze_profile(profile)
        print(f"  Contaminated: {data.get('contaminated', 'N/A')} / {data.get('total_glyphs', '?')} "
              f"({data.get('contamination_pct', '?')}%)")
        if "by_category" in data:
            for cat, d in data["by_category"].items():
                if d["total"] > 0:
                    print(f"    {cat:10s}: {d['contaminated']:3d}/{d['total']:3d} "
                          f"({d['pct']:5.1f}%)  "
                          + (f"worst: {d['worst_files'][:2]}" if d["worst_files"] else ""))
        if "worst_10" in data:
            print("  Worst offenders:")
            for w in data["worst_10"][:5]:
                print(f"    {w['file']:30s}  h={w['h_span']:.2f}  v={w['v_span']:.2f}  "
                      f"line_ratio={w['line_ratio']:.2f}")

        # Contact sheet
        if "all_results" in data:
            build_contact_sheet(profile, data["all_results"])
            # Strip per-glyph list from JSON (keeps file small)
            report[profile] = {k: v for k, v in data.items() if k != "all_results"}
        else:
            report[profile] = data

    out = ROOT / "tests" / "line_contamination_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out}")
    return report


if __name__ == "__main__":
    run()
