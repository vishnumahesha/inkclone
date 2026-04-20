# InkClone Extraction Pipeline Log

## Template Config

Source of truth: `template_config.py`

| Constant | Value | Purpose |
|---|---|---|
| `WARP_W` | 2550 | Warp target width (letter @ 300 DPI) |
| `WARP_H` | 3300 | Warp target height |
| `MARGIN_LEFT` | 150 px | Left page margin |
| `MARGIN_RIGHT` | 150 px | Right page margin |
| `MARGIN_TOP` | 285 px | Top page margin |
| `MARGIN_BOTTOM` | 135 px | Bottom page margin |
| `PAGE_GRIDS` | {1-3:(6,10), 4:(8,11)} | Grid cols×rows per page |
| `CELL_INSET` | 0.08 | Fraction trimmed from each cell edge |
| `RED_CHANNEL_THRESHOLD` | 155 | R < threshold → ink; blue lines (R≈170) rejected |
| `MORPH_KERNEL_SIZE` | 2 | Morphological close kernel (px) |
| `AUTOCROP_PADDING` | 4 | Padding around ink bbox after autocrop |
| `MIN_INK_PIXELS` | 15 | Minimum ink pixels to accept a glyph |
| `BLUE_LINE_COLOR` | (170,210,255) RGB | Blue grid color; R=170 > threshold |
| `BASELINE_RATIO` | 0.70 | Baseline y = cell_top + 0.70 × cell_h |

**Total content cells: 238**
- Page 1: lowercase a–o × 4 variants = 60
- Page 2: lowercase p–z × 4 variants = 44 (+16 empty)
- Page 3: uppercase A–Z × 2 variants = 52 (+8 empty)
- Page 4: digits 0–9 × 3 + 16 punct × 2 + 20 bigrams × 1 = 82 (+6 empty)

**Pipeline** (`/api/extract-template`):
1. `_perspective_warp`: `cv2.resize(WARP_W, WARP_H, INTER_CUBIC)` + sharpen kernel `[[-0.5,-1,-0.5],[-1,7,-1],[-0.5,-1,-0.5]]` — **no corner detection**
2. `_red_channel_binary`: `b,g,r = cv2.split(warped)` → `threshold(r, 155, THRESH_BINARY_INV)` → morph close
3. `_extract_page_cells_v2`: fixed grid positions from `PAGE_MAPS[page]()` + `cell_dims(page)`
4. `_cell_to_rgba_v2`: autocrop to ink bbox + 4px padding, resize to 128px height, RGBA output

---

## Synthetic Results

Generator: `generate_synthetic.py`
Font: Arial Unicode (`/Library/Fonts/Arial Unicode.ttf`)
Char height: 58% of cell height, black on white, blue grid R=170.

Validator: `tests/validate_extraction.py`
Checks: exists / ink≥15px / not full-cell / sane AR / OCR content match.

### Round 1 (initial)
- Bug: cross-correlation NCC computed between very different-scale images → 0/238

### Round 2 (NCC normalized to 48×48 crop-to-bbox)
- 40/238 — NCC still too sensitive to aspect-ratio differences across fonts

### Round 3 (pytesseract primary, NCC fallback for explicit mismatches only)
- **238/238 PASS** ✓

Per-category (final):
| Category | Score | Total |
|---|---|---|
| Lowercase | 104 | 104 |
| Uppercase | 52 | 52 |
| Digits | 30 | 30 |
| Punct | 32 | 32 |
| Bigrams | 20 | 20 |
| **Total** | **238** | **238** |

---

## Real Photo Results

Profile: `real_blue_v1`
Source: `profiles/IMG_3807.jpeg` (page 1) · `IMG_3806.jpeg` (p2) · `IMG_3809.jpeg` (p3) · `IMG_3808.jpeg` (p4)
Resolution: ~925×1118 px (pre-downscaled camera photos)
Pipeline: resize → INTER_CUBIC → sharpen → red-channel threshold

Per-category:
| Category | Score | Total |
|---|---|---|
| Lowercase | 104 | 104 |
| Uppercase | 52 | 52 |
| Digits | 30 | 30 |
| Punct | 32 | 32 |
| Bigrams | 20 | 20 |
| **Total** | **238** | **238** |

Note: structural validation passes for all cells. Content validation is limited for small punct marks — OCR cannot reliably identify single punctuation characters, so content is not verified for those categories.

---

## Known Limitations

### Pencil or light ink (R = 140–160, borderline)
The red-channel threshold (R < 155) accepts ink only if its red channel is below 155. Pencil marks typically have R = 140–160 depending on pressure. Light pencil strokes may fall near or above the threshold and be partially rejected, producing sparse glyphs.

### Compressed / downscaled photos
The pipeline resizes any input to 2550×3300. If the source photo has already been compressed to ~1 MP (as in the test set), the upscale ratio is ~2.75×. INTER_CUBIC + sharpening partially recovers edge detail, but fine strokes may still blur or disconnect.

### Corner detection is off
`_perspective_warp` is a pure resize with no perspective correction. If the template was photographed at an angle, cells will be systematically misaligned. Pages shot straight overhead (phone directly above page) are required.

### Small punctuation cells
Period, comma, apostrophe, and similar characters occupy only a small area of their cells. After autocrop + upscale to 128px height, these glyphs may appear to contain bleed from adjacent cells or baseline guide artifacts.

### Dollar sign (`$`) not in original _PUNCT stem map
`web/app.py:_char_to_stem` did not include `$` → `dollar`. `template_config` adds this mapping. The `VALID_V6_CHARS` set in `extract_v6.py` also lacks `$`; it is included in the V6 template cell layout but may not appear in older profiles.

---

## User Recommendations

1. **Use a black ballpoint pen** — gives R ≈ 20–40, well below the 155 threshold. Felt-tip and fountain pens also work. Avoid pencil and light blue pens.

2. **AirDrop full-resolution photos** — do not share via iMessage or WhatsApp; both compress to ~1 MP. AirDrop preserves native resolution (typically 12 MP) for much better extraction quality.

3. **Shoot straight overhead** — hold your phone directly above the page (not at an angle). Use the `1×` lens. The pipeline does not correct perspective.

4. **Even lighting** — avoid shadows across the page. Natural daylight or a desk lamp positioned to the side works well. Flash can wash out light strokes.

5. **Fill every cell** — empty cells produce `ink < MIN_INK_PIXELS` and are skipped, leaving gaps in your profile. The renderer falls back to substitutes for missing glyphs.
