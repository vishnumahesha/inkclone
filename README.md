# InkClone — Handwriting Replication Engine

Replicate any handwriting style from a single filled template. Generate handwritten documents on realistic paper backgrounds with 15 realism sliders and 5 presets.

**Live**: [https://inkclone-production.up.railway.app](https://inkclone-production.up.railway.app)

---

## Features

- **Profile extraction** — photograph a filled template, extract individual glyphs per character with perspective warp and morphological cleaning
- **15-slider realism engine** — per-glyph size/angle/pressure/fade, per-line baseline wander/margin drift/cramming, per-page fatigue and ink bleed
- **5 presets** — Perfect Student, Natural Notes, Rushed Homework, Messy Scrawl, Custom
- **Paper backgrounds** — college ruled, blank, legal pad, graph, dot grid, sticky note
- **Artifact simulation** — scan, phone photo, clean render
- **Web UI** — FastAPI + single-file HTML frontend

---

## Architecture

```
EXTRACTION                          RENDER
extract_pipeline.py                 paper_backgrounds.py
  └─ perspective warp               render_engine.py        ← 15 realism params
  └─ morph line removal             realism_v2.py           ← sliders → params
  └─ quality scoring                compositor.py
  └─ profiles/{id}/glyphs/         artifact_simulator.py

WEB
web/app.py          (FastAPI, Railway)
web/index.html      (single-file frontend)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11 |
| Web framework | FastAPI + Uvicorn |
| Image processing | Pillow, OpenCV (headless), NumPy |
| Hosting | Railway (1 GB RAM container) |
| Containerization | Docker |

---

## Quick Start

```bash
git clone https://github.com/vishnumahesha/inkclone
cd inkclone
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn web.app:app --reload --port 8000
```

Open `http://localhost:8000`.

---

## Realism Sliders

| Section | Sliders |
|---------|---------|
| Character | Font Size, Letter Spacing, Word Spacing, Slant |
| Lines | Baseline Straightness, Line Spacing, Margin Consistency, Line End Behavior |
| Variation | Size Variation, Spacing Variation, Angle Variation, Pressure Variation |
| Page Effects | Page Fatigue, Ink Fading, Ink Bleed |

Each slider is 0–100. Presets fill all 15 values at once. Any manual change switches to Custom.

---

## Paper Types

`college_ruled` · `blank` · `legal_pad` · `graph` · `dot_grid` · `sticky_note`

---

## Creating a Handwriting Profile

1. Upload a handwriting photo via the web UI (`+ New Profile`)
2. The extraction pipeline detects the template grid, crops cells, scores quality, and saves glyphs to `profiles/{id}/glyphs/`
3. Select the new profile from the dropdown and generate

---

## Deployment

Deployed on Railway. Push to `main` and Railway auto-deploys from the `Dockerfile`.

```bash
git push origin main   # triggers Railway deploy
```

---

## License

Proprietary — All rights reserved
