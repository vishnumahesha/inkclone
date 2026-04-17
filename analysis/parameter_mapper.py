"""
Maps style_analyzer scores (0–100 each) to InkClone engine parameters.

Two output namespaces:
  render_params  → kwargs for HandwritingRenderer.render()
  realism_params → kwargs for realism.apply_realism() (custom preset dict)

All input score keys must match analyze_style() output.
"""

from __future__ import annotations


def map_to_render_params(scores: dict) -> dict:
    """
    Map style scores to render_engine.py HandwritingRenderer.render() kwargs.

    Returned keys correspond to render() parameters with matching names.
    """
    s = scores

    # Inter-letter gap: tight (100) → narrow (1 px), loose (0) → wide (8 px)
    inter_letter_mean = 8.0 - s["letter_spacing_tightness"] * 0.07
    inter_letter_mean = max(0.5, inter_letter_mean)

    # Letter spacing std: driven by size inconsistency
    inter_letter_std = 1.0 + (1.0 - s["size_consistency"] / 100.0) * 3.0

    # Inter-word gap: proportional to word_spacing score
    inter_word_mean = 10.0 + s["word_spacing"] * 0.32
    inter_word_std  = 3.0 + (100.0 - s["size_consistency"]) / 100.0 * 8.0

    # Baseline amplitude: straight (100) → 0.5, wavy (0) → 5.5
    baseline_amplitude = 5.5 - s["baseline_straightness"] * 0.05
    baseline_amplitude = max(0.2, baseline_amplitude)

    # Rotation max: slant inconsistency drives per-letter rotation jitter
    rotation_max_deg = 0.5 + (100.0 - s["slant_consistency"]) / 100.0 * 4.0

    # Scale variance: size consistent (100) → 0.01, very inconsistent (0) → 0.15
    scale_variance = 0.01 + (100.0 - s["size_consistency"]) / 100.0 * 0.14
    scale_variance = max(0.005, scale_variance)

    # Neatness: direct 0–1 mapping
    neatness = s["neatness"] / 100.0

    return {
        "inter_letter_mean": round(inter_letter_mean, 2),
        "inter_letter_std":  round(inter_letter_std,  2),
        "inter_word_mean":   round(inter_word_mean,   2),
        "inter_word_std":    round(inter_word_std,    2),
        "baseline_amplitude": round(baseline_amplitude, 2),
        "rotation_max_deg":  round(rotation_max_deg,  2),
        "scale_variance":    round(scale_variance,     4),
        "neatness":          round(neatness,            3),
    }


def map_to_realism_params(scores: dict) -> dict:
    """
    Map style scores to realism.py effect amounts (0–1 each).

    The returned dict can be used directly as a custom preset:
        from realism import apply_realism
        apply_realism(img, preset=params)   # preset accepts a dict too
    Or the individual keys can be passed to each effect function.
    """
    s = scores

    # Baseline wander: wavy text (low baseline_straightness) → high wander
    baseline_wander = (100.0 - s["baseline_straightness"]) / 100.0 * 0.75

    # Margin drift: inconsistent margin → high drift
    margin_drift = (100.0 - s["margin_consistency"]) / 100.0 * 0.60

    # Pressure variation: direct mapping
    pressure_variation = s["pressure_variation"] / 100.0 * 0.80

    # Page fatigue: composite of baseline instability + margin inconsistency
    page_fatigue = (
        (100.0 - s["baseline_straightness"]) / 200.0
        + (100.0 - s["margin_consistency"])   / 200.0
    ) * 0.80

    # Pen fading: driven by pressure variation
    pen_fading = s["pressure_variation"] / 100.0 * 0.50

    # Line-end cramming: less neat writers tend to scrunch at line ends
    line_end_cramming = (100.0 - s["neatness"]) / 100.0 * 0.60

    return {
        "page_fatigue":       round(page_fatigue,       3),
        "baseline_wander":    round(baseline_wander,    3),
        "margin_drift":       round(margin_drift,        3),
        "pressure_variation": round(pressure_variation, 3),
        "pen_fading":         round(pen_fading,          3),
        "line_end_cramming":  round(line_end_cramming,  3),
    }


def map_all(scores: dict) -> dict:
    """Return both render_params and realism_params from style scores."""
    return {
        "render_params":  map_to_render_params(scores),
        "realism_params": map_to_realism_params(scores),
    }
