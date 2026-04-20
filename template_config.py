"""
template_config.py — Single source of truth for InkClone V6 template geometry.

All extraction pipeline constants live here. Never hardcode these values elsewhere.
"""

# ── Warp target (letter paper @ 300 DPI) ──────────────────────────────────────
WARP_W = 2550
WARP_H = 3300

# ── Page margins (pixels in warped space) ─────────────────────────────────────
MARGIN_LEFT   = 150
MARGIN_RIGHT  = 150
MARGIN_TOP    = 285
MARGIN_BOTTOM = 135

# ── Grid layout per page: {page: (cols, rows)} ────────────────────────────────
PAGE_GRIDS = {1: (6, 10), 2: (6, 10), 3: (6, 10), 4: (8, 11)}

# ── Extraction parameters ──────────────────────────────────────────────────────
CELL_INSET           = 0.08   # fraction trimmed from each edge before thresholding
RED_CHANNEL_THRESHOLD = 155   # R < threshold → ink; blue lines (R≈170) are rejected
MORPH_KERNEL_SIZE    = 2      # morphological close kernel (pixels)
AUTOCROP_PADDING     = 4      # padding added around ink bbox after autocrop
MIN_INK_PIXELS       = 15     # minimum ink pixels to keep a glyph

# ── Synthetic template drawing ─────────────────────────────────────────────────
BLUE_LINE_COLOR = (170, 210, 255)   # RGB; R=170 > RED_CHANNEL_THRESHOLD → rejected
BASELINE_RATIO  = 0.70              # baseline y = cell_top + BASELINE_RATIO * cell_h

# ── Derived geometry ───────────────────────────────────────────────────────────
_USABLE_W = WARP_W - MARGIN_LEFT - MARGIN_RIGHT   # 2250 px
_USABLE_H = WARP_H - MARGIN_TOP  - MARGIN_BOTTOM  # 2880 px


def cell_dims(page: int):
    """Return (cell_w, cell_h) in warped-space pixels for the given page."""
    cols, rows = PAGE_GRIDS[page]
    return _USABLE_W / cols, _USABLE_H / rows


# ── Punctuation name → display character ──────────────────────────────────────
_PUNCT_DISPLAY = {
    'period':    '.',
    'comma':     ',',
    'exclaim':   '!',
    'question':  '?',
    'apostrophe': "'",
    'quote':     '"',
    'hyphen':    '-',
    'colon':     ':',
    'semicolon': ';',
    'lparen':    '(',
    'rparen':    ')',
    'slash':     '/',
    'atsign':    '@',
    'ampersand': '&',
    'hash':      '#',
    'dollar':    '$',
}

# Reverse map: display char → stem name
CHAR_TO_STEM = {v: k for k, v in _PUNCT_DISPLAY.items()}


def label_to_display(label: str | None) -> str:
    """Convert an internal label (stem) to the human-readable character."""
    if not label:
        return ''
    if label.startswith('upper_'):
        return label[6:]       # 'upper_A' → 'A'
    if label.startswith('digit_'):
        return label[6:]       # 'digit_0' → '0'
    if label in _PUNCT_DISPLAY:
        return _PUNCT_DISPLAY[label]
    return label               # lowercase letter or bigram


# ── Page cell maps ─────────────────────────────────────────────────────────────
# Each returns a list of dicts: {label, variant}  (None label = empty cell)
# Length must equal cols × rows for that page.

def build_page1_map():
    """Lowercase a–o × 4 variants = 60 cells (6×10 grid)."""
    cells = []
    for ch in 'abcdefghijklmno':           # 15 chars
        for v in range(4):
            cells.append({'label': ch, 'variant': v})
    assert len(cells) == 60
    return cells


def build_page2_map():
    """Lowercase p–z × 4 = 44 content + 16 empty = 60 cells (6×10 grid)."""
    cells = []
    for ch in 'pqrstuvwxyz':               # 11 chars
        for v in range(4):
            cells.append({'label': ch, 'variant': v})
    while len(cells) < 60:
        cells.append({'label': None, 'variant': 0})
    assert len(cells) == 60
    return cells


def build_page3_map():
    """Uppercase A–Z × 2 = 52 content + 8 empty = 60 cells (6×10 grid)."""
    cells = []
    for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':  # 26 chars
        for v in range(2):
            cells.append({'label': f'upper_{ch}', 'variant': v})
    while len(cells) < 60:
        cells.append({'label': None, 'variant': 0})
    assert len(cells) == 60
    return cells


def build_page4_map():
    """Digits×3 + 16 punct×2 + 20 bigrams×1 = 82 content + 6 empty = 88 cells (8×11)."""
    cells = []
    # Digits 0–9 × 3
    for d in '0123456789':
        for v in range(3):
            cells.append({'label': f'digit_{d}', 'variant': v})
    # 16 punctuation marks × 2
    punct_names = [
        'period', 'comma', 'exclaim', 'question',
        'apostrophe', 'quote', 'hyphen', 'colon',
        'semicolon', 'lparen', 'rparen', 'slash',
        'atsign', 'ampersand', 'hash', 'dollar',
    ]
    for name in punct_names:
        for v in range(2):
            cells.append({'label': name, 'variant': v})
    # 20 bigrams × 1
    bigrams = [
        'th', 'he', 'in', 'an', 'er', 'ou', 'ed', 're', 'on', 'es',
        'ti', 'at', 'st', 'en', 'or', 'ng', 'ing', 'the', 'and', 'tion',
    ]
    for bg in bigrams:
        cells.append({'label': bg, 'variant': 0})
    # Pad to 88 (8×11)
    while len(cells) < 88:
        cells.append({'label': None, 'variant': 0})
    assert len(cells) == 88
    return cells


# Maps page number → builder function
PAGE_MAPS = {
    1: build_page1_map,
    2: build_page2_map,
    3: build_page3_map,
    4: build_page4_map,
}

# Total non-empty cells across all pages (the validation target)
TOTAL_CONTENT_CELLS = 60 + 44 + 52 + 82   # = 238
