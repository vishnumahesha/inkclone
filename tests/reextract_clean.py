#!/usr/bin/env python3
"""Re-extract vishnu_blue_v1 source images using the fixed pipeline → vishnu_blue_v3_clean."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

SOURCE_IMAGES = [
    ROOT / "data/uploads/20260420_190030/page_1.jpeg",
    ROOT / "data/uploads/20260420_190030/page_2.jpeg",
    ROOT / "data/uploads/20260420_190030/page_3.jpeg",
    ROOT / "data/uploads/20260420_190030/page_4.jpeg",
]
PROFILE_NAME = "vishnu_blue_v3_clean"


def _load_app_functions():
    """Load only the extraction functions from web/app.py without starting FastAPI."""
    app_path = ROOT / "web" / "app.py"
    source = app_path.read_text()

    # Replace FastAPI decorators/setup with no-ops so we can import as a plain module
    replacements = [
        ("from fastapi", "# from fastapi"),
        ("from starlette", "# from starlette"),
        ("import uvicorn", "# import uvicorn"),
        ("app = FastAPI(", "# app = FastAPI("),
        ("app.add_middleware(", "# app.add_middleware("),
        ("app.mount(", "# app.mount("),
        ("app.include_router(", "# app.include_router("),
        ("@app.post(", "# @app.post("),
        ("@app.get(", "# @app.get("),
        ("templates = Jinja2Templates(", "# templates = Jinja2Templates("),
    ]
    for old, new in replacements:
        source = source.replace(old, new)

    # Prepend stubs for FastAPI types used in function signatures
    stub = (
        "File = Form = lambda *a, **kw: None\n"
        "UploadFile = object\n"
        "HTTPException = Exception\n"
        "JSONResponse = FileResponse = dict\n"
        "StaticFiles = Jinja2Templates = lambda *a, **kw: None\n"
        "CORSMiddleware = object\n"
        "APIRouter = type('APIRouter', (), {'get': lambda *a,**kw: (lambda f:f), 'post': lambda *a,**kw: (lambda f:f)})\n"
    )
    source = stub + source

    # Write a temp module
    tmp = ROOT / "tests" / "_app_tmp.py"
    tmp.write_text(source)
    spec = importlib.util.spec_from_file_location("_app_tmp", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "web"))
    spec.loader.exec_module(mod)
    return mod


def run():
    print("Loading extraction pipeline...")
    mod = _load_app_functions()

    pages = [(p, i + 1) for i, p in enumerate(SOURCE_IMAGES) if p.exists()]
    print(f"Re-extracting {len(pages)} pages → {PROFILE_NAME} ...")
    glyph_bank = mod._extract_v7_template(pages)
    total = sum(len(v) for v in glyph_bank.values())
    print(f"  Extracted {len(glyph_bank)} characters, {total} total glyphs")

    out_dir = ROOT / "profiles" / PROFILE_NAME / "glyphs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for char, imgs in glyph_bank.items():
        stem = mod._char_to_stem(char)
        for idx, img in enumerate(imgs):
            img.save(str(out_dir / f"{stem}_{idx}.png"))

    # Write minimal profile.json
    saved_chars = {}
    for char, imgs in glyph_bank.items():
        stem = mod._char_to_stem(char)
        saved_chars[char] = [{"path": f"glyphs/{stem}_{i}.png", "confidence": 1.0, "is_weak": False}
                              for i in range(len(imgs))]
    profile_data = {
        "profile_id": PROFILE_NAME,
        "source_images": [str(p) for p, _ in pages],
        "characters": saved_chars,
        "created_at": "2026-04-21",
    }
    (ROOT / "profiles" / PROFILE_NAME / "profile.json").write_text(
        json.dumps(profile_data, indent=2))

    print(f"  Saved {total} glyphs to {out_dir}")
    print("Done.")

    # Clean up temp file
    tmp = ROOT / "tests" / "_app_tmp.py"
    if tmp.exists():
        tmp.unlink()


if __name__ == "__main__":
    run()
