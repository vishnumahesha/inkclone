"""
Shared constants describing the InkClone template v2 layout.

Both template_generator_v2.py and the extraction pipeline reference these
so the cell mapping can never drift out of sync.
"""

CELL_WIDTH_CM  = 1.2
CELL_HEIGHT_CM = 1.5
MARGIN_CM      = 1.5

# One entry per template page (pages 1-3; page 4 is ligatures, not extracted).
# 'characters'    – the ordered list of characters written on that page
# 'cells_per_char'– how many cells the user fills per character
TEMPLATE_PAGES = [
    {
        "characters":     list("abcdefghijklmnopqrstuvwxyz"),
        "cells_per_char": 5,
    },
    {
        "characters":     list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        "cells_per_char": 4,
    },
    {
        "characters":     list("0123456789.,!?'\"-:;()/#&"),
        "cells_per_char": 2,
    },
]
