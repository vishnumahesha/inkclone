"""Basic kerning table for handwriting rendering.

Provides per-pair spacing adjustments that render_engine can apply when
advancing the cursor after each glyph.  Call get_kern_adjustment() to get
a float multiplier on the current letter_spacing value.

Pair conventions
----------------
All pairs are matched case-insensitively on the *lower-case* form of both
characters, so "Ta" and "tA" and "TA" all hit the same entry.

Multiplier semantics
--------------------
  < 1.0  →  tighter than baseline (tight pair)
  > 1.0  →  looser than baseline  (loose pair)
  = 1.0  →  no adjustment (default when pair is not in either table)

The multiplier applies to the *letter_spacing* component only, not to the
glyph width itself.  The caller (render_engine) is responsible for applying
it:

    adj = get_kern_adjustment(prev_char, current_char)
    cursor_x += glyph_width + letter_spacing * adj

Integration note
----------------
render_engine.py should NOT be modified until the file
~/Projects/inkclone/.render_fix_done is present (Task 2C spec).
Once that sentinel exists, wire kerning into the render loop by importing
get_kern_adjustment from this module.
"""

from typing import Dict

# ---------------------------------------------------------------------------
# Tight pairs — reduce letter_spacing by 30 %  (multiplier = 0.70)
# ---------------------------------------------------------------------------
# These pairs have glyphs that optically overlap or whose shapes naturally
# nest into each other.  Classic examples: diagonal strokes meeting a round.
_TIGHT_FACTOR = 0.70

_TIGHT_PAIRS: Dict[str, float] = {
    p: _TIGHT_FACTOR for p in [
        "av", "ay", "aw",
        "fa", "fo",
        "ly", "oy",
        "to",
        "va", "vo",
        "wa", "we", "wo",
        "ya", "yo",
    ]
}

# ---------------------------------------------------------------------------
# Loose pairs — increase letter_spacing by 15 %  (multiplier = 1.15)
# ---------------------------------------------------------------------------
# Pairs where both glyphs have vertical strokes close together, creating an
# artificially cramped look without extra breathing room.
_LOOSE_FACTOR = 1.15

_LOOSE_PAIRS: Dict[str, float] = {
    p: _LOOSE_FACTOR for p in [
        "ri",
        "fl", "fi",
        "ll",
    ]
}

# Merged lookup for O(1) access — tight entries take precedence over loose
# (they can't overlap since the sets are disjoint, but explicit ordering
# makes future edits safe).
_KERN_TABLE: Dict[str, float] = {**_LOOSE_PAIRS, **_TIGHT_PAIRS}


def get_kern_adjustment(char_a: str, char_b: str) -> float:
    """Return the kerning multiplier for the pair (char_a, char_b).

    Args:
        char_a: The character just rendered (left side of pair).
        char_b: The character about to be rendered (right side of pair).

    Returns:
        A float multiplier on letter_spacing:
          0.70  tight pair  (30 % tighter)
          1.15  loose pair  (15 % looser)
          1.00  no adjustment (default)
    """
    pair = (char_a.lower() + char_b.lower()) if (char_a and char_b) else ""
    return _KERN_TABLE.get(pair, 1.0)


def list_kern_pairs() -> Dict[str, float]:
    """Return a copy of the full kerning table (pair → multiplier)."""
    return dict(_KERN_TABLE)
