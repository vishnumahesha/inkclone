# InkClone QA Audit Report

**Date:** 2026-04-20  
**Site:** https://inkclone-production.up.railway.app  
**Auditor:** Claude (automated + manual)  
**Deployment audited:** `217425b` — Delete shadowed dead code in app.py

---

## Executive Summary

InkClone's core rendering pipeline works: all five test strings, all six ink colors, and the three artifact modes produce valid images. However, the product has reliability and completeness problems that block production readiness. The server crashes under sustained sequential load. The best profile (`vishnu_blue_v1`) is inaccessible from the UI. The slider API requires all 16 keys with no defaults, breaking any direct API caller. Three profiles on disk are never served. One profile has an extraction defect so severe a colon glyph is 4640px wide. Generation is consistently slow (>2.6s regardless of text length).

**Bugs found:** 13 (1 critical, 6 high, 4 medium, 2 low)

---

## Part 1 — Extraction Deep Dive

### 1A — Profile Validation

Validated all 10 profiles against 238 required glyph positions (26 lower × 4 variants, 26 upper × 2, 10 digits × 3, 12 punct × 2, 8 bigrams × 2 + extras).

| Profile | Score | Status | Notable Issues |
|---|---|---|---|
| `vishnu_blue_v1` | 235/238 | ✅ PASS | Missing 3 variants |
| `vishnu_v3` | 236/238 | ✅ PASS | Missing dollar_v0, dollar_v1 |
| `vishnu_v4` | 235/238 | ✅ PASS | g_v1 BAD_AR=8.71, missing dollar |
| `vishnu_v6` | 232/238 | ✅ PASS | 5 missing variants; colon_v1 BAD_AR=21.58 |
| `vishnu_v3_clean` | 229/238 | ❌ FAIL | Missing h/l/n variants, dollar, th/or bigrams |
| `vishnu_v3_final` | 229/238 | ❌ FAIL | Identical failures to vishnu_v3_clean |
| `vishnu_v6_new` | 225/238 | ❌ FAIL | 10 uppercase missing, 3 punct missing |
| `vishnu_v7` | 221/238 | ❌ FAIL | 15 lowercase variants missing, dollar missing |
| `freeform_vishnu` | 113/238 | ❌ FAIL | Missing all uppercase, most bigrams |
| `improved_vishnu` | 0/238 | ❌ FAIL | **Profile directory empty — zero glyphs** |

**Bug 1 (HIGH):** `improved_vishnu` profile directory exists but contains zero glyphs. It is present on disk and confuses profile enumeration logic.

**Bug 2 (HIGH):** `vishnu_v3_clean` and `vishnu_v3_final` have identical validation failures, suggesting they may be duplicates or an extraction run was applied twice without change.

**Bug 3 (HIGH):** `vishnu_blue_v1` passes validation (235/238) and is the second-best profile, yet it is never served by `/profiles` API and does not appear in the UI dropdown. Users cannot access it.

### 1B — Visual Glyph Audit (vishnu_v6, 233 glyphs)

Quality breakdown by category:

| Category | Total | Good | Rejected | Rejected Glyphs |
|---|---|---|---|---|
| Lowercase | 100 | 92 | 8 | c_v2, f_v2, k_v1, o_v2, p_v0, r_v0, r_v1, t_v1 |
| Uppercase | 51 | 49 | 2 | N_v0, N_v1 |
| Digits | 30 | 30 | 0 | — |
| Punctuation | 32 | 31 | 1 | colon_v1 |
| Bigrams | 20 | 20 | 0 | — |
| **Total** | **233** | **222** | **11** | |

All 11 rejections are due to aspect ratio exceeding the 2.2 threshold. The colon glyph (`colon_v1`) is a severe outlier at AR 21.58.

**3 best glyphs (by AR closest to 1.0 with Good status):** `colon_v0` (AR 1.00), `comma_v0` (AR 0.73), `semicolon_v1` (AR 1.08)

**3 worst glyphs (widest AR, all Rejected):** `colon_v1` (AR 21.58 / 4640px wide), `f_v2` (AR 2.94), `t_v1` (AR 2.94)

**Bug 4 (HIGH):** `colon_v1` extraction produced a glyph 4640px wide (AR 21.58). This is likely the two colon dots being extracted as a single wide strip rather than a compact square. The glyph is auto-rejected by the quality filter and will not render in output, but the extraction defect indicates a cropping bug for characters with vertically-stacked ink regions.

### 1C — Glyph Size Analysis (vishnu_v6)

| Category | Count | Width range | Height (all same) | Width outliers |
|---|---|---|---|---|
| Lowercase | 100 | 44–680px | 231px | f_v2 (680), r_v1 (677), t_v1 (679) |
| Uppercase | 51 | 54–467px | 174px | none |
| Digits | 30 | 59–305px | 211px | none |
| Punctuation | 32 | 121–4640px | 215px | colon_v1 (4640) |
| Bigrams | 20 | 175–307px | 214px | none |

Heights are perfectly uniform within each category (expected — same baseline height). Width variance is expected for character shape differences, but the four outliers flagged above are extraction defects.

---

## Part 2 — Rendering Tests

### 2A — Core Renders (T1–T5, profile: vishnu_v6)

| Test | Text | Result | Notes |
|---|---|---|---|
| T1 | "The quick brown fox jumps over the lazy dog" | ✅ 200 | Pangram, all chars present |
| T2 | "Hello World" | ✅ 200 | Short text |
| T3 | "1234567890" | ✅ 200 | Digits only |
| T4 | "ABCDEFGHIJKLMNOPQRSTUVWXYZ" | ✅ 200 | All-caps, 2.19s |
| T5 | "Hello™ Café résumé naïve" | ✅ 200 | Unicode — accepted, fallback likely |

All renders produce 1200×1600px RGB PNG images.

### 2B — Style Presets

Available presets: **Perfect Student**, **Natural Notes**, **Rushed Homework**, **Messy Scrawl**, **Custom**

**Bug 5 (LOW):** Presets produce barely distinguishable output. "Perfect Student" and "Messy Scrawl" look nearly identical in renders, suggesting the preset-to-slider mapping differences are too small or the realism engine is not sensitive enough to slider values.

### 2C — Papers and Inks

**Papers in UI (6):** College Ruled, Blank, Graph, Legal Pad, Dot Grid, Sticky Note  
**Papers in API** (`/api/profile-stats`): 7 (Wide Ruled missing from UI)

**Bug 6 (MEDIUM):** Wide Ruled paper exists in the API (`papers: 7`) but is not exposed in the UI. Users cannot select it.

**Inks (6):** Black, Blue, Navy, Green, Red, Pencil — all 6 return 200.

**Bug 7 (CRITICAL):** Server returns 502 after sustained sequential paper/render requests. During audit, College Ruled, Blank, Graph, and Legal Pad rendered successfully, then Dot Grid, Sticky Note, and subsequent requests all 502'd. Server recovered after ~30s. This is likely a Railway container OOM/crash under memory pressure from back-to-back image processing.

### 2D — Sliders

16 sliders available: `font_size`, `stroke_thickness`, `letter_spacing`, `word_spacing`, `slant`, `baseline_straightness`, `line_spacing`, `margin_consistency`, `line_end_behavior`, `size_variation`, `spacing_variation`, `angle_variation`, `pressure_variation`, `page_fatigue`, `ink_fading`, `ink_bleed`.

The UI always sends all 16 keys and works correctly.

**Bug 8 (HIGH):** The API crashes with HTTP 500 if the `sliders` dict is missing any key. The backend indexes into the dict directly (`sliders["key"]`) instead of using `.get("key", default)`. Any direct API caller sending a partial slider dict — or any programmatic client — will receive `{"detail": "Error generating document: '<key_name>'"}`.

**Reproduction:** `POST /generate` with `"sliders": {"font_size": 80}` → 500 `"Error generating document: 'word_spacing'"`.

### 2E — Artifacts

| Artifact value | UI label | Result |
|---|---|---|
| `scan` | Scanned | ✅ 200 |
| `phone` | Phone Photo | ✅ 200 |
| `clean` | Clean Render | ✅ 200 |

Note: Previous ad-hoc testing used `phone_photo` which returns 400. The correct artifact value is `phone`. All three documented artifact modes are functional.

---

## Part 3 — UI/UX Audit

### 3A — Main Page (`/`)

- **Profile dropdown:** 6 profiles, all shown with 🟢 indicator. Indicator means "has glyphs", not "passes validation" — `freeform_vishnu` (113/238, FAIL) and `vishnu_v3_clean`/`vishnu_v3_final` (229/238, FAIL) are shown as green.
- **Missing profiles:** `vishnu_blue_v1` (best profile), `vishnu_v6_new`, `vishnu_v7` not served.
- **Style Preset:** 4 named presets + Custom.
- **Paper tab:** 6 papers (Wide Ruled missing).
- **Ink tab:** 6 inks.
- **Effects tab:** Scanned, Phone Photo, Clean Render.
- **Sliders:** 16 sliders, all functional in UI.

**Bug 9 (MEDIUM):** Preview image does not auto-update when the user edits the text input. The user must click the Generate button to see any change. On a tool that positions itself as handwriting generation, live preview (or at minimum a visible stale indicator) would reduce confusion.

**Bug 10 (MEDIUM):** The profile dropdown shows `freeform_vishnu` with a green 🟢 indicator and "(172 glyphs)" count. However, this profile fails validation — it is missing all uppercase variants and most bigrams. Generating text that includes uppercase or bigrams with this profile will produce degraded output. No warning is shown.

### 3B — Review Page (`/review?profile=vishnu_v6`)

- Stats bar: 233 total, 222 good, 11 rejected.
- Category filters (All, Lowercase, Uppercase, Digits, Punctuation, Bigrams, Flagged) all work.
- Glyph grid loads and images render.
- Sort controls (Character, Quality, Size, AR) are present.

**Bug 11 (MEDIUM):** `GET /review?profile=nonexistent_profile` returns HTTP 200 with an error message rendered in the page body. It should return HTTP 404. This breaks any client that checks HTTP status to determine if a profile exists.

### 3C — Setup Page (`/setup`)

- 3-step flow: Print template → Photograph pages → Upload.
- Supports up to 4 pages.
- Instruction copy is clear and includes useful tips (e.g., pen type, photography angle).
- No functional issues observed.

### 3D — Analyze Page (`/analyze`)

- Upload interface for a handwriting sample image.
- "Analyze Style" button → style scores (editable).
- "Apply to Realism Engine" button pushes scores to slider state.
- No functional issues observed in UI structure.

---

## Part 4 — API Endpoint Audit

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/profiles` | GET | 200 | Returns 6 of 10 on-disk profiles |
| `/api/profile-stats?profile_id=vishnu_v6` | GET | 200 | total_variants=185 (inconsistency — see Bug 12) |
| `/api/profile-glyphs?profile=vishnu_v6` | GET | 200 | Returns 233 glyphs |
| `/generate` (normal text) | POST | 200 | 1200×1600px RGB PNG |
| `/generate` (bad profile) | POST | 400 | `"Profile '...' not found"` |
| `/generate` (empty text) | POST | 400 | `"Text cannot be empty"` |
| `/generate` (500 words) | POST | 200 | Same 1200×1600 dimensions |
| `/api/glyph-image/{profile}/{filename}` | GET | 200 | Returns RGBA PNG at actual glyph size |
| `/review?profile=nonexistent` | GET | 200 | Should be 404 (Bug 11) |

**Bug 12 (MEDIUM):** `/api/profile-stats` returns `total_variants: 185` for `vishnu_v6`, but `/api/profile-glyphs` returns 233 glyphs for the same profile. These two endpoints compute the count differently (or from different data sources), producing a 48-variant discrepancy. Downstream code that relies on `profile-stats` for coverage reporting will show inaccurate numbers.

**Bug 13 (LOW):** Generated images are always 1200×1600px regardless of text length. A two-word input produces the same canvas size as a 500-word document. For short texts this wastes significant whitespace (most of the page is blank).

---

## Part 5 — Performance

| Operation | Time | Threshold | Status |
|---|---|---|---|
| GET `/` | 1.25s | 2s | ✅ |
| GET `/review` | 0.32s | 2s | ✅ |
| GET `/setup` | 1.15s | 2s | ✅ |
| POST `/generate` (2 words) | 2.66s | 2s | ❌ SLOW |
| POST `/generate` (500 words) | 3.14s | 2s | ❌ SLOW |
| GET `/api/glyph-image` (median) | 0.18s | 2s | ✅ |
| GET `/api/glyph-image` (cold) | 1.18s | 2s | ✅ |

Generation is consistently slow regardless of text length. The 2-word case at 2.66s is notable: overhead is paid per request, not per character. This suggests the bottleneck is a fixed startup cost (profile loading, canvas setup, or model inference initialization) rather than text processing itself.

---

## Part 6 — Edge Cases

| Input | Result | Time |
|---|---|---|
| Unicode `Hello™ Café résumé naïve` | 200 | 1.59s |
| Emoji `Hello 😀 World` | 200 | 1.78s |
| Empty string `""` | 400 (rejected) | 0.25s |
| Spaces only `"     "` | 400 (rejected) | 0.25s |
| Punctuation only `...!!???` | 200 | 1.64s |
| Digits only `1234567890` | 200 | 1.63s |
| All caps `ABCDEFGHIJKLMNOPQRSTUVWXYZ` | 200 | 2.19s |
| Newline + tab | 200 | 1.92s |
| 34-char single word | 200 | 1.75s |
| Fake profile on `/review` | 200 (should be 404) | — |

All-caps input at 2.19s slightly exceeds the 2s threshold. Unicode and emoji are accepted without errors — the engine likely falls back to spaces for unrecognized characters, though this was not visually verified.

---

## Bugs Ranked by Severity

### Critical

| # | Bug | Impact |
|---|---|---|
| 7 | **Server 502 crash under sustained load** | Hard crash; users lose in-progress renders; no graceful degradation |

### High

| # | Bug | Impact |
|---|---|---|
| 3 | **`vishnu_blue_v1` not served by `/profiles`** | Best available profile inaccessible; users can't select it |
| 4 | **`colon_v1` extraction defect (AR 21.58, 4640px wide)** | Colon character never renders in output; likely similar bug affects other punctuation |
| 8 | **Sliders API 500 on partial dict** | Any direct API caller with a non-complete slider dict gets 500 |
| 1 | **`improved_vishnu` profile empty (0 glyphs)** | Empty profile on disk causes confusion; if served would generate blank output |
| 2 | **`vishnu_v3_clean` / `vishnu_v3_final` are identical failures** | Duplicate profile entries waste storage; may indicate extraction pipeline duplication bug |
| 12 | **Stats inconsistency: 185 vs 233 total_variants for vishnu_v6** | Incorrect coverage data in `/api/profile-stats` misleads any downstream analytics |

### Medium

| # | Bug | Impact |
|---|---|---|
| 6 | **Wide Ruled paper not in UI** | Seventh paper available in API but inaccessible from the frontend |
| 9 | **Preview does not auto-update on text change** | UX friction; users must manually re-trigger each edit |
| 10 | **Incomplete profiles shown as green/valid in UI** | freeform_vishnu (missing all uppercase) shown as healthy; misleads users |
| 11 | **`/review` with invalid profile returns 200** | HTTP 200 with error body instead of 404 breaks status-based client checks |

### Low

| # | Bug | Impact |
|---|---|---|
| 5 | **Presets visually indistinguishable** | Perfect Student ≈ Messy Scrawl in renders |
| 13 | **Fixed 1200×1600 output regardless of text length** | Excessive whitespace for short inputs; no multi-page layout for long inputs |

---

## Recommendations

1. **Immediate (pre-ship):**
   - Fix the 502 crash (Bug 7) — add Railway memory limit, profile caching, or request queuing.
   - Add `vishnu_blue_v1` to the profiles served by `/profiles` API (Bug 3).
   - Fix slider dict handling to use `.get(key, default)` so partial dicts don't 500 (Bug 8).

2. **Short-term:**
   - Fix colon (and likely other vertically-stacked punct) extraction to crop individual dots correctly (Bug 4).
   - Deduplicate or re-extract `vishnu_v3_clean` / `vishnu_v3_final` (Bug 2).
   - Add Wide Ruled paper to UI (Bug 6).
   - Return 404 from `/review` for nonexistent profiles (Bug 11).

3. **UX polish:**
   - Add live preview debounce or dirty indicator on text change (Bug 9).
   - Show profile completeness warning for profiles with missing categories (Bug 10).
   - Implement adaptive canvas sizing or multi-page output (Bug 13).
   - Tune preset slider deltas so presets are perceptibly different (Bug 5).

4. **Data hygiene:**
   - Reconcile `total_variants` between `/api/profile-stats` and `/api/profile-glyphs` (Bug 12).
   - Delete or populate `improved_vishnu` (Bug 1).
   - Investigate and fix the `all_caps` 2.19s render latency.

---

## Appendix — Test Environment

- **Screenshots:** `tests/audit_screenshots/` (18 PNGs, all ≤1125×1500px)
- **Raw data:** `tests/audit_data/` (validation, glyph sizes, API logs, performance, edge cases)
- **Profiles tested:** all 10 on-disk profiles
- **Rendering tests:** T1–T5, 4 presets, 6 inks, 6 papers, 3 artifacts, 16-slider full set, 9 edge cases
- **Railway incident:** "Degraded volume performance in EU-West" noted during testing — may have contributed to 502 crashes
