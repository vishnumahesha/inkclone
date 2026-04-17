"""
profiles/migrate.py — InkClone Profile Migrator

Reads existing profile directories (freeform_vishnu, template_vishnu, etc.)
and generates a canonical profile.json for each, based on the formal schema.

Usage:
    python profiles/migrate.py                        # migrate all
    python profiles/migrate.py freeform_vishnu        # migrate one
    python profiles/migrate.py --dry-run              # show what would be written

Each generated profile.json sits at profiles/{name}/profile.json and validates
against profiles/schema/profile.schema.json.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

_HERE = Path(__file__).parent          # profiles/
_INKCLONE = _HERE.parent               # project root

sys.path.insert(0, str(_INKCLONE))

from PIL import Image

# Standard sets
_LOWERCASE   = set("abcdefghijklmnopqrstuvwxyz")
_UPPERCASE   = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DIGITS      = set("0123456789")
_PUNCTUATION = set(".,!?'-:;()")

_PUNCT_ALIASES = {
    "period": ".",  "comma": ",",  "exclaim": "!",  "question": "?",
    "apostrophe": "'",  "hyphen": "-",  "colon": ":",  "semicolon": ";",
    "lparen": "(",  "rparen": ")", "hash": "#", "at": "@",
    "ampersand": "&", "slash": "/", "quote": '"',
}

_MIN_INK_DENSITY = 0.03   # glyphs below this are considered noise
_MIN_CHARS_USABLE = 26    # need full a-z for usable=True


# ── Filename parsing ───────────────────────────────────────────────────────────

def _stem_to_char(stem: str) -> str | None:
    """Map a glyph filename stem to its character.

    Examples:
      a_0              → 'a'
      upper_P_0        → 'P'
      upper_T_fallback → 'T'
      digit_0_0        → '0'
      digit_5_fallback → '5'
      period_0         → '.'
      comma_0          → ','
    """
    working = stem
    if working.endswith("_fallback"):
        working = working[: -len("_fallback")]

    # Punctuation aliases
    for alias, ch in _PUNCT_ALIASES.items():
        if working == alias or working.startswith(alias + "_"):
            return ch

    if working.startswith("upper_"):
        rest = working[len("upper_") :]
        parts = rest.split("_")
        if parts and len(parts[0]) == 1 and parts[0].isupper():
            return parts[0]
        return None

    if working.startswith("digit_"):
        rest = working[len("digit_") :]
        parts = rest.split("_")
        if parts and parts[0].isdigit():
            return parts[0]
        return None

    parts = working.split("_")
    if parts and len(parts[0]) == 1:
        return parts[0]

    return None


def _extraction_method(stem: str, source_method: str) -> str:
    """Determine extraction method from filename and profile source method."""
    if stem.endswith("_fallback"):
        return "fallback"
    if source_method == "template":
        return "template_cell"
    return "connected_component"


# ── Image analysis ─────────────────────────────────────────────────────────────

def _analyse_glyph(img_path: Path) -> dict:
    """
    Measure a single glyph PNG.

    Returns:
        width, height, ink_density (ratio of alpha>0 pixels), confidence (0-1)
    """
    try:
        img = Image.open(img_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        arr = np.array(img, dtype=np.float32)
        w, h = img.size
        alpha = arr[:, :, 3]
        total = alpha.size
        ink = (alpha > 10).sum()
        density = float(ink) / total if total > 0 else 0.0
        return {"width": w, "height": h, "ink_density": density, "ok": True}
    except Exception as exc:
        return {"width": 0, "height": 0, "ink_density": 0.0, "ok": False, "error": str(exc)}


def _density_to_confidence(density: float, is_fallback: bool) -> float:
    """
    Convert ink density to a confidence score 0-1.

    Rules:
    - Programmatic fallback glyphs get 0.70 (good quality but not real handwriting)
    - Density < MIN_INK_DENSITY: 0.20 (very sparse — likely noise)
    - Density in [0.03, 0.08]: scale linearly 0.30 → 0.60
    - Density in [0.08, 0.40]: scale linearly 0.60 → 0.95
    - Density > 0.40: 0.90 (very dense; possibly overlapping/thick)
    """
    if is_fallback:
        return 0.70
    if density < _MIN_INK_DENSITY:
        return 0.20
    if density < 0.08:
        t = (density - _MIN_INK_DENSITY) / (0.08 - _MIN_INK_DENSITY)
        return round(0.30 + t * 0.30, 3)
    if density < 0.40:
        t = (density - 0.08) / (0.40 - 0.08)
        return round(0.60 + t * 0.35, 3)
    return 0.90


def _estimate_stroke_width(img_path: Path) -> float:
    """
    Estimate average stroke width in pixels using horizontal scan lines.

    For each row that contains ink, count the mean length of ink 'runs'.
    """
    try:
        img = Image.open(img_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        arr = np.array(img)
        alpha = arr[:, :, 3] > 10  # ink mask (H, W)
        run_lengths = []
        for row in alpha:
            if not row.any():
                continue
            # Count ink pixel groups
            in_run = False
            run_len = 0
            for px in row:
                if px:
                    run_len += 1
                    in_run = True
                else:
                    if in_run and run_len > 0:
                        run_lengths.append(run_len)
                    in_run = False
                    run_len = 0
            if in_run and run_len > 0:
                run_lengths.append(run_len)
        if not run_lengths:
            return 0.0
        # Stroke width ≈ median horizontal run length
        return float(np.median(run_lengths))
    except Exception:
        return 0.0


def _estimate_slant(glyphs_dir: Path, char_entries: dict) -> float:
    """
    Rough slant estimate: for several lowercase letters, compare left/right
    ink column centroids between top half and bottom half.
    Returns slant in degrees (positive = right-leaning).
    """
    angles = []
    test_chars = ["a", "e", "h", "l", "n", "o", "r"]
    for ch in test_chars:
        entry = char_entries.get(ch)
        if not entry:
            continue
        for rel in entry["variants"][:1]:
            path = glyphs_dir / rel
            try:
                img = Image.open(path)
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                arr = np.array(img)
                alpha = arr[:, :, 3] > 10
                H, W = alpha.shape
                if H < 10 or W < 4:
                    continue
                top_half = alpha[: H // 2, :]
                bot_half = alpha[H // 2 :, :]
                if top_half.any() and bot_half.any():
                    top_cx = float(np.where(top_half)[1].mean())
                    bot_cx = float(np.where(bot_half)[1].mean())
                    import math
                    angle = math.degrees(math.atan2(top_cx - bot_cx, H // 2))
                    angles.append(angle)
            except Exception:
                pass
    return round(float(np.mean(angles)), 2) if angles else 0.0


# ── Profile builder ────────────────────────────────────────────────────────────

def build_profile(profile_dir: Path, source_method: str = "freeform") -> dict:
    """
    Scan a profile directory and build a canonical profile dict.

    Args:
        profile_dir: Path to the profile directory (e.g. profiles/freeform_vishnu)
        source_method: "template", "freeform", or "hybrid"

    Returns:
        A dict conforming to profile.schema.json
    """
    profile_id = profile_dir.name
    glyphs_dir = profile_dir / "glyphs"

    if not glyphs_dir.exists():
        raise FileNotFoundError(f"Glyphs directory not found: {glyphs_dir}")

    pngs = sorted(glyphs_dir.glob("*.png"))
    print(f"  [{profile_id}] Found {len(pngs)} PNG files in {glyphs_dir}")

    # ── Group PNGs by character ────────────────────────────────────────────────
    char_map: dict[str, list] = {}  # char → list of (rel_path, analysis, stem)
    for png in pngs:
        char = _stem_to_char(png.stem)
        if char is None:
            print(f"  [migrate] Skipping unrecognised file: {png.name}")
            continue
        analysis = _analyse_glyph(png)
        stem = png.stem
        rel = f"glyphs/{png.name}"
        if char not in char_map:
            char_map[char] = []
        char_map[char].append((rel, analysis, stem))

    # ── Build per_character ────────────────────────────────────────────────────
    per_character: dict = {}
    all_widths: list = []
    all_heights: list = []
    all_densities: list = []
    all_stroke_widths: list = []

    for char, entries in sorted(char_map.items()):
        widths  = [e[1]["width"]  for e in entries if e[1]["ok"]]
        heights = [e[1]["height"] for e in entries if e[1]["ok"]]
        densities = [e[1]["ink_density"] for e in entries if e[1]["ok"]]

        avg_w = round(float(np.mean(widths)),  2) if widths  else 0.0
        avg_h = round(float(np.mean(heights)), 2) if heights else 0.0
        avg_d = float(np.mean(densities)) if densities else 0.0

        # Use best variant's density for confidence
        max_d = max(densities) if densities else 0.0
        is_fallback = all(e[2].endswith("_fallback") for e in entries)
        confidence = _density_to_confidence(max_d, is_fallback)

        method = _extraction_method(entries[0][2], source_method)

        per_character[char] = {
            "variants": [e[0] for e in entries],
            "avg_width": avg_w,
            "avg_height": avg_h,
            "confidence": confidence,
            "extraction_method": method,
        }

        all_widths.extend(widths)
        all_heights.extend(heights)
        all_densities.extend(densities)

    # ── Stroke width (sample up to 20 glyphs for speed) ───────────────────────
    sample_pngs = pngs[:20]
    for png in sample_pngs:
        sw = _estimate_stroke_width(png)
        if sw > 0:
            all_stroke_widths.append(sw)

    avg_stroke = round(float(np.mean(all_stroke_widths)), 2) if all_stroke_widths else 0.0

    # ── Slant estimate ─────────────────────────────────────────────────────────
    slant = _estimate_slant(glyphs_dir, per_character)

    # ── Style metrics ──────────────────────────────────────────────────────────
    # x_height: median height of short lowercase glyphs (a,c,e,m,n,o,r,s,u,v,w,x,z)
    x_chars = set("acemnorsuvwxz")
    x_heights = []
    for ch in x_chars:
        entry = per_character.get(ch)
        if entry:
            x_heights.append(entry["avg_height"])
    median_x_height = round(float(np.median(x_heights)), 2) if x_heights else (
        round(float(np.median(all_heights)), 2) if all_heights else 0.0
    )

    style_metrics = {
        "avg_glyph_width":      round(float(np.mean(all_widths)),   2) if all_widths   else 0.0,
        "median_x_height":      median_x_height,
        "baseline_offset":      0.0,   # not derivable from static images; default
        "slant_estimate_degrees": slant,
        "avg_stroke_width":     avg_stroke,
        "ink_density":          round(float(np.mean(all_densities)), 4) if all_densities else 0.0,
    }

    # ── Coverage ───────────────────────────────────────────────────────────────
    chars = set(per_character.keys())
    lc = chars & _LOWERCASE
    uc = chars & _UPPERCASE
    dg = chars & _DIGITS
    pu = chars & _PUNCTUATION
    total_variants = sum(len(e["variants"]) for e in per_character.values())

    character_coverage = {
        "lowercase_pct":  round(len(lc) / len(_LOWERCASE)   * 100, 1),
        "uppercase_pct":  round(len(uc) / len(_UPPERCASE)   * 100, 1),
        "digits_pct":     round(len(dg) / len(_DIGITS)      * 100, 1),
        "punctuation_pct":round(len(pu) / len(_PUNCTUATION) * 100, 1),
        "total_characters": len(chars),
        "total_variants":   total_variants,
    }

    # ── Missing / weak characters ──────────────────────────────────────────────
    standard_chars = _LOWERCASE | _UPPERCASE | _DIGITS | _PUNCTUATION
    missing = sorted(standard_chars - chars)
    weak    = sorted(
        ch for ch, entry in per_character.items()
        if entry["confidence"] < 0.5
    )

    # ── Source images from existing metadata (best-effort) ────────────────────
    source_images: list = []
    old_meta = profile_dir / "metadata.json"
    if old_meta.exists():
        try:
            old = json.loads(old_meta.read_text())
            src = old.get("source_images") or old.get("source_image") or []
            if isinstance(src, str):
                src = [src]
            source_images = src
        except Exception:
            pass

    usable = len(lc) >= _MIN_CHARS_USABLE

    return {
        "profile_id":         profile_id,
        "created_at":         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_method":      source_method,
        "source_images":      source_images,
        "character_coverage": character_coverage,
        "per_character":      per_character,
        "style_metrics":      style_metrics,
        "missing_characters": missing,
        "weak_characters":    weak,
        "usable":             usable,
    }


# ── Per-profile config ─────────────────────────────────────────────────────────

# Default source_method per profile_id; override here if needed.
_PROFILE_SOURCE_METHOD: dict[str, str] = {
    "template_vishnu":  "template",
    "freeform_vishnu":  "freeform",
    "improved_vishnu":  "freeform",
    "hybrid_vishnu":    "hybrid",
}


def _infer_source_method(profile_id: str) -> str:
    if profile_id in _PROFILE_SOURCE_METHOD:
        return _PROFILE_SOURCE_METHOD[profile_id]
    if "template" in profile_id:
        return "template"
    if "freeform" in profile_id or "free" in profile_id:
        return "freeform"
    return "freeform"


# ── Main migration logic ───────────────────────────────────────────────────────

def migrate_profile(profile_dir: Path, dry_run: bool = False) -> dict | None:
    """
    Build and write profile.json for a single profile directory.

    Returns the profile dict, or None if the directory has no glyphs.
    """
    glyphs_dir = profile_dir / "glyphs"
    if not glyphs_dir.exists():
        print(f"  [migrate] Skipping {profile_dir.name}: no glyphs/ dir")
        return None

    pngs = list(glyphs_dir.glob("*.png"))
    if not pngs:
        print(f"  [migrate] Skipping {profile_dir.name}: glyphs/ is empty")
        return None

    print(f"\n=== Migrating: {profile_dir.name} ===")
    source_method = _infer_source_method(profile_dir.name)
    print(f"  source_method: {source_method}")

    profile = build_profile(profile_dir, source_method=source_method)

    out_path = profile_dir / "profile.json"
    if dry_run:
        print(f"  [dry-run] Would write {out_path}")
        print(f"  Characters: {profile['character_coverage']['total_characters']}")
        print(f"  Coverage: lower={profile['character_coverage']['lowercase_pct']}%  "
              f"upper={profile['character_coverage']['uppercase_pct']}%  "
              f"digits={profile['character_coverage']['digits_pct']}%  "
              f"punct={profile['character_coverage']['punctuation_pct']}%")
        print(f"  Usable: {profile['usable']}")
        print(f"  Missing: {profile['missing_characters'][:10]}{'...' if len(profile['missing_characters']) > 10 else ''}")
        print(f"  Weak: {profile['weak_characters'][:10]}{'...' if len(profile['weak_characters']) > 10 else ''}")
    else:
        out_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Written: {out_path}")
        print(f"  Characters: {profile['character_coverage']['total_characters']}  "
              f"({profile['character_coverage']['total_variants']} variants)")
        print(f"  Coverage: lower={profile['character_coverage']['lowercase_pct']}%  "
              f"upper={profile['character_coverage']['uppercase_pct']}%  "
              f"digits={profile['character_coverage']['digits_pct']}%  "
              f"punct={profile['character_coverage']['punctuation_pct']}%")
        print(f"  Style metrics: x_height={profile['style_metrics']['median_x_height']:.1f}px  "
              f"slant={profile['style_metrics']['slant_estimate_degrees']:.1f}°  "
              f"ink_density={profile['style_metrics']['ink_density']:.4f}")
        print(f"  Usable: {profile['usable']}")
        if profile['missing_characters']:
            n = len(profile['missing_characters'])
            preview = profile['missing_characters'][:10]
            print(f"  Missing ({n}): {preview}{'...' if n > 10 else ''}")
        if profile['weak_characters']:
            n = len(profile['weak_characters'])
            preview = profile['weak_characters'][:10]
            print(f"  Weak ({n}):    {preview}{'...' if n > 10 else ''}")

    return profile


def migrate_all(profile_ids: list[str] | None = None,
                dry_run: bool = False) -> dict[str, dict]:
    """
    Migrate all (or specified) profiles in the profiles/ directory.

    Returns:
        {profile_id: profile_dict} for each successfully migrated profile.
    """
    results = {}

    if profile_ids:
        dirs = [_HERE / pid for pid in profile_ids]
    else:
        dirs = [
            d for d in sorted(_HERE.iterdir())
            if d.is_dir() and not d.name.startswith(".") and d.name != "schema"
        ]

    for pdir in dirs:
        if not pdir.exists():
            print(f"\n[migrate] Profile directory not found: {pdir}")
            continue
        try:
            result = migrate_profile(pdir, dry_run=dry_run)
            if result is not None:
                results[pdir.name] = result
        except Exception as exc:
            print(f"\n[migrate] ERROR migrating {pdir.name}: {exc}")

    return results


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    ids = [a for a in args if not a.startswith("--")]

    print("=" * 60)
    print("InkClone Profile Migrator")
    print("=" * 60)
    if dry_run:
        print("(dry-run mode — no files will be written)\n")

    results = migrate_all(profile_ids=ids or None, dry_run=dry_run)

    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    for pid, profile in results.items():
        cc = profile["character_coverage"]
        print(f"  {pid:25s} "
              f"chars={cc['total_characters']:3d}  "
              f"variants={cc['total_variants']:4d}  "
              f"lower={cc['lowercase_pct']:5.1f}%  "
              f"usable={profile['usable']}")

    print(f"\nMigrated {len(results)} profile(s).")

    if not dry_run and results:
        print("\nValidating written profiles via loader…")
        import importlib.util
        spec = importlib.util.spec_from_file_location("loader", _HERE / "loader.py")
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        for pid in results:
            try:
                p = loader.load_profile(pid)
                print(f"  [OK] {pid}")
            except Exception as exc:
                print(f"  [FAIL] {pid}: {exc}")
