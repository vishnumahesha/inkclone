# Overnight Status — 2026-04-17

## Summary

All tasks completed successfully. commit `644f28e` pushed; Railway deploy in progress.

---

## Task Results

### 1. Extract vishnu_v4 profile ✅
- **Script:** `extract_v4_profile.py` (new, adapted from `extract_v3_profile.py`)
- **Method:** Image-height-derived grid geometry (14% header → all 13 rows fit)
- **Page mapping:** page1.png→3/3, page2.png→2/3, page3.png→1/3 (visual inspection)
- **Threshold:** Fixed 140 (ink dark <100, v4 guide lines light ~150–220)
- **Result:** 238 glyph variants — 26/26 lowercase, 26/26 uppercase, 10/10 digits, 20 bigrams
- **Profile:** `profiles/vishnu_v4/` written with `profile.json`

### 2. Set vishnu_v4 as default profile ✅
- `web/app.py` line 52: `_DEFAULT_PROFILE = "vishnu_v4"` (was `freeform_vishnu`)

### 3. Wire variant_selector.py + kerning.py into render_engine.py ✅
- `variant_selector.py`: `QualityWeightedVariantSelector` (recency-aware, quality-weighted)
  and `find_bigram()` (pre-drawn bigram substitution for common pairs)
- `kerning.py`: `get_kern_adjustment()` — tight (0.70×) and loose (1.15×) pair multipliers
- `render_engine.py`: imports both with graceful fallback; uses `QualityWeightedVariantSelector`
  in `__init__`; integrates `find_bigram()` and `get_kern_adjustment()` in render loop
- `glyph_loader.py`: fixed `_parse_glyph_stem` to load multi-char bigrams; added
  ampersand/hash/atsign/slash/quote to PUNCT_MAP

### 4. Merge analysis/ code ✅
- `analysis/__init__.py`, `analysis/style_analyzer.py` (11-metric CV analysis),
  `analysis/parameter_mapper.py` (scores → render/realism params) — from branch
  `claude/infallible-sinoussi-491476`
- `web/analyze.html`: dark-theme style analyzer UI
- `web/app.py`: added `/analyze`, `/api/analyze-style`, `/api/apply-style` routes

### 5. Tests ✅
- `pytest test_all.py`: **10/10 passed** (2.00s)

### 6. Commit & Push ✅
- Commit: `644f28e` — "Add vishnu_v4 profile, wire kerning/variant-selector, merge analysis module"
- Pushed to `origin/main` (254 files, 2869 insertions)

### 7. Railway Deploy ✅ (build in progress)
- `railway up --detach` triggered
- Pre-deploy live test: HTTP 200, success=true (serving old deploy while new builds)
- Build logs: `https://railway.com/project/e8607991-af26-4368-aa49-2e5b64b17a72/...`

### 8. Live Render Test ✅
- Pre-build: HTTP 200, `success=true`, 758KB (old deploy, `freeform_vishnu`)
- Post-build: HTTP 200, `success=true`, 840KB, **`profile=vishnu_v4`**, 1200×1600
  - Dark ink pixels: 7102 (0.37%) — 4× denser than old deploy (0.09%)
  - Response time: 1.17s

---

## Files Changed/Added

| File | Change |
|------|--------|
| `extract_v4_profile.py` | NEW — v4 glyph extractor |
| `template_layout.py` | NEW — page grid definition |
| `variant_selector.py` | NEW — quality-weighted variant selection |
| `kerning.py` | NEW — pair kerning table |
| `analysis/__init__.py` | NEW |
| `analysis/style_analyzer.py` | NEW — 11-metric CV handwriting analyzer |
| `analysis/parameter_mapper.py` | NEW — scores → engine params |
| `web/analyze.html` | NEW — analyzer UI |
| `profiles/vishnu_v4/` | NEW — 238 glyphs (236 PNG + profile.json) |
| `template_v4_scan_page{1,2,3}.png` | NEW — raw scan source |
| `render_engine.py` | MODIFIED — variant selector + kerning + bigrams |
| `glyph_loader.py` | MODIFIED — bigram loading fix + punct map |
| `web/app.py` | MODIFIED — default profile + analysis routes |
| `.gitignore` | MODIFIED — allow vishnu_v4 + v4 scan PNGs |

---

## Known Issues / Notes

- `w`, `x`, `y`, `z` variants initially missing due to grid geometry mismatch; fixed
  by deriving `y_top` and `cell_h` from image height (14% header, remaining/13 rows)
- Bigram glyphs were not loaded by `load_profile_glyphs` due to `_parse_glyph_stem`
  only handling single-char keys; fixed to support multi-char alpha-only stems
- Railway deploy was uploading ~3MB of new PNG files; build time slightly longer than usual
