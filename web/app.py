"""
InkClone Web Interface Backend
FastAPI server for handwriting document generation
"""

import sys
import os
import json
import shutil
import time
import uuid
from pathlib import Path
from io import BytesIO
import base64
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Add parent directory to path to import inkclone modules
_WEB_DIR    = Path(__file__).parent
_ROOT       = _WEB_DIR.parent
sys.path.insert(0, str(_ROOT))

from render_engine import HandwritingRenderer, create_dummy_glyph_bank
from glyph_loader import load_profile_glyphs
from paper_backgrounds import (generate_blank_paper, generate_college_ruled,
                               generate_wide_ruled, generate_graph_paper, generate_legal_pad,
                               generate_dot_grid, generate_sticky_note)
from compositor import composite, INK_COLORS
from artifact_simulator import simulate_scan, simulate_phone_photo, simulate_clean
from realism_v2 import sliders_to_render_params, PRESETS as REALISM_PRESETS, get_preset

# ── Directories ────────────────────────────────────────────────────────────────
_PROFILES_DIR = _ROOT / "profiles"
_DATA_DIR     = _ROOT / "data"
_UPLOADS_DIR  = _DATA_DIR / "uploads"
_STATIC_DIR   = _WEB_DIR / "static"

_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_STATIC_DIR.mkdir(parents=True, exist_ok=True)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="InkClone", description="Handwriting document generator")
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ── Default glyph bank ─────────────────────────────────────────────────────────
_DEFAULT_PROFILE  = "vishnu_v6"
_PROFILE_DIR      = _PROFILES_DIR / _DEFAULT_PROFILE
_GLYPH_BANKS: dict = {}   # cache: profile_id → glyph_bank dict


def _get_glyph_bank(profile_id: str | None = None) -> dict:
    """Load (and cache) a glyph bank for the given profile ID."""
    pid = profile_id or _DEFAULT_PROFILE
    if pid not in _GLYPH_BANKS:
        profile_path = _PROFILES_DIR / pid
        if not profile_path.exists():
            pid = _DEFAULT_PROFILE
            profile_path = _PROFILES_DIR / pid
        try:
            _GLYPH_BANKS[pid] = load_profile_glyphs(profile_path, fallback_dummy=True)
        except Exception:
            _GLYPH_BANKS[pid] = create_dummy_glyph_bank()
    return _GLYPH_BANKS[pid]


# Warm up default bank at startup
try:
    _GLYPH_BANKS[_DEFAULT_PROFILE] = load_profile_glyphs(_PROFILE_DIR, fallback_dummy=True)
except Exception as exc:
    print(f"[startup] Warning: could not load default profile: {exc}")
    _GLYPH_BANKS[_DEFAULT_PROFILE] = create_dummy_glyph_bank()

# ── Paper / artifact maps ──────────────────────────────────────────────────────
PAPERS = {
    "blank":          generate_blank_paper,
    "college_ruled":  generate_college_ruled,
    "wide_ruled":     generate_wide_ruled,
    "graph":          generate_graph_paper,
    "legal_pad":      generate_legal_pad,
    "dot_grid":       generate_dot_grid,
    "sticky_note":    generate_sticky_note,
}

# Render parameters matched to each paper's actual line/margin geometry.
# line_spacing values come from paper_backgrounds.py (hardcoded regardless of image size).
# char_height = 60% of line_spacing (x-height target); margin_left = margin_x + 4px.
_PAPER_RENDER_PARAMS = {
    "college_ruled": {"line_height": 42, "char_height": 30, "margin_left": 204, "margin_top": 120},
    "wide_ruled":    {"line_height": 51, "char_height": 36, "margin_left": 204, "margin_top": 120},
    "legal_pad":     {"line_height": 51, "char_height": 36, "margin_left": 204, "margin_top": 201},
    "blank":         {"line_height": 55, "char_height": 40, "margin_left": 100, "margin_top": 150},
    "graph":         {"line_height": 30, "char_height": 18, "margin_left": 100, "margin_top": 100},
    "dot_grid":      {"line_height": 42, "char_height": 25, "margin_left": 100, "margin_top": 100},
    "sticky_note":   {"line_height": 40, "char_height": 24, "margin_left": 30,  "margin_top": 30},
}

ARTIFACTS = {
    "clean": simulate_clean,
    "scan":  simulate_scan,
    "phone": simulate_phone_photo,
}


# ── Models ─────────────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    text:        str
    paper:       str   = "college_ruled"
    ink_color:   str   = "black"
    ink:         str   = None    # legacy alias
    artifact:    str   = "scan"
    seed:        int   = None
    profile_id:  str   = None
    transparent: bool  = False
    sliders:     dict  = None    # 15 realism_v2 sliders (0–100 each)
    preset:      str   = "natural_notes"  # fallback when sliders is None

    def get_ink(self) -> str:
        return self.ink_color or self.ink or "black"

    def get_sliders(self) -> dict:
        if self.sliders:
            return self.sliders
        return get_preset(self.preset)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def get_index():
    html_file = _WEB_DIR / "index.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>InkClone</h1><p>index.html not found</p>"


@app.get("/setup", response_class=HTMLResponse)
async def get_setup():
    setup_file = _WEB_DIR / "setup.html"
    if setup_file.exists():
        return setup_file.read_text(encoding="utf-8")
    return "<h1>Setup</h1><p>setup.html not found</p>"


@app.post("/generate")
async def generate_document(request: GenerateRequest):
    """Generate a handwritten document."""
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if request.paper not in PAPERS:
        raise HTTPException(status_code=400, detail=f"Invalid paper type: {request.paper}")
    ink = request.get_ink()
    if ink not in INK_COLORS:
        raise HTTPException(status_code=400, detail=f"Invalid ink color: {ink}")
    if request.artifact not in ARTIFACTS:
        raise HTTPException(status_code=400, detail=f"Invalid artifact type: {request.artifact}")

    pid = request.profile_id or _DEFAULT_PROFILE
    profile_path = _PROFILES_DIR / pid
    if not profile_path.exists():
        raise HTTPException(status_code=400, detail=f"Profile '{pid}' not found")

    try:
        PAGE_W, PAGE_H = 1200, 1600
        bank     = _get_glyph_bank(request.profile_id)
        renderer = HandwritingRenderer(bank, seed=request.seed)

        paper_params = _PAPER_RENDER_PARAMS.get(request.paper, _PAPER_RENDER_PARAMS["college_ruled"])
        line_spacing = paper_params["line_height"]
        slider_params = sliders_to_render_params(request.get_sliders(), line_spacing)

        render_params = {
            "margin_left":  paper_params["margin_left"],
            "margin_top":   paper_params["margin_top"],
            "line_height":  paper_params["line_height"],
            **slider_params,
        }
        text_img = renderer.render(
            request.text,
            page_width=PAGE_W, page_height=PAGE_H,
            **render_params,
        )
        if request.transparent:
            # Colorize the ink alpha mask and return as RGBA (no paper)
            import numpy as np
            arr = np.array(text_img.convert("RGBA")).astype(float)
            r, g, b = INK_COLORS[ink]
            arr[:, :, 0] = r
            arr[:, :, 1] = g
            arr[:, :, 2] = b
            from PIL import Image as _PIL
            result = _PIL.fromarray(arr.astype("uint8"), "RGBA")
            final  = ARTIFACTS[request.artifact](result)
            buf = BytesIO()
            final.save(buf, format="PNG")
        else:
            _fixed_size = {"sticky_note", "dot_grid"}
            if request.paper in _fixed_size:
                paper = PAPERS[request.paper]()
            else:
                paper = PAPERS[request.paper](width=PAGE_W, height=PAGE_H)
            result = composite(text_img, paper, ink_color=INK_COLORS[ink])
            final  = ARTIFACTS[request.artifact](result)
            buf = BytesIO()
            final.save(buf, format="PNG")

        buf.seek(0)
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return JSONResponse({
            "success":    True,
            "image":      f"data:image/png;base64,{img_b64}",
            "width":      final.width,
            "height":     final.height,
            "paper":      request.paper,
            "ink_color":  ink,
            "artifact":   request.artifact,
            "profile_id": request.profile_id or _DEFAULT_PROFILE,
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating document: {exc}")


# ── Profile stats ──────────────────────────────────────────────────────────────

@app.get("/api/profile-stats")
async def get_profile_stats(profile_id: str = None):
    """Return glyph counts for a profile (used to populate the stats cards)."""
    bank = _get_glyph_bank(profile_id)
    total_variants = sum(len(v) for v in bank.values())
    unique_chars   = len(bank)
    return JSONResponse({
        "total_variants": total_variants,
        "unique_chars":   unique_chars,
        "papers":         len(PAPERS),
    })


# ── Glyph review endpoints ─────────────────────────────────────────────────────

_WIDE_CHARS = set('mwMW') | {
    'th', 'he', 'in', 'an', 'er', 'on', 'ed', 're',
    'ou', 'es', 'ti', 'at', 'st', 'en', 'or', 'ng',
    'ing', 'the', 'and', 'tion',
}

def _glyph_quality(char: str, w: int, h: int, ink: int, top_ink: int):
    """Return (quality, reason) for display on the review page.

    Label-contamination is NOT checked here because post-processed glyphs
    have ink starting at row 0, making the top-quarter test meaningless.
    AR threshold is 2.2 for single chars (glyph_loader uses 1.8 after autocrop
    but review shows raw files which are slightly wider before autocrop).
    """
    if w < 8 or h < 8:
        return 'rejected', 'too small'
    ar = w / h
    max_ar = 3.5 if char in _WIDE_CHARS else 2.2
    if ar > max_ar:
        return 'rejected', f'AR {ar:.2f} > {max_ar}'
    if ar < 0.15:
        return 'rejected', 'too narrow'
    if ink < 50:
        return 'rejected', 'insufficient ink'
    if ink < 150:
        return 'warning', 'low ink count'
    return 'good', ''

def _char_category(char: str) -> str:
    if len(char) > 1:
        return 'bigrams'
    if char.islower():
        return 'lowercase'
    if char.isupper():
        return 'uppercase'
    if char.isdigit():
        return 'digits'
    return 'punctuation'

@app.get("/review", response_class=HTMLResponse)
async def review_page():
    with open(_WEB_DIR / "review.html", encoding="utf-8") as f:
        return f.read()

@app.get("/api/glyph-image/{profile}/{filename}")
async def get_glyph_image(profile: str, filename: str):
    path = _PROFILES_DIR / profile / "glyphs" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(path), media_type="image/png")

@app.get("/api/profile-glyphs")
async def get_profile_glyphs(profile: str = None):
    import numpy as np
    pid = profile or _DEFAULT_PROFILE
    glyphs_dir = _PROFILES_DIR / pid / "glyphs"
    if not glyphs_dir.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{pid}' not found")

    from glyph_loader import _parse_glyph_stem, _is_valid_glyph
    from PIL import Image as _Image

    glyphs = []
    variant_counter: dict = {}

    for png in sorted(glyphs_dir.glob("*.png")):
        char = _parse_glyph_stem(png.stem)
        if char is None:
            continue
        variant_counter[char] = variant_counter.get(char, -1) + 1
        variant = variant_counter[char]
        try:
            img = _Image.open(png)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            w, h = img.size
            arr   = np.array(img)
            alpha = arr[:, :, 3]
            ink   = int((alpha > 0).sum())
            top_ink = int((alpha[:max(1, h // 4), :] > 0).sum())
        except Exception:
            continue

        quality, reason = _glyph_quality(char, w, h, ink, top_ink)
        if quality == "warning" and not _is_valid_glyph(img, char):
            quality, reason = "skipped", "loader skips (short ink span)"
        glyphs.append({
            "filename":     png.name,
            "char":         char,
            "variant":      variant,
            "width":        w,
            "height":       h,
            "aspect_ratio": round(w / max(h, 1), 3),
            "ink_pixels":   ink,
            "quality":      quality,
            "quality_reason": reason,
            "category":     _char_category(char),
            "image_url":    f"/api/glyph-image/{pid}/{png.name}",
        })

    total    = len(glyphs)
    good     = sum(1 for g in glyphs if g["quality"] == "good")
    warnings = sum(1 for g in glyphs if g["quality"] == "warning")
    skipped  = sum(1 for g in glyphs if g["quality"] == "skipped")
    rejected = sum(1 for g in glyphs if g["quality"] == "rejected")
    return JSONResponse({
        "profile": pid,
        "glyphs":  glyphs,
        "summary": {"total": total, "good": good, "warnings": warnings, "skipped": skipped, "rejected": rejected},
    })


# ── Profile listing ────────────────────────────────────────────────────────────

@app.get("/profiles")
async def list_profiles():
    """List all available profiles with stats."""
    if not _PROFILES_DIR.exists():
        return JSONResponse([])

    _ALLOW = {"vishnu_v6"}
    results = []
    for entry in sorted(_PROFILES_DIR.iterdir()):
        if not entry.is_dir() or entry.name not in _ALLOW:
            continue

        profile_json = entry / "profile.json"
        character_coverage = {}
        created_at = None

        if profile_json.exists():
            try:
                data = json.loads(profile_json.read_text(encoding="utf-8"))
                character_coverage = data.get("character_coverage", {})
                created_at = data.get("created_at")
            except Exception:
                pass

        if not character_coverage:
            # Synthesise basic coverage from PNG count
            glyphs_dir = entry / "glyphs"
            n = len(list(glyphs_dir.glob("*.png"))) if glyphs_dir.exists() else 0
            # Rough split: assume mostly lowercase
            character_coverage = {
                "total_variants": n,
                "lowercase_pct":  min(100.0, round(n / 26 * 100, 1)),
                "uppercase_pct":  0.0,
                "digits_pct":     0.0,
            }

        results.append({
            "profile_id":          entry.name,
            "name":                entry.name.replace("_", " ").title(),
            "character_coverage":  character_coverage,
            "created_at":          created_at,
            "has_schema":          profile_json.exists(),
        })

    return JSONResponse(results)


@app.get("/profiles/{profile_id}/contact_sheet.png")
async def get_contact_sheet(profile_id: str):
    """Serve a profile's contact sheet image."""
    sheet = _PROFILES_DIR / profile_id / "contact_sheet.png"
    if not sheet.exists():
        # Generate one on-demand if it doesn't exist
        try:
            _generate_contact_sheet(profile_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Contact sheet not found")
    if not sheet.exists():
        raise HTTPException(status_code=404, detail="Contact sheet not found")
    return FileResponse(str(sheet), media_type="image/png")


# ── Profile creation ───────────────────────────────────────────────────────────

@app.post("/profiles/create")
async def create_profile(images: List[UploadFile] = File(...)):
    """
    Accept 1–3 handwriting template photos, extract glyphs, build a profile.

    Extraction pipeline:
    1. Save uploaded images to data/uploads/{timestamp}/
    2. Preprocess each image (grayscale, denoise, Otsu threshold)
    3. Detect template grid structure; extract glyph cells
    4. Clean each cell: morph-close → crop tight → RGBA (ink=240, bg=0) → 128px height
    5. Score quality (ink_density, bbox_fill); skip noise glyphs
    6. Save glyphs to profiles/{id}/glyphs/
    7. Write profile.json via migrate.py logic
    8. Generate contact_sheet.png
    9. Return profile stats
    """
    if not images:
        raise HTTPException(status_code=400, detail="No images provided")
    if len(images) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 images allowed")

    # ── 1. Save uploads ────────────────────────────────────────────────────────
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_dir = _UPLOADS_DIR / ts
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for img_file in images:
        ext      = Path(img_file.filename or "image.jpg").suffix.lower() or ".jpg"
        dst      = upload_dir / f"page_{len(saved_paths)+1}{ext}"
        contents = await img_file.read()
        dst.write_bytes(contents)
        saved_paths.append(dst)

    # ── 1b. Image quality gate ─────────────────────────────────────────────────
    all_warnings: list[str] = []
    for idx, p in enumerate(saved_paths):
        page_warnings = _check_image_quality(p)
        for w in page_warnings:
            all_warnings.append(f"Page {idx+1}: {w}" if len(saved_paths) > 1 else w)

    # ── 2-6. Extract glyphs ────────────────────────────────────────────────────
    profile_id  = f"profile_{ts}"
    profile_dir = _PROFILES_DIR / profile_id
    glyphs_dir  = profile_dir / "glyphs"
    glyphs_dir.mkdir(parents=True, exist_ok=True)

    try:
        glyph_bank = _extract_glyphs_pipeline(saved_paths, glyphs_dir)
    except Exception as exc:
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")

    if not glyph_bank:
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise HTTPException(
            status_code=422,
            detail="No legible glyphs could be extracted. "
                   "Ensure good lighting, shoot straight above the page, and use a dark pen."
        )

    # ── 7. Save glyphs to disk + write profile.json ────────────────────────────
    # glyph_bank: {char: [(PIL.Image, confidence, is_weak), ...]}
    saved_chars: dict[str, list] = {}
    for char, variants in glyph_bank.items():
        char_name = _char_to_stem(char)
        for v_idx, (glyph_img, confidence, is_weak) in enumerate(variants):
            fname = f"{char_name}_{v_idx}.png"
            glyph_img.save(str(glyphs_dir / fname))
            saved_chars.setdefault(char, []).append({
                "path":       f"glyphs/{fname}",
                "confidence": confidence,
                "is_weak":    is_weak,
            })

    _write_profile_json(profile_dir, profile_id, saved_chars, saved_paths)

    # ── 8. Contact sheet ───────────────────────────────────────────────────────
    _generate_contact_sheet(profile_id)

    # ── 9. Response ────────────────────────────────────────────────────────────
    total_glyphs    = sum(len(v) for v in saved_chars.values())
    lowercase_chars = sum(1 for c in saved_chars if c.islower())
    uppercase_chars = sum(1 for c in saved_chars if c.isupper())
    digit_chars     = sum(1 for c in saved_chars if c.isdigit())

    coverage_pct  = round(lowercase_chars / 26 * 100, 1) if lowercase_chars else 0.0
    uppercase_pct = round(uppercase_chars / 26 * 100, 1)
    digits_pct    = round(digit_chars / 10 * 100, 1)

    weak_chars = sorted(
        c for c, variants in saved_chars.items()
        if any(v["is_weak"] for v in variants)
    )

    lc_label = f"{coverage_pct:.0f}%" if lowercase_chars else "auto-generated"
    uc_label = f"{uppercase_pct:.0f}%" if uppercase_chars else "auto-generated"
    dg_label = f"{digits_pct:.0f}%"    if digit_chars     else "auto-generated"
    coverage_report = f"Lowercase: {lc_label} | Uppercase: {uc_label} | Digits: {dg_label}"

    # Invalidate cache so next render picks up new profile
    _GLYPH_BANKS.pop(profile_id, None)

    return JSONResponse({
        "profile_id":        profile_id,
        "total_glyphs":      total_glyphs,
        "coverage_pct":      coverage_pct,
        "uppercase_pct":     uppercase_pct,
        "digits_pct":        digits_pct,
        "weak_chars":        weak_chars,
        "coverage_report":   coverage_report,
        "warnings":          all_warnings,
        "contact_sheet_url": f"/profiles/{profile_id}/contact_sheet.png",
    })


# ── Extraction pipeline ────────────────────────────────────────────────────────

def _check_image_quality(img_path: Path) -> list:
    """Return user-facing warning strings for sharpness, brightness, and aspect ratio."""
    import cv2

    img_cv = cv2.imread(str(img_path))
    if img_cv is None:
        return []

    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    warnings_out = []

    # Sharpness: Laplacian variance < 50 → blurry
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if lap_var < 50:
        warnings_out.append("Photo is blurry — try holding steadier")

    # Brightness: mean pixel value
    mean_val = float(gray.mean())
    if mean_val < 80:
        warnings_out.append("Photo is too dark")
    elif mean_val > 220:
        warnings_out.append("Photo is overexposed")

    # Aspect ratio: letter paper portrait ≈ 8.5/11 = 0.773
    portrait_ratio = min(w, h) / max(w, h)
    if abs(portrait_ratio - 0.773) > 0.15:
        warnings_out.append("Photo may be cropped incorrectly")

    return warnings_out


def _score_cell_quality(cell_bin: "np.ndarray") -> dict:
    """
    Score glyph quality from a binary cell crop.

    Metrics (weights):
      ink_density       0.20 — fill ratio within tight ink bbox
      centering_score   0.15 — how centred the ink is in the cell
      size_score        0.25 — ink bbox / cell area, ideal 0.2-0.7
      noise_score       0.20 — penalises tiny disconnected fragments
      stroke_continuity 0.20 — largest component / total ink

    Returns confidence 0-1, component scores, and is_weak flag.
    """
    import cv2
    import numpy as np

    h, w = cell_bin.shape
    cell_area = h * w
    total_ink = int((cell_bin > 0).sum())

    if total_ink == 0 or cell_area == 0:
        return {"confidence": 0.0, "is_weak": True}

    rows = np.any(cell_bin > 0, axis=1)
    cols = np.any(cell_bin > 0, axis=0)
    rmin = int(np.where(rows)[0][0]);  rmax = int(np.where(rows)[0][-1])
    cmin = int(np.where(cols)[0][0]);  cmax = int(np.where(cols)[0][-1])
    ink_bbox_area = (rmax - rmin + 1) * (cmax - cmin + 1)

    # ink_density: fill ratio within tight ink bbox
    tight_ink = int((cell_bin[rmin:rmax+1, cmin:cmax+1] > 0).sum())
    ink_density = tight_ink / max(1, ink_bbox_area)

    # centering_score: how close the ink centre is to the cell centre
    center_r = (rmin + rmax) / 2.0 / max(1, h)
    center_c = (cmin + cmax) / 2.0 / max(1, w)
    centering_score = max(0.0, 1.0 - 2.0 * max(abs(center_r - 0.5), abs(center_c - 0.5)))

    # size_score: ink bbox area / cell area, ideal 0.2-0.7
    size_ratio = ink_bbox_area / max(1, cell_area)
    if 0.2 <= size_ratio <= 0.7:
        size_score = 1.0
    elif size_ratio < 0.2:
        size_score = size_ratio / 0.2
    else:
        size_score = max(0.0, 1.0 - (size_ratio - 0.7) / 0.3)

    # Connected-component analysis
    n_labels, _, stats, _ = cv2.connectedComponentsWithStats(cell_bin, connectivity=8)
    if n_labels <= 1:
        return {"confidence": 0.0, "is_weak": True}

    comp_areas  = [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n_labels)]
    largest_area = max(comp_areas)
    small_count  = sum(1 for a in comp_areas if a < max(1, total_ink) * 0.05)

    noise_score       = max(0.0, 1.0 - small_count / max(1, len(comp_areas)))
    stroke_continuity = largest_area / max(1, total_ink)

    confidence = (
        ink_density       * 0.20 +
        centering_score   * 0.15 +
        size_score        * 0.25 +
        noise_score       * 0.20 +
        stroke_continuity * 0.20
    )
    confidence = min(1.0, max(0.0, confidence))

    return {
        "confidence":        round(confidence, 3),
        "is_weak":           confidence < 0.5,
        "ink_density":       round(ink_density, 4),
        "centering_score":   round(centering_score, 3),
        "size_score":        round(size_score, 3),
        "noise_score":       round(noise_score, 3),
        "stroke_continuity": round(stroke_continuity, 3),
    }


def _extract_glyphs_pipeline(image_paths: list, glyphs_dir: Path) -> dict:
    """
    Main glyph extraction pipeline.

    For each image:
    - Preprocess to binary (Otsu)
    - Detect if template (regular grid lines present)
    - If template: extract cells at known grid positions
    - If freeform: connected-component extraction with OCR labelling
    - Clean each component: morph-close, crop, RGBA, resize 128px
    - Score quality; discard noise
    Returns: {char: [PIL.Image (RGBA), ...]}
    """
    import cv2
    import numpy as np
    from PIL import Image

    bank: dict[str, list] = {}

    for img_path in image_paths:
        img_cv = cv2.imread(str(img_path))
        if img_cv is None:
            continue

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

        # Mild denoise
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        # Otsu threshold → ink=255 (inverted)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Morphological closing to connect broken strokes
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        is_template = _detect_template_grid(binary)

        if is_template:
            extracted = _extract_template_cells(gray, binary, img_cv)
        else:
            extracted = _extract_freeform_components(gray, binary)

        for char, glyph_rgba, confidence, is_weak in extracted:
            bank.setdefault(char, []).append((glyph_rgba, confidence, is_weak))

    return bank


def _detect_template_grid(binary: "np.ndarray") -> bool:
    """
    Return True if the image contains a regular grid pattern
    characteristic of the InkClone template.

    Heuristic: detect long horizontal lines via Hough transform.
    A template page has 10+ parallel horizontal lines.
    """
    import cv2
    import numpy as np

    h, w = binary.shape
    # Erode vertically to isolate horizontal lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 8, 1))
    h_lines  = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)

    # Count distinct horizontal line bands
    col_sum  = h_lines.sum(axis=1)          # sum across each row
    threshold = w * 0.3                      # line present if >30% of row is ink
    line_rows = col_sum > threshold
    # Count runs of True
    runs = 0
    in_run = False
    for v in line_rows:
        if v and not in_run:
            runs += 1
            in_run = True
        elif not v:
            in_run = False
    return runs >= 6


def _extract_template_cells(gray, binary, img_cv) -> list:
    """
    Extract glyph cells from a filled-in InkClone template photo.

    Template layout (from template_generator_v2.py, letter paper at ~150 DPI):
      Page 1: lowercase a-z, 5 cells per char → 130 cells, row-major
      Cell: 1.2cm wide × 1.5cm tall
      Margin: 1.5cm

    We first auto-detect the usable region using the grid lines,
    then divide into cells at computed positions.
    """
    import cv2
    import numpy as np
    from PIL import Image

    H, W = gray.shape

    # ── Find the grid bounding box from horizontal lines ──────────────────
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (W // 8, 1))
    h_lines  = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    col_sum  = h_lines.sum(axis=1)
    threshold = W * 0.25
    line_ys  = [i for i, v in enumerate(col_sum) if v > threshold]

    if len(line_ys) < 4:
        return _extract_freeform_components(gray, binary)  # fallback

    top_y    = line_ys[0]
    bottom_y = line_ys[-1]

    # ── Estimate cell dimensions ──────────────────────────────────────────
    # Group line_ys into distinct bands
    bands = []
    prev = line_ys[0]
    band_start = prev
    for y in line_ys[1:]:
        if y - prev > 5:
            bands.append((band_start + prev) // 2)
            band_start = y
        prev = y
    bands.append((band_start + prev) // 2)

    if len(bands) < 3:
        return _extract_freeform_components(gray, binary)

    cell_h = int(np.median([bands[i+1] - bands[i] for i in range(len(bands)-1)]))
    if cell_h < 10:
        return _extract_freeform_components(gray, binary)

    # Estimate margin + cell width from vertical projection
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, cell_h // 2))
    v_lines  = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
    row_sum  = v_lines.sum(axis=0)
    vthresh  = cell_h * 0.3
    vline_xs = [i for i, v in enumerate(row_sum) if v > vthresh]

    if vline_xs:
        left_x  = vline_xs[0]
        right_x = vline_xs[-1]
    else:
        left_x  = int(W * 0.05)
        right_x = int(W * 0.95)

    usable_w = right_x - left_x
    # Estimate cells per row: for template ~15 cells/row at typical phone photo res
    cell_w = max(10, usable_w // 15)

    # ── Build cell map for lowercase a-z (Page 1) ─────────────────────────
    CHARS_PAGE1 = list("abcdefghijklmnopqrstuvwxyz")
    CELLS_PER_CHAR = 5
    cells_per_row = max(1, usable_w // cell_w)

    extracted = []
    cell_idx = 0
    for char in CHARS_PAGE1:
        for variant in range(CELLS_PER_CHAR):
            row = cell_idx // cells_per_row
            col = cell_idx % cells_per_row
            x0 = left_x  + col * cell_w
            y0 = top_y   + row * cell_h
            x1 = min(W, x0 + cell_w)
            y1 = min(H, y0 + cell_h)
            cell_idx += 1

            if y1 > H or x1 > W:
                continue

            cell_gray = gray[y0:y1, x0:x1]
            if cell_gray.size == 0:
                continue

            # Per-cell Otsu threshold handles uneven lighting across the page
            _, cell_bin = cv2.threshold(
                cell_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            quality = _score_cell_quality(cell_bin)
            if quality["confidence"] < 0.3:
                continue  # unusable — skip entirely

            glyph = _cell_to_rgba(cell_bin, cell_gray)
            if glyph is not None:
                extracted.append((char, glyph, quality["confidence"], quality["is_weak"]))

    return extracted


def _extract_freeform_components(gray, binary) -> list:
    """
    Extract individual glyphs from a freeform handwriting image using
    connected components + Tesseract OCR for character labelling.
    """
    import cv2
    import numpy as np
    from PIL import Image

    try:
        import pytesseract
        ocr_available = True
    except ImportError:
        ocr_available = False

    H, W = binary.shape
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )

    extracted = []
    for i in range(1, n_labels):
        x, y, w, h, area = stats[i]

        # Size filters
        if area < 80:                               # too small → noise
            continue
        if w > W * 0.25 or h > H * 0.25:           # too large → not a single char
            continue
        if w < 6 or h < 10:                         # too skinny
            continue
        aspect = w / max(1, h)
        if aspect > 3.5 or aspect < 0.08:           # weird aspect → not a letter
            continue

        pad  = max(4, min(w, h) // 8)
        x0   = max(0, x - pad)
        y0   = max(0, y - pad)
        x1   = min(W, x + w + pad)
        y1   = min(H, y + h + pad)

        cell_bin  = binary[y0:y1, x0:x1]
        cell_gray = gray[y0:y1, x0:x1]

        # OCR to label the glyph
        char = None
        if ocr_available:
            # Upscale for better OCR accuracy
            scale    = max(1.0, 64.0 / max(w, h))
            ocr_img  = cv2.resize(cell_bin, None, fx=scale, fy=scale,
                                  interpolation=cv2.INTER_LINEAR)
            whitelist = (
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789.,!?'-:"
            )
            try:
                raw = pytesseract.image_to_string(
                    ocr_img,
                    config=f"--psm 10 --oem 3 -c tessedit_char_whitelist={whitelist}"
                ).strip()
                if len(raw) == 1 and raw.isprintable() and not raw.isspace():
                    char = raw
            except Exception:
                pass

        if char is None:
            continue

        quality = _score_cell_quality(cell_bin)
        if quality["confidence"] < 0.3:
            continue

        glyph = _cell_to_rgba(cell_bin, cell_gray)
        if glyph is not None:
            extracted.append((char, glyph, quality["confidence"], quality["is_weak"]))

    return extracted


def _cell_to_rgba(cell_bin, cell_gray) -> "PIL.Image | None":
    """
    Convert a binary cell crop to a clean RGBA glyph at 128px height.

    Steps:
    1. Find ink bounding box; skip if ink < 5% of cell
    2. Crop tight with 3px padding
    3. Build RGBA: ink pixels → (0,0,0,240), rest → transparent
    4. Resize to 128px height preserving aspect ratio
    """
    import cv2
    import numpy as np
    from PIL import Image

    h, w = cell_bin.shape
    ink_pixels = cell_bin.sum() // 255
    total_px   = h * w
    if ink_pixels < total_px * 0.05:    # <5% ink → noise/empty cell
        return None
    if ink_pixels < 20:                 # absolute minimum
        return None

    # Tight crop
    rows = np.any(cell_bin > 0, axis=1)
    cols = np.any(cell_bin > 0, axis=0)
    if not rows.any():
        return None
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    pad  = 3
    rmin = max(0, rmin - pad)
    rmax = min(h - 1, rmax + pad)
    cmin = max(0, cmin - pad)
    cmax = min(w - 1, cmax + pad)
    cropped = cell_bin[rmin:rmax+1, cmin:cmax+1]

    ch, cw = cropped.shape

    # Resize to 128px height
    target_h = 128
    scale    = target_h / max(1, ch)
    target_w = max(1, int(round(cw * scale)))
    resized  = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

    # RGBA: ink→black+alpha, background→transparent
    ink_mask = resized > 128
    arr = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    arr[ink_mask, 3] = 240       # alpha: ink is opaque
    # RGB stays 0 (black ink)

    return Image.fromarray(arr, "RGBA")


# ── Contact sheet generation ───────────────────────────────────────────────────

def _generate_contact_sheet(profile_id: str):
    """
    Build a contact sheet PNG showing all glyphs in the profile, arranged
    in a grid of 128px-high thumbnails with character labels.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    profile_dir = _PROFILES_DIR / profile_id
    glyphs_dir  = profile_dir / "glyphs"
    if not glyphs_dir.exists():
        return

    pngs = sorted(glyphs_dir.glob("*.png"))
    if not pngs:
        return

    # Layout parameters
    thumb_h    = 64
    thumb_w    = 80
    label_h    = 16
    cols       = 16
    bg_color   = (18, 18, 24)
    ink_color  = (200, 200, 210)
    label_col  = (100, 100, 120)
    border_col = (40, 40, 55)

    rows = (len(pngs) + cols - 1) // cols
    sheet_w = cols  * (thumb_w + 2) + 2
    sheet_h = rows  * (thumb_h + label_h + 4) + 4

    sheet = Image.new("RGB", (sheet_w, sheet_h), bg_color)
    draw  = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 10)
    except Exception:
        font = ImageFont.load_default()

    for idx, png in enumerate(pngs):
        col = idx % cols
        row = idx // cols
        cx  = col * (thumb_w + 2) + 2
        cy  = row * (thumb_h + label_h + 4) + 4

        # Draw cell border
        draw.rectangle([cx-1, cy-1, cx+thumb_w, cy+thumb_h+label_h+1], outline=border_col)

        # Load glyph and composite onto dark background
        try:
            glyph = Image.open(png)
            if glyph.mode != "RGBA":
                glyph = glyph.convert("RGBA")

            # Scale to fit thumbnail
            gw, gh = glyph.size
            scale  = min(thumb_w / max(1, gw), thumb_h / max(1, gh))
            nw     = max(1, int(gw * scale))
            nh     = max(1, int(gh * scale))
            glyph  = glyph.resize((nw, nh), Image.LANCZOS)

            # Center in cell
            ox = cx + (thumb_w - nw) // 2
            oy = cy + (thumb_h - nh) // 2

            # Tint alpha channel to light ink color
            cell_bg = Image.new("RGB", (thumb_w, thumb_h), bg_color)
            arr = np.array(glyph)
            alpha = arr[:, :, 3:4] / 255.0
            tinted = np.array(cell_bg.crop((0, 0, thumb_w, thumb_h)))
            # Place glyph at offset
            place = Image.new("RGB", (thumb_w, thumb_h), bg_color)
            glyph_rgb = Image.new("RGB", (nw, nh), ink_color)
            glyph_rgb.putalpha(Image.fromarray(arr[:, :, 3]))
            place.paste(glyph_rgb, (ox - cx, oy - cy), glyph_rgb)
            sheet.paste(place, (cx, cy))
        except Exception:
            pass

        # Character label below thumbnail
        from profiles.loader import _parse_glyph_stem  # noqa: reuse existing parser
        try:
            char = _parse_glyph_stem_local(png.stem)
        except Exception:
            char = png.stem[:3]

        label = char if char else png.stem[:4]
        lx = cx + thumb_w // 2
        ly = cy + thumb_h + 2
        draw.text((lx, ly), label, fill=label_col, font=font, anchor="mt")

    sheet.save(str(profile_dir / "contact_sheet.png"))


def _parse_glyph_stem_local(stem: str) -> str:
    """Minimal stem→char converter (mirrors glyph_loader._parse_glyph_stem)."""
    working = stem
    if working.endswith("_fallback"):
        working = working[:-9]
    _PUNCT = {
        "period": ".", "comma": ",", "exclaim": "!", "question": "?",
        "apostrophe": "'", "hyphen": "-", "colon": ":", "semicolon": ";",
        "lparen": "(", "rparen": ")", "hash": "#", "at": "@",
        "ampersand": "&", "slash": "/", "quote": '"',
    }
    for key, ch in _PUNCT.items():
        if working == key or working.startswith(key + "_"):
            return ch
    if working.startswith("upper_"):
        rest = working[6:]
        parts = rest.split("_")
        if parts and len(parts[0]) == 1:
            return parts[0]
        return "?"
    if working.startswith("digit_"):
        rest = working[6:]
        parts = rest.split("_")
        if parts and parts[0].isdigit():
            return parts[0]
        return "?"
    parts = working.split("_")
    if parts and len(parts[0]) == 1:
        return parts[0]
    return "?"


def _char_to_stem(char: str) -> str:
    """Map a character to its canonical filename stem."""
    _SPECIAL = {
        ".": "period", ",": "comma", "!": "exclaim", "?": "question",
        "'": "apostrophe", "-": "hyphen", ":": "colon", ";": "semicolon",
        "(": "lparen", ")": "rparen", "#": "hash", "@": "at",
        "&": "ampersand", "/": "slash", '"': "quote",
    }
    if char in _SPECIAL:
        return _SPECIAL[char]
    if char.isupper():
        return f"upper_{char}"
    if char.isdigit():
        return f"digit_{char}"
    return char


# ── Profile.json writer ────────────────────────────────────────────────────────

def _write_profile_json(profile_dir: Path, profile_id: str,
                        saved_chars: dict, source_images: list):
    """Write a canonical profile.json for a newly created profile."""
    import numpy as np
    from PIL import Image

    LOWERCASE   = set("abcdefghijklmnopqrstuvwxyz")
    UPPERCASE   = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    DIGITS      = set("0123456789")
    PUNCTUATION = set(".,!?'-:;()")

    chars = set(saved_chars.keys())
    lc    = chars & LOWERCASE
    uc    = chars & UPPERCASE
    dg    = chars & DIGITS
    pu    = chars & PUNCTUATION

    total_variants = sum(len(v) for v in saved_chars.values())

    per_character = {}
    all_widths, all_heights, all_densities = [], [], []

    glyphs_dir = profile_dir / "glyphs"

    # saved_chars: {char: [{"path": str, "confidence": float, "is_weak": bool}, ...]}
    for char, variants in saved_chars.items():
        widths, heights, confidences = [], [], []
        rel_paths = []
        for v in variants:
            rel_paths.append(v["path"])
            confidences.append(v["confidence"])
            try:
                img = Image.open(glyphs_dir / Path(v["path"]).name)
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                w, h = img.size
                arr  = np.array(img)
                dens = float((arr[:, :, 3] > 10).sum()) / max(1, arr[:, :, 3].size)
                widths.append(w)
                heights.append(h)
                all_densities.append(dens)
            except Exception:
                pass

        max_conf = max(confidences) if confidences else 0.2
        is_weak  = max_conf < 0.5

        per_character[char] = {
            "variants":          rel_paths,
            "avg_width":         round(float(np.mean(widths)),  2) if widths  else 0.0,
            "avg_height":        round(float(np.mean(heights)), 2) if heights else 0.0,
            "confidence":        round(max_conf, 3),
            "is_weak":           is_weak,
            "extraction_method": "template_cell",
        }
        all_widths.extend(widths)
        all_heights.extend(heights)

    standard = LOWERCASE | UPPERCASE | DIGITS | PUNCTUATION
    missing  = sorted(standard - chars)
    weak     = sorted(c for c, e in per_character.items() if e["is_weak"])

    profile = {
        "profile_id":    profile_id,
        "created_at":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_method": "template",
        "source_images": [str(p) for p in source_images],
        "character_coverage": {
            "lowercase_pct":   round(len(lc) / 26 * 100, 1),
            "uppercase_pct":   round(len(uc) / 26 * 100, 1),
            "digits_pct":      round(len(dg) / 10 * 100, 1),
            "punctuation_pct": round(len(pu) / 10 * 100, 1),
            "total_characters": len(chars),
            "total_variants":   total_variants,
            "lowercase_complete":   len(lc) == 26,
            "uppercase_complete":   len(uc) == 26,
            "digits_complete":      len(dg) == 10,
        },
        "per_character": per_character,
        "style_metrics": {
            "avg_glyph_width":        round(float(np.mean(all_widths)),    2) if all_widths    else 0.0,
            "median_x_height":        128.0,
            "baseline_offset":        0.0,
            "slant_estimate_degrees": 0.0,
            "avg_stroke_width":       8.0,
            "ink_density":            round(float(np.mean(all_densities)), 4) if all_densities else 0.0,
        },
        "missing_characters": missing,
        "weak_characters":    weak,
        # Partial profiles are immediately usable — fallback_dummy fills gaps
        "usable":             len(lc) >= 1,
    }

    (profile_dir / "profile.json").write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Style analysis routes ──────────────────────────────────────────────────────

@app.get("/analyze", response_class=HTMLResponse)
async def get_analyze():
    html_file = _WEB_DIR / "analyze.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>Style Analyzer</h1><p>analyze.html not found</p>"


@app.post("/api/analyze-style")
async def api_analyze_style(image: UploadFile = File(...)):
    """Analyze handwriting style from an uploaded image. Returns 11 scores (0–100)."""
    contents = await image.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty image file")

    try:
        sys.path.insert(0, str(_ROOT))
        from analysis.style_analyzer import analyze_style
        scores = analyze_style(contents)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    return JSONResponse({"success": True, "scores": scores})


class ApplyStyleRequest(BaseModel):
    scores: dict


@app.post("/api/apply-style")
async def api_apply_style(request: ApplyStyleRequest):
    """Map 11 style scores to HandwritingRenderer and realism engine parameters."""
    if not request.scores:
        raise HTTPException(status_code=400, detail="No scores provided")

    try:
        from analysis.parameter_mapper import map_all
        params = map_all(request.scores)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mapping failed: {exc}")

    return JSONResponse({"success": True, "params": params})


@app.delete("/api/glyph/{profile}/{filename}")
async def delete_glyph(profile: str, filename: str):
    """Delete a single glyph PNG from a profile."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _PROFILES_DIR / profile / "glyphs" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Glyph not found")
    path.unlink()
    _GLYPH_BANKS.pop(profile, None)
    return JSONResponse({"success": True})


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
