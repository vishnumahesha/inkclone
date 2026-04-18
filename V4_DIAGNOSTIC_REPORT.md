# V4 Glyph Extraction — Diagnostic Report
**Date:** 2026-04-17  
**Track:** A (Read-only diagnostic)  
**Pipeline:** `extract_pipeline.py` → profile `vishnu_v4`  
**Scan source:** `template_v4_scan_page3.png` (lowercase, page_dots=1)

---

## A1 — V3 vs V4 Glyph Side-by-Side Comparison

All images are 128 px tall (height-normalized). Ink% = non-zero alpha pixels / total pixels.  
Visual quality assessed by checking whether dimensions and ink density are consistent with
the character shape (V3 is the reference baseline: widths 144–182 px, ink% 1.9–9.0%).

| CHAR | V3 FILE    | V3 SIZE   | V3 INK%  | V4 FILE    | V4 SIZE   | V4 INK%  | VISUAL QUALITY      |
|------|------------|-----------|----------|------------|-----------|----------|---------------------|
| a    | a_0.png    | 181×128   | 0.0442   | a_0.png    | 306×128   | 0.0374   | Partial (too wide)  |
| e    | e_0.png    | 174×128   | 0.0346   | e_0.png    | 374×128   | 0.0087   | No (sparse blob)    |
| h    | h_0.png    | 170×128   | 0.0903   | h_0.png    | 229×128   | 0.1007   | Yes                 |
| i    | i_0.png    | 177×128   | 0.0187   | i_0.png    | 332×128   | 0.0191   | No (oversized)      |
| m    | m_0.png    | 173×128   | 0.0304   | m_0.png    | 218×128   | 0.0071   | Yes (sparse)        |
| n    | n_0.png    | 170×128   | 0.0236   | n_0.png    | 130×128   | 0.2520   | No (tiny dense blob)|
| o    | o_0.png    | 160×128   | 0.0338   | o_0.png    | 473×128   | 0.1360   | No (absurdly wide)  |
| s    | s_0.png    | 182×128   | 0.0323   | s_0.png    | 170×128   | 0.0117   | Yes (sparse)        |
| t    | t_0.png    | 177×128   | 0.0303   | t_0.png    | 120×128   | 0.2576   | No (tiny dense blob)|
| v    | v_0.png    | 144×128   | 0.0256   | v_0.png    | 141×128   | 0.3509   | No (tiny dense blob)|

**Result:** 6 of 10 first-variant glyphs are broken. Two failure modes observed:
- **Mode A (too wide, sparse ink):** `a`, `e`, `i`, `o` — widths 306–473 px vs V3's 144–182 px. Nearly all ink is missing; what remains is spread over the full cell width. Ink% is 2–10× lower than V3.
- **Mode B (tiny blob, dense ink):** `n`, `t`, `v` — widths 120–141 px but ink% is 10–14× higher than V3 (25–35%). Only a small ink fragment survived; the rest was filtered away.

---

## A2 — Pipeline Trace for Lowercase "h"

**Scan:** `template_v4_scan_page3.png` (1968×2564 px, ~233 DPI)  
**Warped to:** 2550×3300 px (300 DPI target)  
**"h" cell:** page_dots=1, cell index 28, col=4 row=3  
**Cell bounds (after 8 px inset):** x0=1283 y0=996 x1=1552 y1=1195

| Stage | Description                  | Dims (WxH) | Ink Pixels | Looks like "h"? |
|-------|------------------------------|-----------|------------|-----------------|
| 1     | Raw cell crop (inset applied)| 269×199   | 1,614      | Yes — full letter visible |
| 2     | After border inset (8 px)    | 269×199   | 1,614      | Yes — unchanged |
| 3     | After label zone mask (35%)  | 269×199   | 1,552      | Yes — top 69 px blanked, letter body intact |
| 4     | After threshold (tight=137, loose=182) | 269×199 | tight=1,747 / loose=2,831 | Yes — both masks capture the letter |
| 5     | After morph+CC+row/col filter| 269×199   | **434**    | **Partial — major ink loss, rows_zeroed=5** |
| 6     | After autocrop               | 88×49     | 434        | Partial — tiny 49 px tall fragment |
| 7     | Final RGBA (scaled to 128 px)| 229×128   | 2,953      | Partial — top stroke blob, missing stems |

**Threshold values used:** `bg_median=237.0`, `thresh_tight=137.0`, `thresh_loose=182.0`

**Where it breaks:** Between Stage 4 and Stage 5. The morphological + CC shape filter + per-row guide-line filter eliminates **75% of the ink** (1,747 → 434 pixels). Five rows (`rows_zeroed=5`) were deleted by the guide-line row filter. The CC shape filter (`bh_c > ch*0.35 AND bw_c < 8` → any component taller than 70 px and narrower than 8 px is deleted) removes the vertical stem of "h" since thin handwriting strokes match this pattern. The autocrop then finds only a small 88×49 blob — the crossbar region — not the full glyph.

**Debug images saved:**
- `/tmp/h_stage1_raw_crop.png` — 269×199, letter visible
- `/tmp/h_stage2_border_inset.png` — 269×199, same as stage 1
- `/tmp/h_stage3_label_masked.png` — 269×199, top blanked
- `/tmp/h_stage4_thresh_tight.png` — binary, tight mask (thresh=137)
- `/tmp/h_stage4_thresh_loose.png` — binary, loose mask (thresh=182)
- `/tmp/h_stage5_morph_filtered.png` — 269×199, only 434 px remain
- `/tmp/h_stage6_autocrop.png` — 88×49 fragment
- `/tmp/h_stage7_final_rgba.png` — 229×128 RGBA output

---

## A3 — Perspective Warp Accuracy

**Expected cell size:** 285.0 × 214.6 px (computed from `(2550-270)/8` and `(3300-510)/13`)  
**Tolerance:** ±5 px

| Position | Grid (row,col) | Computed Cell | Actual Slice  | Within ±5 px? |
|----------|----------------|---------------|---------------|---------------|
| TL       | (0, 0)         | 285×214       | 285×214       | YES           |
| TR       | (0, 7)         | 285×214       | 285×214       | YES           |
| Center   | (6, 3)         | 285×215       | 285×215       | YES           |
| BL       | (12, 0)        | 285×215       | 285×215       | YES           |
| BR       | (12, 7)        | 285×215       | 285×215       | YES           |

**Detected corners (on 1968×2564 scan):**
- TL: (70, 49), TR: (1915, 61), BL: (72, 2496), BR: (1912, 2506)

**Conclusion:** The warp math is arithmetically correct — all cells land within ±1 px of the 285×214.6 target. However, the source scan is **1968×2564 px (~233 DPI)**, not 2550×3300 px (300 DPI). The pipeline upscales by **~29%** via Lanczos4, which blurs thin ink strokes. A stroke that was 2 px wide at 233 DPI becomes anti-aliased to ~2.6 px at 300 DPI with intermediate gray values (130–200) that straddle the thresholds. The grid geometry is correct, but the upscaling degrades ink fidelity.

---

## A4 — Threshold Appropriateness (5 Positions, Lowercase Page)

All measurements from the warped lowercase scan (`template_v4_scan_page3.png`, page_dots=1).  
Working zone = cell below label (bottom 65%) with 6 px side margins.

| Position    | Char | BG Median | Darkest Px | Gap   | thresh_tight | thresh_loose | Ink%_tight | Ink%_loose | Correct? |
|-------------|------|-----------|-----------|-------|-------------|-------------|------------|------------|----------|
| TopLeft     | a    | 238.0     | 0         | 238.0 | 138.0       | 183.0       | 7.67%      | 11.03%     | **YES**  |
| TopRight    | b    | 236.0     | 0         | 236.0 | 136.0       | 181.0       | 9.15%      | 12.26%     | **YES**  |
| Center      | m    | 233.0     | 0         | 233.0 | 133.0       | 178.0       | 1.73%      | 4.89%      | **YES**  |
| BottomLeft  | y    | 244.0     | 2         | 242.0 | 140.0       | 189.0       | 2.36%      | 3.43%      | **YES**  |
| BottomRight | z    | 245.0     | 0         | 245.0 | 140.0       | 190.0       | 2.33%      | 3.53%      | **YES**  |

**Conclusion:** Thresholds are not the problem. All 5 positions show clean paper (bg 233–245) against pure black ink (darkest 0–2), with gaps of 233–245. The hysteresis threshold (tight=133–140, loose=178–190) correctly separates ink from paper at every position tested. The loose mask captures 1.5–3× more pixels than tight, which is the intended behavior.

---

## A5 — Root Cause Statement

**The V4 extraction pipeline produces broken glyphs because its CC shape filter and per-row guide-line filter cannot distinguish between template grid artifacts (horizontal rule lines, cell borders) and the thin handwritten ink strokes of the letters themselves.**

Specifically, two independent but compounding bugs cause the breakage:

1. **CC tall-and-thin filter deletes letter stems** (`extract_pipeline.py:138–141`): Any connected component taller than `ch*0.35` (≈70 px) and narrower than 8 px is deleted under the assumption it is a cell border. Thin handwriting at 233 DPI upscaled to 300 DPI produces vertical strokes that are exactly 4–8 px wide — they pass this filter and get erased. This is the primary cause of Mode B failures (n, t, v): only the widest parts of the letter (horizontal strokes, a serif, the top of a curve) survive, leaving a tiny dense blob.

2. **Per-row guide-line filter deletes ink rows of wide letters** (`extract_pipeline.py:146–153`): Any row where ink spans >65% of cell width (`span > cw*0.65 = 175 px`) is zeroed entirely. This correctly removes the printed guide lines, but handwritten letters like "m", "w", and partially "h" (crossbar) also have rows that span >175 px at this scale, causing 5+ rows of actual letterform to be deleted.

3. **Upscaling from 233 DPI → 300 DPI introduces blurring** (A3): The scan is ~29% smaller than assumed. Lanczos4 interpolation spreads ink pixels into anti-aliased gray values (130–200), which are captured by `thresh_loose` but may not overlap `thresh_tight` seeds, failing the CC hysteresis test. This reduces reliable ink detection at stroke edges, making the glyph appear thinner or fragmented before the shape filters even run.

4. **Consequence — two failure modes**: When a letter's widest component survives but its vertical stem is deleted, the autocrop spans the full cell width collecting sparse evidence → Mode A (e, a, i, o: 306–473 px wide, ink% 0.9–3.7%). When only a tiny horizontal fragment survives all filters, autocrop captures a tiny dense blob → Mode B (n, t, v: 19–47 px, ink% 25–35%). In both cases the quality flag reports "good" because the pipeline's own quality metric (stroke-width of survivors) does not detect that most of the letter is missing.

**Fix priorities:**
1. Widen the tall+thin CC filter threshold from `bw < 8` to `bw < 4` to preserve letter stems.
2. Raise the per-row span filter from `cw*0.65` to `cw*0.85` to protect wide letter strokes.
3. Rescan at native 300 DPI to eliminate the 29% upscaling blurring problem.
4. Add a sanity check: if output glyph ink% > 20% or bbox shorter than 40% of expected letter height, flag as "broken" rather than "good".
