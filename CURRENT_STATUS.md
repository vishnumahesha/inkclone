# InkClone Status — 2026-04-27

## What Works

- Full extraction pipeline (v7): Hough line corner detection → perspective warp → sharpen → min-channel ink extraction → morphological grid-line removal → autocrop → RGBA glyph PNG
- Synthetic template test: **238/238** (100%) — pipeline is structurally sound
- Glyph review page (`/review`), 4-page upload wizard (`/setup`), and render page all functional
- All 16 render sliders working (font size, spacing, slant, pressure, fatigue, etc.)
- 5 presets, 7 paper backgrounds, 6 ink colors, 3 artifact modes
- Auto-deploy from GitHub push → Railway
- Two profiles available on live site: `vishnu_blue_v1` (234 glyphs) and `vishnu_blue_v7_hough_fix` (212 glyphs)

## Current Quality

**Best profile: `vishnu_blue_v7_hough_fix` — 212 glyphs**

| Category         | Glyphs | Notes                             |
|-----------------|--------|-----------------------------------|
| Lowercase a–z    | 96     | Many with only 1–2 good variants  |
| Uppercase A–Z    | 52     | Most present, low ink density     |
| Digits 0–9       | 30     | Best quality category             |
| Punctuation      | 14     | Mixed quality                     |
| Bigrams          | 20     | Mostly tiny, some unusable        |

**Render readability: 3/10**  
**Handwriting realism: 2/10**  
**Character coverage: 78/98 meaningful glyphs (rest are artifacts)**

The renders are currently faint, difficult to read, and have residual horizontal line artifacts from template guide lines.

## Root Cause of Poor Quality (Honest Assessment)

The extraction pipeline is now **correct** — it successfully filters blue guide lines via min-channel binarization and removes detected grid lines morphologically. Synthetic tests pass perfectly.

The real problem is **input photo quality**:

1. **Low-resolution photos**: Template photos are ~913×1100px (compressed via chat upload). The warp target is 2550×3300 — a **2.75× upscale**. This causes:
   - JPEG compression artifacts blur into the ink detection range
   - Blue guide line pixels bleed into adjacent cells during interpolation
   - Thin ink strokes become fuzzy gray gradients indistinguishable from background noise
   - Result: 83/212 glyphs have <3% ink coverage (bounding box set by edge artifacts, not actual character)

2. **Pages 3–4 written in pencil**: Uppercase A–Z and digits/punctuation pages were filled with pencil. Pencil ink (R≈140–155) is nearly indistinguishable from paper and guide lines at this resolution. All 52 uppercase glyphs have ink coverage of 3–8% — borderline usable.

3. **Some lowercase cells faint**: Several lowercase characters (e, i, s, v) have only 1 clean glyph variant out of 4, because 3 cells were written too lightly or the ink was too faint after JPEG compression.

## User Requirements for Good Results

| Requirement | Current | Needed |
|-------------|---------|--------|
| Photo resolution | 913×1100 (compressed) | 4032×3024 (iPhone native, AirDrop) |
| Photo angle | OK (Hough corrects ≤10°) | OK |
| Pen type | Pencil on pages 3–4 | **Black ballpoint on ALL 4 pages** |
| Lighting | Mixed | Even, shadow-free |

**Critical user action needed:**
1. **Reprint pages 3 and 4** (uppercase and digits) and fill with black ballpoint pen — pencil does not work
2. **AirDrop all 4 photos** directly from iPhone (do not upload through chat or Messages — this compresses them). Photos should be ~5–8 MB each.
3. Upload to `/setup` on the live site and extract as a new profile

With full-resolution, black-pen photos, the extraction pipeline is expected to produce glyphs with 10–25% ink coverage and clean bounding boxes, yielding readable, realistic handwriting renders.

## Architecture

```
upload (4 photos, one per page)
  → _auto_deskew (Hough lines, ≤10° correction)
  → _normalize_brightness (local mean normalization)
  → _reduce_noise (Gaussian blur)
  → _find_corners (Hough line grid detection → extrapolate page corners)
       fallback: largest dark blob per quadrant
  → _perspective_warp (to 2550×3300)
  → _enhance_red_channel (CLAHE on red channel)
  → _sharpen (unsharp mask)
  → per-cell extraction:
      → _extract_glyph_cell(warped_bgr, col, row, …)
          → 8% cell inset (removes printed grid edge lines)
          → 15% label zone whiteout (removes printed character labels)
          → min-channel binarization: pixel is ink if min(R,G,B) < 100
          → morphological OPEN (2×2 kernel, removes isolated noise)
          → morphological line removal (H-span ≥60%, V-span ≥60% → subtract)
          → connected-component noise removal (area < 12px → remove)
          → autocrop to ink bounding box + 4px padding
          → RGBA PNG (black ink on transparent background)
          → fallback: adaptive threshold on red channel if <35 ink pixels found
```

**Config**: `template_config.py` (single source of truth for grid dimensions)  
**Validation**: `tests/validate_extraction.py` + `tests/synthetic/` (238/238 required)

## What Was Fixed in This Session

1. **Corner detection** (v7): Replaced broken blob-based detection with Hough line detection on the cell grid border. Hough extrapolates full-page corners from grid bounds using known margin ratios. Fallback to blob detection for pages where Hough fails.

2. **Cell inset** (v7): Corrected from 3% to 8% (matching `CELL_INSET` constant) — this was leaving the printed grid line inside the extracted cell.

3. **Ink extraction** (v7): Replaced red-channel threshold with `min(R,G,B) < 100` — blue guide lines have `min ≈ 150` so are correctly excluded. Followed by morphological line removal.

4. **Bad glyphs cleaned**: Deleted 26 glyphs from `vishnu_blue_v7_hough_fix` with aspect ratios >4.0 (these were pure horizontal line artifacts).

5. **Synthetic test** verified: 238/238 after all changes.

## Next Steps to Improve Quality

**Priority 1 (blocks everything else):** AirDrop full-resolution iPhone photos and re-extract.  
Expected improvement: renders go from 3/10 → 7/10 readability.

**Priority 2:** Reprint and re-fill pages 3–4 with black ballpoint pen.  
Expected improvement: uppercase and digits become usable.

**Priority 3:** For the 15 lowercase chars with only 1 variant, consider refilling those specific cells on a supplemental template page.

**Priority 4 (code):** After getting good photos, consider:
- Lowering the min-channel threshold from 100 to 80 for improved ink sensitivity on good photos
- Tightening the bounding box using ink-density trimming (remove columns/rows with <2 ink pixels) to eliminate artifact-bloated bounding boxes
- Adding glyph width normalization to prevent outlier-sized glyphs from distorting word spacing
