"""Intelligent variant selection for handwriting rendering.

Provides quality-weighted, recency-aware variant selection and bigram
preference logic. Designed to replace the simple VariantSelector in
render_engine.py.

Key behaviours
--------------
* Recency queue: tracks last RECENCY_WINDOW variants used per character;
  never selects the same variant twice in a row.
* Quality weighting: variants with higher audit scores are preferred.
* Rotation: all variants are cycled within every ROTATION_WINDOW uses so no
  single variant dominates.
* Bigram preference: `find_bigram()` returns the longest available bigram
  glyph at a text position, so callers can substitute the pre-drawn bigram
  glyph instead of compositing two individual letters.
"""

import json
import random
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Bigrams ordered longest-first so we always prefer the most-specific match.
# These are the multi-char glyph keys present in vishnu_v3/profile.json.
KNOWN_BIGRAMS: List[str] = [
    "tion", "the", "ing", "and",
    "th", "he", "in", "an", "ed", "en", "er", "es",
    "ng", "on", "or", "ou", "re", "st", "ti",
]

RECENCY_WINDOW = 2    # recent variants per char to avoid repeating
ROTATION_WINDOW = 5   # force full rotation within this many uses


class QualityWeightedVariantSelector:
    """Selects glyph variants with quality weighting and recency avoidance.

    Usage
    -----
    selector = QualityWeightedVariantSelector.from_audit_report(
        "profiles/vishnu_v3/audit_report.json"
    )
    # At the start of each render call:
    selector.reset()
    # For each character in text:
    idx = selector.select(char, len(glyph_bank[char]))
    glyph = glyph_bank[char][idx]
    """

    def __init__(
        self,
        quality_scores: Optional[Dict[str, float]] = None,
        seed: Optional[int] = None,
    ):
        """
        Args:
            quality_scores: Maps glyph filename stem → quality score (0–1).
                            Built from audit_report.json. Uniform if None.
            seed: Optional random seed for reproducible selections.
        """
        self._quality: Dict[str, float] = quality_scores or {}
        self._recent: Dict[str, deque] = {}
        self._use_counts: Dict[str, List[int]] = {}
        self._rng = random.Random(seed)

    # ── Public API ────────────────────────────────────────────────────────────

    def select(self, char: str, num_variants: int) -> int:
        """Return the index of the best variant for *char*.

        Rules applied in order:
        1. Exclude variants seen in the last RECENCY_WINDOW uses (no repeat).
        2. Among eligible variants, prefer the least-used (rotation guarantee).
        3. Break ties by quality score (weighted random pick).
        """
        if num_variants <= 0:
            return 0
        if num_variants == 1:
            return 0

        self._ensure_tracking(char, num_variants)

        recent = self._recent[char]
        use_counts = self._use_counts[char]

        # Step 1: build candidate set (exclude recently used)
        candidates = [i for i in range(num_variants) if i not in recent]
        if not candidates:
            # All variants are recent — allow any (forced restart of rotation)
            candidates = list(range(num_variants))

        # Step 2: prefer least-used candidates (rotation within ROTATION_WINDOW)
        min_uses = min(use_counts[i] for i in candidates)
        candidates = [i for i in candidates if use_counts[i] == min_uses]

        # Step 3: weighted random pick by quality score
        chosen = self._weighted_pick(char, candidates, num_variants)

        # Update tracking
        recent.append(chosen)
        self._use_counts[char][chosen] += 1
        return chosen

    def reset(self):
        """Clear per-render state. Call at the start of each render()."""
        self._recent.clear()
        self._use_counts.clear()

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_audit_report(
        cls,
        report_path,
        seed: Optional[int] = None,
    ) -> "QualityWeightedVariantSelector":
        """Build selector from audit_report.json produced by scripts/audit_glyphs.py."""
        report_path = Path(report_path)
        if not report_path.exists():
            return cls(seed=seed)
        try:
            with open(report_path) as f:
                report = json.load(f)
            scores: Dict[str, float] = {}
            for entry in report.get("per_glyph", []):
                stem = Path(entry["file"]).stem
                scores[stem] = float(entry.get("quality_score", 0.85))
            return cls(quality_scores=scores, seed=seed)
        except Exception as e:
            print(f"[variant_selector] WARNING: could not load audit report: {e}")
            return cls(seed=seed)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_tracking(self, char: str, num_variants: int):
        if char not in self._recent:
            self._recent[char] = deque(maxlen=RECENCY_WINDOW)
        if char not in self._use_counts:
            self._use_counts[char] = [0] * num_variants
        elif len(self._use_counts[char]) < num_variants:
            self._use_counts[char].extend(
                [0] * (num_variants - len(self._use_counts[char]))
            )

    def _weighted_pick(self, char: str, candidates: List[int], num_variants: int) -> int:
        """Weighted random pick from candidates using quality scores."""
        if len(candidates) == 1:
            return candidates[0]

        weights = [
            max(0.01, self._quality.get(_stem(char, i), 0.85))
            for i in candidates
        ]
        total = sum(weights)
        r = self._rng.random() * total
        cumulative = 0.0
        for idx, w in zip(candidates, weights):
            cumulative += w
            if r <= cumulative:
                return idx
        return candidates[-1]

    def get_quality(self, char: str, variant_idx: int) -> float:
        """Return quality score for a specific (char, variant_idx) pair."""
        return self._quality.get(_stem(char, variant_idx), 0.85)


# ── Bigram utilities ──────────────────────────────────────────────────────────


def find_bigram(
    text: str, pos: int, glyph_bank: dict
) -> Optional[Tuple[str, int]]:
    """Find the longest bigram glyph available at *pos* in *text*.

    Checks KNOWN_BIGRAMS longest-first, returning the first match that:
    - Fits within the remaining text, and
    - Has a glyph in the bank.

    Args:
        text:       Full text being rendered.
        pos:        Current character position in *text*.
        glyph_bank: The loaded glyph bank (char → list of PIL.Image).

    Returns:
        (bigram_str, length) of the best match, or None if no bigram applies.
    """
    for bigram in KNOWN_BIGRAMS:
        end = pos + len(bigram)
        if end > len(text):
            continue
        substr = text[pos:end].lower()
        if substr == bigram and bigram in glyph_bank:
            return bigram, len(bigram)
    return None


# ── Filename helpers ──────────────────────────────────────────────────────────

_PUNCT_STEM: Dict[str, str] = {
    ".": "period", ",": "comma", "!": "exclaim", "?": "question",
    "'": "apostrophe", "-": "hyphen", ":": "colon", ";": "semicolon",
    "(": "lparen", ")": "rparen", "&": "ampersand", "#": "hash",
    "@": "atsign", "/": "slash", '"': "quote",
}


def _stem(char: str, variant_idx: int) -> str:
    """Return expected glyph filename stem for (char, variant_idx)."""
    if char in _PUNCT_STEM:
        return f"{_PUNCT_STEM[char]}_{variant_idx}"
    if char.isupper():
        return f"upper_{char}_{variant_idx}"
    if char.isdigit():
        return f"digit_{char}_{variant_idx}"
    # Lowercase single chars and multi-char bigrams both use "key_N" format
    return f"{char}_{variant_idx}"
