"""
Realism v2: 15 slider-based render parameters + 5 presets.

Each slider is an integer 0–100. sliders_to_render_params() maps them
to kwargs accepted by HandwritingRenderer.render().
"""

from typing import Dict

SLIDER_NAMES = [
    "font_size", "stroke_thickness", "letter_spacing", "word_spacing", "slant",
    "baseline_straightness", "line_spacing", "margin_consistency",
    "line_end_behavior", "size_variation", "spacing_variation",
    "angle_variation", "pressure_variation", "page_fatigue",
    "ink_fading", "ink_bleed",
]

SLIDER_LABELS = {
    "font_size":            "Font Size",
    "stroke_thickness":     "Stroke Thickness",
    "letter_spacing":       "Letter Spacing",
    "word_spacing":         "Word Spacing",
    "slant":                "Slant",
    "baseline_straightness":"Baseline Straightness",
    "line_spacing":         "Line Spacing",
    "margin_consistency":   "Margin Consistency",
    "line_end_behavior":    "Line End Behavior",
    "size_variation":       "Size Variation",
    "spacing_variation":    "Spacing Variation",
    "angle_variation":      "Angle Variation",
    "pressure_variation":   "Pressure Variation",
    "page_fatigue":         "Page Fatigue",
    "ink_fading":           "Ink Fading",
    "ink_bleed":            "Ink Bleed",
}

PRESETS: Dict[str, Dict[str, int]] = {
    "perfect_student": {
        "font_size": 55, "stroke_thickness": 50, "letter_spacing": 42, "word_spacing": 48,
        "slant": 52, "baseline_straightness": 92, "line_spacing": 50,
        "margin_consistency": 92, "line_end_behavior": 50,
        "size_variation": 8, "spacing_variation": 8, "angle_variation": 8,
        "pressure_variation": 10, "page_fatigue": 5, "ink_fading": 5, "ink_bleed": 8,
    },
    "natural_notes": {
        "font_size": 50, "stroke_thickness": 50, "letter_spacing": 40, "word_spacing": 50,
        "slant": 55, "baseline_straightness": 75, "line_spacing": 50,
        "margin_consistency": 75, "line_end_behavior": 60,
        "size_variation": 25, "spacing_variation": 25, "angle_variation": 20,
        "pressure_variation": 30, "page_fatigue": 15, "ink_fading": 10, "ink_bleed": 25,
    },
    "rushed_homework": {
        "font_size": 42, "stroke_thickness": 50, "letter_spacing": 35, "word_spacing": 58,
        "slant": 45, "baseline_straightness": 42, "line_spacing": 55,
        "margin_consistency": 38, "line_end_behavior": 82,
        "size_variation": 55, "spacing_variation": 55, "angle_variation": 52,
        "pressure_variation": 55, "page_fatigue": 58, "ink_fading": 32, "ink_bleed": 42,
    },
    "messy_scrawl": {
        "font_size": 48, "stroke_thickness": 50, "letter_spacing": 25, "word_spacing": 65,
        "slant": 38, "baseline_straightness": 18, "line_spacing": 62,
        "margin_consistency": 18, "line_end_behavior": 95,
        "size_variation": 82, "spacing_variation": 82, "angle_variation": 78,
        "pressure_variation": 78, "page_fatigue": 82, "ink_fading": 62, "ink_bleed": 68,
    },
}
PRESETS["custom"] = dict(PRESETS["natural_notes"])


def _lerp(t: float, lo: float, hi: float) -> float:
    return lo + (hi - lo) * (t / 100.0)


def sliders_to_render_params(sliders: Dict[str, int], line_spacing_px: int) -> dict:
    """
    Map 0–100 sliders to HandwritingRenderer.render() kwargs.

    line_spacing_px is the ruled-line spacing for the chosen paper type
    (e.g. 42 for college_ruled). Font size and word spacing are expressed
    as fractions of this spacing so the text fits within the lines.
    """
    s   = {k: max(0, min(100, int(v))) for k, v in sliders.items()}
    lsp = max(1, line_spacing_px)

    return {
        # Character metrics
        "char_height":        int(_lerp(s["font_size"],               lsp * 0.30, lsp * 0.80)),
        "stroke_thickness":   int(_lerp(s.get("stroke_thickness", 50), -1, 3)),
        "inter_letter_mean":  _lerp(s["letter_spacing"],              -2.0,   6.0),
        "inter_word_mean":    _lerp(s["word_spacing"],                lsp * 0.25, lsp * 1.2),
        "slant_deg":          _lerp(s["slant"],                       -12.0, 12.0),
        # Line layout
        "baseline_wander_px": _lerp(100 - s["baseline_straightness"],  0.0,  10.0),
        "line_spacing_mult":  _lerp(s["line_spacing"],                 0.85,  2.0),
        "margin_drift_px":    _lerp(100 - s["margin_consistency"],     0.0,  18.0),
        "line_end_cramming":  _lerp(s["line_end_behavior"],            0.4,   1.0),
        # Per-glyph variation
        "size_jitter":        _lerp(s["size_variation"],               0.0,   0.35),
        "spacing_jitter":     _lerp(s["spacing_variation"],            0.0,   0.6),
        "angle_jitter_deg":   _lerp(s["angle_variation"],              0.0,   8.0),
        "pressure_range":     _lerp(s["pressure_variation"],           0.0,   0.45),
        # Page-level effects
        "fatigue_factor":     _lerp(s["page_fatigue"],                 0.0,   0.6),
        "ink_fade":           _lerp(s["ink_fading"],                   0.0,   0.35),
        "bleed_radius":       _lerp(s["ink_bleed"],                    0.0,   3.0),
    }


def get_preset(name: str) -> Dict[str, int]:
    """Return a copy of a named preset, defaulting to natural_notes."""
    return dict(PRESETS.get(name, PRESETS["natural_notes"]))
