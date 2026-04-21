"""
InkClone Web Interface Backend
FastAPI server for handwriting document generation
"""

import sys
import os
import json
import shutil
from pathlib import Path
from io import BytesIO
import base64
from datetime import datetime, timezone
from typing import List

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
    from glyph_loader import _parse_glyph_stem
    pid = profile_id or _DEFAULT_PROFILE
    glyphs_dir = _PROFILES_DIR / pid / "glyphs"
    if not glyphs_dir.exists():
        glyphs_dir = _PROFILES_DIR / _DEFAULT_PROFILE / "glyphs"
    pngs = list(glyphs_dir.glob("*.png"))
    chars = {_parse_glyph_stem(p.stem) for p in pngs if _parse_glyph_stem(p.stem) is not None}
    return JSONResponse({
        "total_variants": len(pngs),
        "unique_chars":   len(chars),
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

    results = []
    for entry in sorted(_PROFILES_DIR.iterdir()):
        if not entry.is_dir():
            continue
        # Skip non-profile directories (e.g. template photos)
        glyphs_dir = entry / "glyphs"
        if not glyphs_dir.exists():
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


@app.post("/api/extract-template")
async def extract_template_api(
    page1: UploadFile = File(None),
    page2: UploadFile = File(None),
    page3: UploadFile = File(None),
    page4: UploadFile = File(None),
    profile_name: str = Form("my_handwriting"),
):
    """Setup-page endpoint: accepts named page files with known page identity."""
    # Build list of (UploadFile, page_number) pairs preserving page identity
    page_uploads = []
    for pg_num, upload in [(1, page1), (2, page2), (3, page3), (4, page4)]:
        if upload is not None:
            page_uploads.append((upload, pg_num))
    if not page_uploads:
        raise HTTPException(status_code=400, detail="No images provided")

    response = await create_profile(page_uploads=page_uploads, profile_name=profile_name)
    return response


@app.post("/profiles/create")
async def create_profile(
    images: List[UploadFile] = File(None),
    profile_name: str = Form("my_handwriting"),
    page_uploads: list = None,
):
    """
    Accept 1–4 handwriting template photos, extract glyphs, build a profile.
    Uses extract_v6-style pipeline: warp to 2550×3300, red channel, threshold 160.
    """
    import re

    # Handle both calling conventions: page_uploads from /api/extract-template,
    # or raw images list from /profiles/create
    if page_uploads is None:
        if not images:
            raise HTTPException(status_code=400, detail="No images provided")
        if len(images) > 4:
            raise HTTPException(status_code=400, detail="Maximum 4 images allowed")
        # Assume page order matches upload order
        page_uploads = [(img, idx + 1) for idx, img in enumerate(images)]

    # ── 1. Save uploads ────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_dir = _UPLOADS_DIR / ts
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_pages: list[tuple[Path, int]] = []  # (file_path, page_number)
    for img_file, pg_num in page_uploads:
        ext = Path(img_file.filename or "image.jpg").suffix.lower() or ".jpg"
        dst = upload_dir / f"page_{pg_num}{ext}"
        contents = await img_file.read()
        dst.write_bytes(contents)
        saved_pages.append((dst, pg_num))

    # Profile naming
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', profile_name.strip()) if profile_name else ""
    profile_id = safe_name if safe_name else f"profile_{ts}"

    # ── 1b. Image quality gate ─────────────────────────────────────────────────
    all_warnings: list[str] = []
    for path, pg_num in saved_pages:
        page_warnings = _check_image_quality(path)
        for w in page_warnings:
            all_warnings.append(f"Page {pg_num}: {w}" if len(saved_pages) > 1 else w)

    # ── 2-6. Extract glyphs using v7 template pipeline ─────────────────────────
    profile_dir = _PROFILES_DIR / profile_id
    glyphs_dir = profile_dir / "glyphs"
    glyphs_dir.mkdir(parents=True, exist_ok=True)

    try:
        glyph_bank = _extract_v7_template(saved_pages)
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
    saved_chars: dict[str, list] = {}
    for char, glyph_imgs in glyph_bank.items():
        char_name = _char_to_stem(char)
        for v_idx, glyph_img in enumerate(glyph_imgs):
            fname = f"{char_name}_{v_idx}.png"
            glyph_img.save(str(glyphs_dir / fname))
            saved_chars.setdefault(char, []).append({
                "path": f"glyphs/{fname}",
                "confidence": 1.0,
                "is_weak": False,
            })

    _write_profile_json(profile_dir, profile_id, saved_chars, [p for p, _ in saved_pages])

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

    unique_characters = len(saved_chars)

    return JSONResponse({
        "success":           True,
        "profile":           profile_id,
        "profile_id":        profile_id,
        "total_glyphs":      total_glyphs,
        "unique_characters": unique_characters,
        "coverage_pct":      coverage_pct,
        "uppercase_pct":     uppercase_pct,
        "digits_pct":        digits_pct,
        "weak_chars":        weak_chars,
        "coverage_report":   coverage_report,
        "warnings":          all_warnings,
        "contact_sheet_url": f"/profiles/{profile_id}/contact_sheet.png",
    })


# ── Extraction pipeline (v7 template-aware) ───────────────────────────────────
#
# Mirrors extract_v6.py logic: warp to 2550×3300, red channel only,
# fixed threshold 160, known page layouts and character mappings.

_WARP_W, _WARP_H = 2550, 3300

# Template margin ratios (8.5"×11" letter paper)
_ML_RATIO = 0.5 / 8.5    # left margin
_MT_RATIO = 0.95 / 11.0  # top margin
_MR_RATIO = 0.5 / 8.5    # right margin
_MB_RATIO = 0.45 / 11.0  # bottom margin

_SMALL_CHARS = {'.', ',', "'", '"', '-', ':', ';', '!'}


def _page_cells(pg: int) -> list[str]:
    """Character sequence for each template page (matches extract_v6.py)."""
    if pg == 1:
        return [c for c in 'abcdefghijklmno' for _ in range(4)]
    if pg == 2:
        return [c for c in 'pqrstuvwxyz' for _ in range(4)]
    if pg == 3:
        return [c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' for _ in range(2)]
    # Page 4: digits + punctuation + bigrams
    cells = [d for d in '0123456789' for _ in range(3)]
    punct = ['.', ',', '!', '?', "'", '"', '-', ':', ';',
             '(', ')', '/', '@', '&', '#', '$']
    cells += [p for p in punct for _ in range(2)]
    cells += ['th', 'he', 'in', 'an', 'er', 'on', 'ed', 're', 'ou', 'es',
              'ti', 'at', 'st', 'en', 'or', 'ng', 'ing', 'the', 'and', 'tion']
    return cells


def _page_grid(pg: int) -> tuple:
    """Return (cols, rows, margin_left, margin_top, cell_w, cell_h) at 2550×3300."""
    ml = int(_WARP_W * _ML_RATIO)
    mt = int(_WARP_H * _MT_RATIO)
    gw = _WARP_W - ml - int(_WARP_W * _MR_RATIO)
    gh = _WARP_H - mt - int(_WARP_H * _MB_RATIO)
    cols, rows = (6, 10) if pg <= 3 else (8, 11)
    return cols, rows, ml, mt, gw / cols, gh / rows


def _find_corners(gray):
    """Find 4 corner markers as largest dark blob per quadrant (from extract_v6)."""
    import cv2
    import numpy as np

    _, binarized = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
    n_comp, _, stats, centroids = cv2.connectedComponentsWithStats(binarized, 8)
    h, w = gray.shape
    blobs = []
    for i in range(1, n_comp):
        area = stats[i, cv2.CC_STAT_AREA]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        if area > 50 and bh > 0 and 0.3 < bw / bh < 3.0:
            blobs.append((area, float(centroids[i, 0]), float(centroids[i, 1])))
    mid_x, mid_y = w / 2, h / 2
    quadrants = {
        'TL': [b for b in blobs if b[1] < mid_x and b[2] < mid_y],
        'TR': [b for b in blobs if b[1] >= mid_x and b[2] < mid_y],
        'BL': [b for b in blobs if b[1] < mid_x and b[2] >= mid_y],
        'BR': [b for b in blobs if b[1] >= mid_x and b[2] >= mid_y],
    }
    fallback = {
        'TL': (w * .02, h * .02), 'TR': (w * .98, h * .02),
        'BL': (w * .02, h * .98), 'BR': (w * .98, h * .98),
    }
    corners = {}
    for q, qblobs in quadrants.items():
        if qblobs:
            best = max(qblobs, key=lambda x: x[0])
            corners[q] = (best[1], best[2])
        else:
            corners[q] = fallback[q]
    return corners


def _perspective_warp(img, corners):
    """Warp image to 2550×3300 using detected corners (from extract_v6)."""
    import cv2
    import numpy as np

    src = np.array([corners['TL'], corners['TR'],
                    corners['BR'], corners['BL']], np.float32)
    dst = np.array([[0, 0], [_WARP_W, 0],
                    [_WARP_W, _WARP_H], [0, _WARP_H]], np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    is_upscale = _WARP_W > img.shape[1]
    interp = cv2.INTER_CUBIC if is_upscale else cv2.INTER_AREA
    return cv2.warpPerspective(img, matrix, (_WARP_W, _WARP_H), flags=interp)


def _extract_glyph_cell(warped_bgr, col, row, ml, mt, cw, ch, char_name=''):
    """Extract one cell using RED CHANNEL — blue guide lines are invisible.
    Matches extract_v6.extract_glyph exactly."""
    import cv2
    import numpy as np
    from PIL import Image

    scale = _WARP_W / 2550.0
    inward_x = max(3, int(cw * 0.03))
    inward_y = max(3, int(ch * 0.03))
    pad = max(2, int(4 * scale))

    x0 = int(round(ml + col * cw)) + inward_x
    y0 = int(round(mt + row * ch)) + inward_y
    x1 = min(_WARP_W, int(round(ml + (col + 1) * cw)) - inward_x)
    y1 = min(_WARP_H, int(round(mt + (row + 1) * ch)) - inward_y)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None

    cell = warped_bgr[y0:y1, x0:x1].copy()
    cell_h = cell.shape[0]

    # White out label zone (top 15% of cell)
    label_mask_h = int(cell_h * 0.15)
    cell[:label_mask_h, :] = [255, 255, 255]

    # RED CHANNEL ONLY — threshold 160 (matches extract_v6)
    red_channel = cell[:, :, 2]  # OpenCV BGR: index 2 = Red
    _, binarized = cv2.threshold(red_channel, 160, 255, cv2.THRESH_BINARY_INV)

    # Morphological open with 2×2 kernel to clean noise
    binarized = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    # Remove small connected components (noise)
    cc_min = max(5, int(12 * scale))
    n_cc, labels, cc_stats, _ = cv2.connectedComponentsWithStats(binarized, 8)
    for i in range(1, n_cc):
        if cc_stats[i, cv2.CC_STAT_AREA] < cc_min:
            binarized[labels == i] = 0

    # Autocrop to ink bounding box with 4px padding
    ink_coords = np.argwhere(binarized > 0)
    min_ink_small = max(5, int(15 * scale))
    min_ink = min_ink_small if char_name in _SMALL_CHARS else max(10, int(35 * scale))
    if len(ink_coords) < min_ink:
        return None

    y_min, x_min = ink_coords.min(axis=0)
    y_max, x_max = ink_coords.max(axis=0)
    y_min = max(0, y_min - pad)
    x_min = max(0, x_min - pad)
    y_max = min(binarized.shape[0] - 1, y_max + pad)
    x_max = min(binarized.shape[1] - 1, x_max + pad)
    crop = binarized[y_min:y_max + 1, x_min:x_max + 1]

    min_crop = max(4, int(8 * scale))
    if crop.shape[0] < min_crop or crop.shape[1] < min_crop:
        return None

    # RGBA: black ink on transparent background
    rgba = np.zeros((*crop.shape, 4), np.uint8)
    rgba[crop > 128] = [0, 0, 0, 240]
    return Image.fromarray(rgba, 'RGBA')


def _extract_v7_template(saved_pages: list) -> dict:
    """
    Main extraction pipeline for v7 blue templates.
    Mirrors extract_v6.run() — warp to 2550×3300, red channel, known page layouts.

    Args: saved_pages — list of (file_path, page_number) tuples
    Returns: {char: [PIL.Image (RGBA), ...]}
    """
    import cv2
    import numpy as np

    bank: dict[str, list] = {}

    for img_path, pg in saved_pages:
        img_cv = cv2.imread(str(img_path))
        if img_cv is None:
            continue

        # Corner detection on grayscale (only for warp — NOT for extraction)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        corners = _find_corners(gray)

        # Warp color image to 2550×3300
        warped = _perspective_warp(img_cv, corners)

        # Get page-specific grid and character mapping
        cols, rows, ml, mt, cw, ch = _page_grid(pg)
        cells = _page_cells(pg)

        for idx, char in enumerate(cells):
            col = idx % cols
            row = idx // cols
            if row >= rows:
                break
            glyph = _extract_glyph_cell(warped, col, row, ml, mt, cw, ch,
                                         char_name=char)
            if glyph is not None:
                bank.setdefault(char, []).append(glyph)

    return bank


def _check_image_quality(img_path: Path) -> list:
    """Return user-facing warning strings for sharpness, brightness, and aspect ratio."""
    import cv2

    img_cv = cv2.imread(str(img_path))
    if img_cv is None:
        return []

    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    warnings_out = []

    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if lap_var < 50:
        warnings_out.append("Photo is blurry — try holding steadier")

    mean_val = float(gray.mean())
    if mean_val < 80:
        warnings_out.append("Photo is too dark")
    elif mean_val > 220:
        warnings_out.append("Photo is overexposed")

    portrait_ratio = min(w, h) / max(w, h)
    if abs(portrait_ratio - 0.773) > 0.15:
        warnings_out.append("Photo may be cropped incorrectly")

    return warnings_out


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
        "(": "lparen", ")": "rparen", "#": "hash", "@": "atsign",
        "&": "ampersand", "/": "slash", '"': "quote", "$": "dollar",
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
