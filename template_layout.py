"""
Template v3 layout definition.

Each page is 8 columns × 13 rows = 104 cells, filled left-to-right, top-to-bottom.
Page identity is encoded by the number of "page ID dots" printed on the template.

  Page 1 (1 dot):  lowercase a-z, 4 variants each            → 104 cells
  Page 2 (2 dots): uppercase A-Z (2 each) + digits 0-9 (3 each) → 82 filled, 22 empty
  Page 3 (3 dots): 16 punctuation (2 each) + 20 bigrams (1 each) → 52 filled, 52 empty
"""

COLS = 8
ROWS = 13
CELLS_PER_PAGE = COLS * ROWS  # 104

# ── Punctuation / bigram characters in Page 3 ─────────────────────────────────
_PUNCT_CHARS = [
    '.', ',', '!', '?', "'", '"', '-', ':',
    ';', '(', ')', '/', '@', '&', '#', ',',
]

_BIGRAMS = [
    'th', 'he', 'in', 'an', 'er', 'on', 'ed', 're', 'ou', 'es',
    'ti', 'at', 'st', 'en', 'or', 'ng', 'ing', 'the', 'and', 'tion',
]


def _build_page1():
    """a-z with 4 variants each = 104 cells."""
    seq = []
    for ch in 'abcdefghijklmnopqrstuvwxyz':
        seq.extend([ch] * 4)
    return seq  # 104


def _build_page2():
    """A-Z (2 each) + 0-9 (3 each) = 82 cells; pad to 104 with None."""
    seq = []
    for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        seq.extend([ch] * 2)
    for ch in '0123456789':
        seq.extend([ch] * 3)
    seq += [None] * (CELLS_PER_PAGE - len(seq))
    return seq  # 104


def _build_page3():
    """16 punct (2 each) + 20 bigrams (1 each) = 52 cells; pad to 104 with None."""
    seq = []
    for ch in _PUNCT_CHARS:
        seq.extend([ch] * 2)
    seq.extend(_BIGRAMS)
    seq += [None] * (CELLS_PER_PAGE - len(seq))
    return seq  # 104


# Map: page_id_dots (1-3) → cell sequence list of 104 elements (char or None)
PAGE_LAYOUTS = {
    1: _build_page1(),
    2: _build_page2(),
    3: _build_page3(),
}


def get_cell_char(page_dots: int, cell_index: int):
    """Return the character for a page (by dot count) and 0-based cell index."""
    layout = PAGE_LAYOUTS.get(page_dots)
    if layout is None or cell_index >= len(layout):
        return None
    return layout[cell_index]


def build_manifest():
    """Return a JSON-serialisable manifest: {page: {cell_index: char, ...}}."""
    manifest = {}
    for page_dots, layout in PAGE_LAYOUTS.items():
        page_key = str(page_dots)
        manifest[page_key] = {}
        for idx, char in enumerate(layout):
            if char is not None:
                manifest[page_key][str(idx)] = char
    return manifest


# ── Stem mapping ───────────────────────────────────────────────────────────────
_SPECIAL_STEMS = {
    '.': 'period', ',': 'comma', '!': 'exclaim', '?': 'question',
    "'": 'apostrophe', '"': 'quote', '-': 'hyphen', ':': 'colon',
    ';': 'semicolon', '(': 'lparen', ')': 'rparen', '/': 'slash',
    '@': 'atsign', '&': 'ampersand', '#': 'hash',
}


def char_to_stem(char: str) -> str:
    """Map a character or bigram to its canonical PNG filename stem.

    Examples:
      'a'    → 'a'
      'A'    → 'upper_A'
      '5'    → 'digit_5'
      '.'    → 'period'
      'th'   → 'th'
      'tion' → 'tion'
    """
    if char in _SPECIAL_STEMS:
        return _SPECIAL_STEMS[char]
    if len(char) > 1:
        return char  # bigram/trigram stored as-is
    if char.isupper():
        return f'upper_{char}'
    if char.isdigit():
        return f'digit_{char}'
    return char
