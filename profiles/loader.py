"""
profiles/loader.py — InkClone Profile Loader

Loads, validates, and queries handwriting profiles in the canonical schema.

Usage:
    from profiles.loader import load_profile, list_profiles, compute_coverage

    profile = load_profile("freeform_vishnu")
    ids = list_profiles()
    cov = compute_coverage(profile)
"""

import json
import os
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent          # profiles/
_SCHEMA_PATH = _THIS_DIR / "schema" / "profile.schema.json"

# Standard sets used for coverage %
_LOWERCASE  = set("abcdefghijklmnopqrstuvwxyz")
_UPPERCASE  = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DIGITS     = set("0123456789")
_PUNCTUATION = set(".,!?'-:;()")

# Minimum criteria for usable=True
_MIN_CHARS_USABLE = 26  # full lowercase alphabet


# ── Schema loading ─────────────────────────────────────────────────────────────

def _load_schema() -> dict:
    """Load and cache the JSON Schema from disk."""
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Profile schema not found at {_SCHEMA_PATH}")
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


_CACHED_SCHEMA: dict | None = None


def _get_schema() -> dict:
    global _CACHED_SCHEMA
    if _CACHED_SCHEMA is None:
        _CACHED_SCHEMA = _load_schema()
    return _CACHED_SCHEMA


# ── Validation ─────────────────────────────────────────────────────────────────

def validate_profile(profile_path: str | Path) -> dict:
    """
    Load and validate a profile.json against the canonical schema.

    Args:
        profile_path: Path to the profile.json file (or directory containing it).

    Returns:
        The parsed profile dict if valid.

    Raises:
        FileNotFoundError: If the profile.json does not exist.
        ValueError: If the profile fails schema validation or has dangling glyph paths.
    """
    profile_path = Path(profile_path)
    if profile_path.is_dir():
        profile_path = profile_path / "profile.json"

    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)

    _validate_required_keys(profile, profile_path)
    _validate_types(profile, profile_path)
    _validate_per_character(profile, profile_path)
    return profile


def _validate_required_keys(profile: dict, path: Path):
    schema = _get_schema()
    required = schema.get("required", [])
    missing = [k for k in required if k not in profile]
    if missing:
        raise ValueError(
            f"[{path}] Missing required fields: {missing}\n"
            f"Required: {required}"
        )


def _validate_types(profile: dict, path: Path):
    """Spot-check key field types and ranges."""
    errors = []

    if not isinstance(profile.get("profile_id"), str):
        errors.append("profile_id must be a string")

    sm = profile.get("source_method")
    if sm not in ("template", "freeform", "hybrid"):
        errors.append(f"source_method must be template|freeform|hybrid, got: {sm!r}")

    cc = profile.get("character_coverage", {})
    for field in ("lowercase_pct", "uppercase_pct", "digits_pct", "punctuation_pct"):
        v = cc.get(field)
        if v is None or not isinstance(v, (int, float)) or not (0 <= v <= 100):
            errors.append(f"character_coverage.{field} must be 0-100, got: {v!r}")

    if not isinstance(profile.get("usable"), bool):
        errors.append("usable must be a boolean")

    if errors:
        raise ValueError(f"[{path}] Validation errors:\n  " + "\n  ".join(errors))


def _validate_per_character(profile: dict, path: Path):
    """Check per_character entries have valid shapes and existing variant paths."""
    per_char = profile.get("per_character", {})
    if not isinstance(per_char, dict):
        raise ValueError(f"[{path}] per_character must be an object")

    allowed_methods = {"template_cell", "connected_component", "fallback"}
    errors = []

    profile_dir = path.parent if path.name == "profile.json" else path
    for char, entry in per_char.items():
        if not isinstance(entry, dict):
            errors.append(f"  per_character[{char!r}] must be an object")
            continue

        method = entry.get("extraction_method")
        if method not in allowed_methods:
            errors.append(f"  per_character[{char!r}].extraction_method={method!r} not in {allowed_methods}")

        confidence = entry.get("confidence")
        if confidence is None or not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
            errors.append(f"  per_character[{char!r}].confidence must be 0-1, got {confidence!r}")

        variants = entry.get("variants", [])
        if not variants:
            errors.append(f"  per_character[{char!r}].variants is empty")
        for vpath in variants:
            full = (profile_dir / vpath)
            if not full.exists():
                errors.append(f"  per_character[{char!r}] missing file: {vpath}")

    if errors:
        raise ValueError(f"[{path}] per_character errors (first 10):\n" + "\n".join(errors[:10]))


# ── Coverage computation ───────────────────────────────────────────────────────

def compute_coverage(profile: dict) -> dict:
    """
    Re-compute coverage percentages from the per_character data.

    Returns:
        dict with keys: lowercase_pct, uppercase_pct, digits_pct,
                        punctuation_pct, total_characters, total_variants,
                        missing_lowercase, missing_uppercase, missing_digits,
                        missing_punctuation
    """
    chars = set(profile.get("per_character", {}).keys())

    lc_covered = chars & _LOWERCASE
    uc_covered = chars & _UPPERCASE
    dg_covered = chars & _DIGITS
    pu_covered = chars & _PUNCTUATION

    total_variants = sum(
        len(e.get("variants", []))
        for e in profile.get("per_character", {}).values()
    )

    return {
        "lowercase_pct": round(len(lc_covered) / len(_LOWERCASE) * 100, 1),
        "uppercase_pct": round(len(uc_covered) / len(_UPPERCASE) * 100, 1),
        "digits_pct": round(len(dg_covered) / len(_DIGITS) * 100, 1),
        "punctuation_pct": round(len(pu_covered) / len(_PUNCTUATION) * 100, 1),
        "total_characters": len(chars),
        "total_variants": total_variants,
        "missing_lowercase": sorted(_LOWERCASE - lc_covered),
        "missing_uppercase": sorted(_UPPERCASE - uc_covered),
        "missing_digits": sorted(_DIGITS - dg_covered),
        "missing_punctuation": sorted(_PUNCTUATION - pu_covered),
    }


# ── Profile loading ────────────────────────────────────────────────────────────

def load_profile(profile_id: str) -> dict:
    """
    Load a profile by ID from the profiles/ directory.

    Args:
        profile_id: Profile directory name (e.g. "freeform_vishnu").

    Returns:
        Validated profile dict.

    Raises:
        FileNotFoundError: If the profile directory or profile.json doesn't exist.
        ValueError: If the profile fails validation.
    """
    profile_dir = _THIS_DIR / profile_id
    if not profile_dir.exists():
        available = list_profiles()
        raise FileNotFoundError(
            f"Profile '{profile_id}' not found at {profile_dir}\n"
            f"Available profiles: {available}"
        )

    profile_json = profile_dir / "profile.json"
    if not profile_json.exists():
        raise FileNotFoundError(
            f"Profile '{profile_id}' exists but has no profile.json.\n"
            f"Run 'python profiles/migrate.py' to generate it."
        )

    return validate_profile(profile_json)


def load_profile_glyphs_from_schema(profile: dict) -> dict:
    """
    Build a glyph bank dict from a loaded profile.

    Returns:
        {char: [PIL.Image (RGBA), ...]} — the same format HandwritingRenderer expects.

    Each image is loaded from the variant paths listed in per_character.
    """
    from PIL import Image

    profile_dir = _THIS_DIR / profile["profile_id"]
    bank: dict = {}

    for char, entry in profile["per_character"].items():
        images = []
        for rel_path in entry.get("variants", []):
            full_path = profile_dir / rel_path
            try:
                img = Image.open(full_path)
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                images.append(img.copy())
            except Exception as exc:
                print(f"[loader] WARNING: failed to load {full_path}: {exc}")
        if images:
            bank[char] = images

    return bank


# ── Profile discovery ──────────────────────────────────────────────────────────

def list_profiles() -> list[str]:
    """
    Return sorted list of profile IDs that have a profile.json.

    Also reports profiles that exist as directories but lack profile.json.
    """
    ids = []
    for entry in sorted(_THIS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name == "schema":
            continue
        if (entry / "profile.json").exists():
            ids.append(entry.name)
    return ids


def list_all_profile_dirs() -> list[str]:
    """
    Return all profile directories, including those without profile.json.
    """
    dirs = []
    for entry in sorted(_THIS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name == "schema":
            continue
        if (entry / "glyphs").exists() or (entry / "metadata.json").exists():
            dirs.append(entry.name)
    return dirs


# ── CLI helper ─────────────────────────────────────────────────────────────────

def _print_profile_summary(profile: dict):
    cov = compute_coverage(profile)
    sm = profile.get("style_metrics", {})
    print(f"  Profile ID   : {profile['profile_id']}")
    print(f"  Source method: {profile['source_method']}")
    print(f"  Created at   : {profile['created_at']}")
    print(f"  Usable       : {profile['usable']}")
    print(f"  Characters   : {cov['total_characters']}  ({cov['total_variants']} variants)")
    print(f"  Coverage     : lower={cov['lowercase_pct']}%  upper={cov['uppercase_pct']}%  "
          f"digits={cov['digits_pct']}%  punct={cov['punctuation_pct']}%")
    print(f"  Style        : x_height={sm.get('median_x_height', '?'):.1f}px  "
          f"slant={sm.get('slant_estimate_degrees', 0):.1f}°  "
          f"ink_density={sm.get('ink_density', 0):.3f}")
    if profile.get("missing_characters"):
        print(f"  Missing      : {profile['missing_characters']}")
    if profile.get("weak_characters"):
        print(f"  Weak (<0.5)  : {profile['weak_characters']}")


if __name__ == "__main__":
    print("=== InkClone Profile Loader ===\n")

    ids = list_profiles()
    all_dirs = list_all_profile_dirs()

    print(f"Profiles with profile.json : {ids}")
    print(f"All profile directories    : {all_dirs}")
    print()

    for pid in ids:
        try:
            p = load_profile(pid)
            print(f"[{pid}]")
            _print_profile_summary(p)
            print()
        except Exception as exc:
            print(f"[{pid}] ERROR: {exc}")
            print()

    if not ids:
        print("No profiles with profile.json found.")
        print("Run: python profiles/migrate.py")
