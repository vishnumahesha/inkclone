# InkClone — Project Context (auto-generated 2026-04-14)

## Project Overview

InkClone is a handwriting replication engine. It:
1. Captures real handwriting from scanned/photographed templates (inkclone-capture)
2. Stores glyphs in profiles with layout metadata
3. Renders new documents in that handwriting style (inkclone)

The pipeline is: Print template → Fill in → Photograph → Segment → Build profile → Render text

---

## Working Directories

| Directory | Purpose |
|---|---|
| `~/Projects/inkclone/` | Rendering engine, web UIs, output |
| `~/Projects/inkclone-capture/` | Capture pipeline: template, preprocess, segment, profile |

---

## inkclone/ — Key Files

```
inkclone/
├── cli.py                    # CLI entry point
├── freeform_extract.py       # Freeform (non-grid) glyph extraction (32 KB)
├── extract_real_glyphs.py    # Grid-based real glyph extractor
├── glyph_loader.py           # Load glyphs for rendering
├── render_engine.py          # Core rendering
├── render_real_document.py   # Render with real glyphs
├── compositor.py             # Image composition
├── preprocess.py             # Scan preprocessing
├── segment.py                # Segmentation
├── template_generator_v2.py  # 4-page PDF template generator
├── natural_writing_analyzer.py # Layout param measurement
├── artifact_simulator.py     # Scanning artifacts
├── ink_effects.py            # Ballpoint/gel/pencil/felt tip
├── paper_backgrounds.py      # Paper types (blank, ruled, graph, etc.)
├── page_layout.py            # Layout engine (margins, fatigue)
├── generate_template.py      # Template generator v1
├── demo.py                   # Demo script
├── clean.jpg / real_handwriting.jpg  # Source scan images
├── profiles/                 # Rendered profile (135 glyphs, 36 chars)
│   ├── glyphs/               # 135 PNG glyphs (a_0.png … T_0.png etc.)
│   ├── metadata.json
│   └── glyph_metadata.json
├── real_glyphs/              # 37 items (glyph bank + individual PNGs)
├── output/                   # Generated images and PDFs (21 items)
├── web/                      # Flask web app
│   ├── app.py
│   ├── index.html
│   └── README.md
└── web-nextjs/               # Next.js premium UI (shadcn/ui)
    ├── app/
    ├── package.json
    └── node_modules/
```

---

## inkclone-capture/ — Key Files

```
inkclone-capture/
├── generate_template.py      # 3-page PDF template (v1)
├── preprocess.py             # Quality check, perspective, normalize, binarize
├── segment.py                # Grid cell extraction, glyph cropping (RGBA)
├── profile.py                # HandwritingProfile class (save/load/coverage)
├── freeform_extract.py       # Freeform extraction (32 KB)
├── quality_feedback.py       # Quality scoring
├── test_all.py               # 18 pytest tests (all passing)
├── profiles/
│   └── freeform_vishnu/      # REAL Vishnu glyph profile
│       ├── glyphs/           # 135 PNG glyphs (36 chars covered)
│       ├── metadata.json     # layout params, x_height=45px
│       └── glyph_metadata.json
├── profile_builder/          # Freeform pipeline modules
│   ├── extract_glyphs.py
│   ├── preprocess_scan.py
│   ├── segment_lines.py
│   ├── segment_words.py
│   └── __init__.py
├── output/                   # Test outputs (template_v1.pdf, sample_glyph.png, etc.)
└── test_images/              # 203 synthetic test images
```

---

## Real Glyph Locations

The **canonical real glyph profile** (Vishnu's handwriting) lives at:
```
~/Projects/inkclone-capture/profiles/freeform_vishnu/
```
- 135 glyphs covering 36 characters
- layout metadata: slant=0°±2°, x_height=45px, inter_letter_gap=3±2px
- This profile was also copied/synced to `~/Projects/inkclone/profiles/`

---

## What Works

- **inkclone-capture test suite**: 18/18 tests passing
- **Template generation**: v1 (3-page) and v2 (4-page with ligatures) PDFs
- **Preprocessing pipeline**: perspective correction, normalize, binarize
- **Segmentation**: grid-cell glyph extraction → RGBA 128px PNGs
- **Profile save/load**: HandwritingProfile roundtrip works
- **Freeform extraction**: 135 glyphs extracted from Vishnu's freeform scan
- **Rendering engine**: render_engine.py, render_real_document.py
- **Paper backgrounds**: blank, college ruled, wide ruled, legal pad, graph, dot grid, index card, sticky note
- **Ink effects**: ballpoint, gel pen, pencil, felt tip
- **Page layout engine**: baselines, text wrap, margin jitter, fatigue
- **Natural writing analyzer**: line height, spacing, word gap, slant detection
- **Output images**: 21 rendered samples in inkclone/output/
- **Web UI**: Flask app (web/) + Next.js premium UI (web-nextjs/) with shadcn/ui
- **CLI**: cli.py entry point

---

## What's Broken / Incomplete

- Font export (potrace) — SKIPPED, not essential
- DISPATCH_PROGRESS.md — did not exist prior to this session
- No OVERNIGHT_DONE.md in inkclone-capture (it's in inkclone/)
- inkclone/test_all.py — not confirmed passing (different from capture tests)
- web-nextjs dev server status unknown (not running during this check)

---

## Dependencies Installed

- **Python**: 3.14.3 (system Homebrew)
- **pytest**: 9.0.3
- **OpenCV** (cv2): installed (used by preprocess, segment)
- **Pillow** (PIL): installed
- **numpy**: installed
- **reportlab**: installed (PDF generation)
- **scikit-image**: installed (Sauvola binarization)
- **Node.js / npm**: installed (web-nextjs)
- **tesseract**: 5.5.2 at /opt/homebrew/bin/tesseract (leptonica 1.87.0)
- **Claude Code**: v2.1.107 at /opt/homebrew/bin/claude

---

## Tool Availability

| Tool | Status |
|---|---|
| Claude Code CLI | ✅ v2.1.107 |
| tesseract | ✅ v5.5.2 |
| python3 | ✅ 3.14.3 |
| pytest | ✅ 9.0.3 |

---

## Current Task Status

As of 2026-04-14 afternoon:
- **Overnight build** (completed ~2:30 AM): template_generator_v2, natural_writing_analyzer, ink_effects, page_layout, 3 new paper types — all done
- **Premium UI**: Next.js + shadcn/ui dark theme complete (FRONTEND_COMPLETE.md, PREMIUM_UI_COMPLETE.md)
- **Real handwriting demo**: freeform_extract.py produced 135 real Vishnu glyphs
- **Profile sync**: profiles/ in both repos contain matching freeform_vishnu data
- **No active dispatch in progress** at time of context generation

---

## Git Status (inkclone)

Branch: `main` (also worktree `claude/nice-banach`)
Recent commits:
- `08c12f7` COMPLETE UI OVERHAUL: Premium dark theme interface
- `db680aa` Premium shadcn/ui integration + enhanced interface
- `f775755` Initial commit: InkClone handwriting replication engine
