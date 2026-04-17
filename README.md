# InkClone — Handwriting Replication Engine

Replicate any handwriting style from a single photo. Generate handwritten documents on realistic paper backgrounds with scan and photo artifacts.

**Live demo**: [https://inkclone-pro.fly.dev/](https://inkclone-pro.fly.dev/)

**Status**: Deployed — April 2026

---

## Screenshots

<!-- TODO: add screenshot 1 — web UI upload flow -->
<!-- TODO: add screenshot 2 — generated document example -->
<!-- TODO: add screenshot 3 — glyph extraction result -->

---

## Features

- **Profile extraction** — photograph a filled template, extract individual glyphs per character with alpha cleaning
- **Realism engine** — baseline drift, rotation jitter, scale variance, ligature kerning, page-progression fatigue
- **Paper backgrounds** — college ruled, blank, legal pad, graph, dot grid, index card, sticky note
- **Artifact simulation** — scan, phone photo, clean render modes
- **Web UI** — FastAPI + single-file HTML frontend at `/`
- **Dockerized** — single `docker run` to start locally
- **CLI** — `python3 cli.py generate "text" --paper college_ruled --ink blue --artifact scan`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11 |
| Web framework | FastAPI + Uvicorn |
| Image processing | Pillow, OpenCV (headless), NumPy |
| OCR (eval) | Tesseract via pytesseract |
| Containerization | Docker |
| Hosting | Fly.io (shared-cpu-1x, 1 GB RAM) |

---

## Quick Start

### Generate a Document

```bash
python3 cli.py generate "Your text here" --paper college_ruled --ink blue --artifact scan
```

Output: `output/document_college_ruled_blue_scan.png`

### Create a Handwriting Profile (from a real handwriting sample)

```bash
# 1. Generate template PDF
python3 cli.py template

# 2. Print, fill in handwriting, take photo
# 3. Extract glyphs from photo
python3 cli.py create-profile filled_template.jpg

# 4. Generate documents using your handwriting
python3 cli.py generate "Hello world" --paper blank --ink black
```

---

## Architecture

```
CAPTURE PIPELINE                    RENDER PIPELINE
├─ generate_template.py             ├─ paper_backgrounds.py
├─ preprocess.py                    ├─ render_engine.py
└─ segment.py                       ├─ compositor.py
                                    ├─ artifact_simulator.py
                                    └─ demo.py

                          UNIFIED CLI (cli.py)
           template → create-profile → generate
```

---

## Commands

### `python3 cli.py generate <text> [options]`

- `--paper` — `blank`, `college_ruled`, `wide_ruled`, `graph`, `legal_pad` (default: college_ruled)
- `--ink` — `black`, `blue`, `dark_blue`, `green`, `red`, `pencil` (default: black)
- `--artifact` — `clean`, `scan`, `phone` (default: scan)
- `--neatness` — 0.0 (messy) to 1.0 (neat), default 0.5
- `--opacity` — 0.0–1.0, default 1.0
- `--seed` — integer for reproducible output

### `python3 cli.py template`
Generate a blank template PDF for handwriting sample collection.

### `python3 cli.py create-profile <photo.jpg>`
Extract handwriting glyphs from a filled-in template photo. Saves `output/profile.pkl`.

### `python3 cli.py test`
Run full test suite.

---

## Performance

Measured on the eval harness and stress tests:

| Operation | Time |
|-----------|------|
| Avg generation (eval harness) | ~0.3s |
| Stress test peak | ~748ms |
| Full pipeline (paper + render + artifact) | <1s typical |

---

## Known Limitations

- **OCR verification scores ~42%** on real handwriting output. The rendering engine produces visually convincing output but Tesseract struggles to read it back — this is expected given the stylized nature of the glyphs, but it means automated OCR-based QA has low recall.
- Glyph extraction works best with clear, dark handwriting, consistent character size, and good photo lighting.
- Artifact simulation doesn't cover all scanner/camera variations.

---

## Roadmap

### Done
- [x] Paper generation (5 types)
- [x] Glyph extraction from template photos
- [x] Text rendering with real glyph bank
- [x] Artifact simulation (scan, phone, clean)
- [x] CLI interface
- [x] Web UI (FastAPI + HTML frontend)
- [x] Deployed on Fly.io
- [x] Multiple handwriting profiles

### Next
- [ ] Improve OCR verification accuracy (currently ~42%)
- [ ] Character kerning optimization
- [ ] Bleed-through simulation
- [ ] ML-based handwriting style transfer
- [ ] Export to PDF

---

## Installation

```bash
git clone https://github.com/vishnumahesha/inkclone
cd inkclone
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 cli.py info
```

---

## License

Proprietary — All rights reserved
