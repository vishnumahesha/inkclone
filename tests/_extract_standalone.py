import cv2
import numpy as np
from PIL import Image
from pathlib import Path
import os, sys

_WARP_W, _WARP_H = 2550, 3300

# Template margin ratios (8.5"×11" letter paper)
_ML_RATIO = 0.5 / 8.5    # left margin
_MT_RATIO = 0.95 / 11.0  # top margin
_MR_RATIO = 0.5 / 8.5    # right margin
_MB_RATIO = 0.45 / 11.0  # bottom margin

_SMALL_CHARS = {'.', ',', "'", '"', '-', ':', ';', '!'}


def _page_cells(pg: int) -> list[str]:
    """Character sequence for each template page (matches extract_v6.py)."""
    if pg == 1:
        return [c for c in 'abcdefghijklmno' for _ in range(4)]
    if pg == 2:
        return [c for c in 'pqrstuvwxyz' for _ in range(4)]
    if pg == 3:
        return [c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' for _ in range(2)]
    # Page 4: digits + punctuation + bigrams
    cells = [d for d in '0123456789' for _ in range(3)]
    punct = ['.', ',', '!', '?', "'", '"', '-', ':', ';',
             '(', ')', '/', '@', '&', '#', '$']
    cells += [p for p in punct for _ in range(2)]
    cells += ['th', 'he', 'in', 'an', 'er', 'on', 'ed', 're', 'ou', 'es',
              'ti', 'at', 'st', 'en', 'or', 'ng', 'ing', 'the', 'and', 'tion']
    return cells


def _page_grid(pg: int) -> tuple:
    """Return (cols, rows, margin_left, margin_top, cell_w, cell_h) at 2550×3300."""
    ml = int(_WARP_W * _ML_RATIO)
    mt = int(_WARP_H * _MT_RATIO)
    gw = _WARP_W - ml - int(_WARP_W * _MR_RATIO)
    gh = _WARP_H - mt - int(_WARP_H * _MB_RATIO)
    cols, rows = (6, 10) if pg <= 3 else (8, 11)
    return cols, rows, ml, mt, gw / cols, gh / rows


def _find_corners(gray):
    """
    Find 4 corners of the template content area.

    Primary: Hough line detection on the printed cell grid.  The template's
    outermost horizontal and vertical grid lines form a rectangle whose corners
    we use directly.  This is more robust than blob-based corner marker
    detection because the grid lines are long and clearly detectable even when
    the small corner marker squares are faint or cropped.

    Fallback: largest dark blob per image quadrant (original extract_v6 logic).
    """
    import cv2
    import numpy as np

    h, w = gray.shape

    # ── Primary: Hough grid border ─────────────────────────────────────────
    edges = cv2.Canny(gray, 30, 80)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=max(50, int(w * 0.15)),
                            maxLineGap=60)
    h_ys: list[int] = []
    v_xs: list[int] = []
    if lines is not None:
        for seg in lines:
            x1, y1, x2, y2 = seg[0]
            angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            if angle < 10 or angle > 170:          # near-horizontal
                y = min(y1, y2)
                if 0 < y < h - 1:
                    h_ys.append(y)
            elif 80 < angle < 100:                 # near-vertical
                x = min(x1, x2)
                if 0 < x < w - 1:
                    v_xs.append(x)

    if h_ys and v_xs and len(h_ys) >= 2 and len(v_xs) >= 2:
        top_y  = float(min(h_ys))
        bot_y  = float(max(h_ys))
        left_x = float(min(v_xs))
        rgt_x  = float(max(v_xs))
        # Sanity: border must cover ≥50 % of image in each dimension
        if (rgt_x - left_x) >= w * 0.50 and (bot_y - top_y) >= h * 0.50:
            # Hough found cell-grid bounds, not full-page corners.
            # Extrapolate to full-page corners using known margin ratios.
            # Template: ml=150, mr=150, mt=285, mb=135 in 2550×3300 warp.
            # Cell grid = warp content area [150:2400] × [285:3165].
            grid_w = rgt_x - left_x
            grid_h = bot_y  - top_y
            px_x = grid_w / 2250.0   # image pixels per warp unit (x)
            px_y = grid_h / 2880.0   # image pixels per warp unit (y)
            tl_x = left_x - 150 * px_x
            tl_y = top_y  - 285 * px_y
            tr_x = rgt_x  + 150 * px_x
            br_y = bot_y  + 135 * px_y
            return {
                'TL': (tl_x, tl_y), 'TR': (tr_x, tl_y),
                'BL': (tl_x, br_y), 'BR': (tr_x, br_y),
            }

    # ── Fallback: largest dark blob per quadrant ───────────────────────────
    _, binarized = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
    n_comp, _, stats, centroids = cv2.connectedComponentsWithStats(binarized, 8)
    blobs = []
    for i in range(1, n_comp):
        area = stats[i, cv2.CC_STAT_AREA]
        bw   = stats[i, cv2.CC_STAT_WIDTH]
        bh   = stats[i, cv2.CC_STAT_HEIGHT]
        if area > 50 and bh > 0 and 0.3 < bw / bh < 3.0:
            blobs.append((area, float(centroids[i, 0]), float(centroids[i, 1])))
    mid_x, mid_y = w / 2, h / 2
    quadrants = {
        'TL': [b for b in blobs if b[1] < mid_x and b[2] < mid_y],
        'TR': [b for b in blobs if b[1] >= mid_x and b[2] < mid_y],
        'BL': [b for b in blobs if b[1] < mid_x and b[2] >= mid_y],
        'BR': [b for b in blobs if b[1] >= mid_x and b[2] >= mid_y],
    }
    fallback = {
        'TL': (w * .02, h * .02), 'TR': (w * .98, h * .02),
        'BL': (w * .02, h * .98), 'BR': (w * .98, h * .98),
    }
    corners = {}
    for q, qblobs in quadrants.items():
        if qblobs:
            best = max(qblobs, key=lambda x: x[0])
            corners[q] = (best[1], best[2])
        else:
            corners[q] = fallback[q]
    return corners


def _perspective_warp(img, corners):
    """Warp image to 2550×3300 using detected corners (from extract_v6)."""
    import cv2
    import numpy as np

    src = np.array([corners['TL'], corners['TR'],
                    corners['BR'], corners['BL']], np.float32)
    dst = np.array([[0, 0], [_WARP_W, 0],
                    [_WARP_W, _WARP_H], [0, _WARP_H]], np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    is_upscale = _WARP_W > img.shape[1]
    interp = cv2.INTER_CUBIC if is_upscale else cv2.INTER_AREA
    return cv2.warpPerspective(img, matrix, (_WARP_W, _WARP_H), flags=interp)


def _extract_glyph_cell(warped_bgr, col, row, ml, mt, cw, ch, char_name=''):
    """Extract one cell using RED CHANNEL — blue guide lines are invisible.
    Matches extract_v6.extract_glyph exactly."""
    import cv2
    import numpy as np
    from PIL import Image

    scale = _WARP_W / 2550.0
    inward_x = max(3, int(cw * 0.08))
    inward_y = max(3, int(ch * 0.08))
    pad = max(2, int(4 * scale))

    x0 = int(round(ml + col * cw)) + inward_x
    y0 = int(round(mt + row * ch)) + inward_y
    x1 = min(_WARP_W, int(round(ml + (col + 1) * cw)) - inward_x)
    y1 = min(_WARP_H, int(round(mt + (row + 1) * ch)) - inward_y)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None

    cell = warped_bgr[y0:y1, x0:x1].copy()
    cell_h = cell.shape[0]

    # White out label zone (top 15% of cell)
    label_mask_h = int(cell_h * 0.15)
    cell[:label_mask_h, :] = [255, 255, 255]

    # Min-channel binarization: ink min(R,G,B)≈7-87; gray/blue lines min≈130+
    # Works for both blue template lines (R=170) and gray photographed lines (R≈G≈B≈150)
    red_channel = cell[:, :, 2]  # kept for adaptive fallback below
    min_channel = np.min(cell, axis=2)
    _, binarized = cv2.threshold(min_channel, 100, 255, cv2.THRESH_BINARY_INV)

    # Morphological open with 2×2 kernel to clean noise
    binarized = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    # Remove horizontal/vertical template grid lines (photographed as gray, captured as ink)
    _cell_inner_w = x1 - x0
    _cell_inner_h = y1 - y0
    _hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, int(_cell_inner_w * 0.60)), 1))
    _vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, int(_cell_inner_h * 0.60))))
    _h_lines = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, _hk)
    _v_lines = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, _vk)
    binarized = cv2.subtract(binarized, cv2.add(_h_lines, _v_lines))

    # Remove small connected components (noise)
    cc_min = max(5, int(12 * scale))
    n_cc, labels, cc_stats, _ = cv2.connectedComponentsWithStats(binarized, 8)
    for i in range(1, n_cc):
        if cc_stats[i, cv2.CC_STAT_AREA] < cc_min:
            binarized[labels == i] = 0

    # Autocrop to ink bounding box with 4px padding
    ink_coords = np.argwhere(binarized > 0)
    min_ink_small = max(5, int(15 * scale))
    min_ink = min_ink_small if char_name in _SMALL_CHARS else max(10, int(35 * scale))
    if len(ink_coords) < min_ink:
        # Fallback: adaptive threshold on red channel for faded ink.
        # Avoids blue guide lines (R≈170) by operating on the red channel only.
        cell_area = max(1, (x1 - x0) * (y1 - y0))
        if (binarized > 0).sum() / cell_area < 0.005:
            binarized_ad = cv2.adaptiveThreshold(
                red_channel, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 15, 8)
            binarized_ad = cv2.morphologyEx(binarized_ad, cv2.MORPH_OPEN,
                                             np.ones((2, 2), np.uint8))
            n2, lbl2, st2, _ = cv2.connectedComponentsWithStats(binarized_ad, 8)
            for j in range(1, n2):
                if st2[j, cv2.CC_STAT_AREA] < cc_min:
                    binarized_ad[lbl2 == j] = 0
            ink_coords2 = np.argwhere(binarized_ad > 0)
            if len(ink_coords2) >= min_ink:
                binarized  = binarized_ad
                ink_coords = ink_coords2
            else:
                return None
        else:
            return None

    y_min, x_min = ink_coords.min(axis=0)
    y_max, x_max = ink_coords.max(axis=0)
    y_min = max(0, y_min - pad)
    x_min = max(0, x_min - pad)
    y_max = min(binarized.shape[0] - 1, y_max + pad)
    x_max = min(binarized.shape[1] - 1, x_max + pad)
    crop = binarized[y_min:y_max + 1, x_min:x_max + 1]

    min_crop = max(4, int(8 * scale))
    if crop.shape[0] < min_crop or crop.shape[1] < min_crop:
        return None

    # RGBA: black ink on transparent background
    rgba = np.zeros((*crop.shape, 4), np.uint8)
    rgba[crop > 128] = [0, 0, 0, 240]
    return Image.fromarray(rgba, 'RGBA')


def _auto_deskew(img_bgr):
    """
    Correct image tilt using Hough line detection.
    Only applies if |angle| is in (0.5°, 10°) and ≥5 lines support it.
    BORDER_REPLICATE fills any new border pixels from rotation.
    """
    import cv2
    import numpy as np

    gray  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=150)
    if lines is None or len(lines) < 5:
        return img_bgr

    angles = []
    for line in lines:
        rho, theta = line[0]
        angle = np.degrees(theta) - 90.0
        if 0.5 < abs(angle) < 10.0:
            angles.append(angle)
    if len(angles) < 5:
        return img_bgr

    skew = float(np.median(angles))
    h, w = img_bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), -skew, 1.0)
    return cv2.warpAffine(img_bgr, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def _normalize_brightness(img_bgr):
    """
    Per-channel brightness normalization via large-kernel Gaussian blur.
    Flattens uneven lighting without touching fine-grained ink detail.
    """
    import cv2
    import numpy as np

    # Divide by local mean, multiply by 255 so background stays white (not gray).
    # This corrects uneven lighting while keeping blue lines (R≈170) above the
    # red-channel threshold (160) and black ink well below it.
    blur = cv2.GaussianBlur(img_bgr.astype(np.float32), (101, 101), 0)
    corrected = img_bgr.astype(np.float32) * 255.0 / (blur + 1e-6)
    return np.clip(corrected, 0, 255).astype(np.uint8)


def _reduce_noise(img_bgr):
    """Bilateral filter: reduce sensor/scanner noise while keeping ink edges sharp."""
    import cv2
    return cv2.bilateralFilter(img_bgr, d=5, sigmaColor=40, sigmaSpace=40)


def _enhance_red_channel(img_bgr):
    """
    CLAHE on the red channel to improve local contrast for ink vs. background.
    Applied to the warped (2550×3300) image before cell extraction.
    """
    import cv2
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    result = img_bgr.copy()
    result[:, :, 2] = clahe.apply(img_bgr[:, :, 2])  # BGR: index 2 = Red
    return result


def _sharpen(img_bgr):
    """Unsharp mask to crisp ink edges after perspective warp upscaling."""
    import cv2
    blur = cv2.GaussianBlur(img_bgr, (0, 0), 2.0)
    return cv2.addWeighted(img_bgr, 1.5, blur, -0.5, 0)


def preprocess_photo(img_bgr):
    """
    Harden an uploaded template photo for the extraction pipeline.

    Pipeline: deskew → normalize brightness → denoise.
    Applied before _find_corners + _perspective_warp.
    Post-warp steps (_enhance_red_channel, _sharpen) are applied inside
    _extract_v7_template after the perspective transform.
    """
    img_bgr = _auto_deskew(img_bgr)
    img_bgr = _normalize_brightness(img_bgr)
    img_bgr = _reduce_noise(img_bgr)
    return img_bgr


def _extract_v7_template(saved_pages: list) -> dict:
    """
    Main extraction pipeline for v7 blue templates.
    Mirrors extract_v6.run() — warp to 2550×3300, red channel, known page layouts.

    Args: saved_pages — list of (file_path, page_number) tuples
    Returns: {char: [PIL.Image (RGBA), ...]}
    """
    import cv2
    import numpy as np

    bank: dict[str, list] = {}

    for img_path, pg in saved_pages:
        img_cv = cv2.imread(str(img_path))
        if img_cv is None:
            continue

        # Pre-process: deskew, normalize brightness, reduce noise
        img_cv = preprocess_photo(img_cv)

        # Corner detection on grayscale (only for warp — NOT for extraction)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        corners = _find_corners(gray)

        # Warp color image to 2550×3300, then enhance and sharpen
        warped = _perspective_warp(img_cv, corners)
        warped = _enhance_red_channel(warped)
        warped = _sharpen(warped)

        # Get page-specific grid and character mapping
        cols, rows, ml, mt, cw, ch = _page_grid(pg)
        cells = _page_cells(pg)

        for idx, char in enumerate(cells):
            col = idx % cols
            row = idx // cols
            if row >= rows:
                break
            glyph = _extract_glyph_cell(warped, col, row, ml, mt, cw, ch,
                                         char_name=char)
            if glyph is not None:
                bank.setdefault(char, []).append(glyph)

    return bank


def _check_image_quality(img_path: Path) -> list:
    """Return user-facing warning strings for sharpness, brightness, and aspect ratio."""
    import cv2

    img_cv = cv2.imread(str(img_path))
    if img_cv is None:
        return []

    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    warnings_out = []

    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if lap_var < 50:
        warnings_out.append("Photo is blurry — try holding steadier")

    mean_val = float(gray.mean())
    if mean_val < 80:
        warnings_out.append("Photo is too dark")
    elif mean_val > 220:
        warnings_out.append("Photo is overexposed")

    portrait_ratio = min(w, h) / max(w, h)
    if abs(portrait_ratio - 0.773) > 0.15:
        warnings_out.append("Photo may be cropped incorrectly")

    return warnings_out


# ── Contact sheet generation ───────────────────────────────────────────────────

def _generate_contact_sheet(profile_id: str):
    """
    Build a contact sheet PNG showing all glyphs in the profile, arranged
    in a grid of 128px-high thumbnails with character labels.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    profile_dir = _PROFILES_DIR / profile_id
    glyphs_dir  = profile_dir / "glyphs"
    if not glyphs_dir.exists():
        return

    pngs = sorted(glyphs_dir.glob("*.png"))
    if not pngs:
        return

    # Layout parameters
    thumb_h    = 64
    thumb_w    = 80
    label_h    = 16
    cols       = 16
    bg_color   = (18, 18, 24)
    ink_color  = (200, 200, 210)
    label_col  = (100, 100, 120)
    border_col = (40, 40, 55)

    rows = (len(pngs) + cols - 1) // cols
    sheet_w = cols  * (thumb_w + 2) + 2
    sheet_h = rows  * (thumb_h + label_h + 4) + 4

    sheet = Image.new("RGB", (sheet_w, sheet_h), bg_color)
    draw  = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 10)
    except Exception:
        font = ImageFont.load_default()

    for idx, png in enumerate(pngs):
        col = idx % cols
        row = idx // cols
        cx  = col * (thumb_w + 2) + 2
        cy  = row * (thumb_h + label_h + 4) + 4

        # Draw cell border
        draw.rectangle([cx-1, cy-1, cx+thumb_w, cy+thumb_h+label_h+1], outline=border_col)

        # Load glyph and composite onto dark background
        try:
            glyph = Image.open(png)
            if glyph.mode != "RGBA":
                glyph = glyph.convert("RGBA")

            # Scale to fit thumbnail
            gw, gh = glyph.size
            scale  = min(thumb_w / max(1, gw), thumb_h / max(1, gh))
            nw     = max(1, int(gw * scale))
            nh     = max(1, int(gh * scale))
            glyph  = glyph.resize((nw, nh), Image.LANCZOS)

            # Center in cell
            ox = cx + (thumb_w - nw) // 2
            oy = cy + (thumb_h - nh) // 2

            # Tint alpha channel to light ink color
            cell_bg = Image.new("RGB", (thumb_w, thumb_h), bg_color)
            arr = np.array(glyph)
            alpha = arr[:, :, 3:4] / 255.0
            tinted = np.array(cell_bg.crop((0, 0, thumb_w, thumb_h)))
            # Place glyph at offset
            place = Image.new("RGB", (thumb_w, thumb_h), bg_color)
            glyph_rgb = Image.new("RGB", (nw, nh), ink_color)
            glyph_rgb.putalpha(Image.fromarray(arr[:, :, 3]))
            place.paste(glyph_rgb, (ox - cx, oy - cy), glyph_rgb)
            sheet.paste(place, (cx, cy))
        except Exception:
            pass

        # Character label below thumbnail
        try:
            char = _parse_glyph_stem_local(png.stem)
        except Exception:
            char = png.stem[:3]

        label = char if char else png.stem[:4]
        lx = cx + thumb_w // 2
        ly = cy + thumb_h + 2
        draw.text((lx, ly), label, fill=label_col, font=font, anchor="mt")

    sheet.save(str(profile_dir / "contact_sheet.png"))


def _parse_glyph_stem_local(stem: str) -> str:
    """Minimal stem→char converter (mirrors glyph_loader._parse_glyph_stem)."""
    working = stem
    if working.endswith("_fallback"):
        working = working[:-9]
    _PUNCT = {
        "period": ".", "comma": ",", "exclaim": "!", "question": "?",
        "apostrophe": "'", "hyphen": "-", "colon": ":", "semicolon": ";",
        "lparen": "(", "rparen": ")", "hash": "#", "at": "@",
        "ampersand": "&", "slash": "/", "quote": '"',
    }
    for key, ch in _PUNCT.items():
        if working == key or working.startswith(key + "_"):
            return ch
    if working.startswith("upper_"):
        rest = working[6:]
        parts = rest.split("_")
        if parts and len(parts[0]) == 1:
            return parts[0]
        return "?"
    if working.startswith("digit_"):
        rest = working[6:]
        parts = rest.split("_")
        if parts and parts[0].isdigit():
            return parts[0]
        return "?"
    parts = working.split("_")
    if parts and len(parts[0]) == 1:
        return parts[0]
    return "?"


def _char_to_stem(char: str) -> str:
    """Map a character to its canonical filename stem."""
    _SPECIAL = {
        ".": "period", ",": "comma", "!": "exclaim", "?": "question",
        "'": "apostrophe", "-": "hyphen", ":": "colon", ";": "semicolon",
        "(": "lparen", ")": "rparen", "#": "hash", "@": "atsign",
        "&": "ampersand", "/": "slash", '"': "quote", "$": "dollar",
    }
    if char in _SPECIAL:
        return _SPECIAL[char]
    if char.isupper():
        return f"upper_{char}"
    if char.isdigit():
        return f"digit_{char}"
    return char


# ── Profile.json writer ────────────────────────────────────────────────────────

def _write_profile_json(profile_dir: Path, profile_id: str,
                        saved_chars: dict, source_images: list):
    """Write a canonical profile.json for a newly created profile."""
    import numpy as np
    from PIL import Image

    LOWERCASE   = set("abcdefghijklmnopqrstuvwxyz")
    UPPERCASE   = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    DIGITS      = set("0123456789")
    PUNCTUATION = set(".,!?'-:;()")

    chars = set(saved_chars.keys())
    lc    = chars & LOWERCASE
    uc    = chars & UPPERCASE
    dg    = chars & DIGITS
    pu    = chars & PUNCTUATION

    total_variants = sum(len(v) for v in saved_chars.values())

    per_character = {}
    all_widths, all_heights, all_densities = [], [], []

    glyphs_dir = profile_dir / "glyphs"

    # saved_chars: {char: [{"path": str, "confidence": float, "is_weak": bool}, ...]}
    for char, variants in saved_chars.items():
        widths, heights, confidences = [], [], []
        rel_paths = []
        for v in variants:
            rel_paths.append(v["path"])
            confidences.append(v["confidence"])
            try:
                img = Image.open(glyphs_dir / Path(v["path"]).name)
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                w, h = img.size
                arr  = np.array(img)
                dens = float((arr[:, :, 3] > 10).sum()) / max(1, arr[:, :, 3].size)
                widths.append(w)
                heights.append(h)
                all_densities.append(dens)
            except Exception:
                pass

        max_conf = max(confidences) if confidences else 0.2
        is_weak  = max_conf < 0.5

        per_character[char] = {
            "variants":          rel_paths,
            "avg_width":         round(float(np.mean(widths)),  2) if widths  else 0.0,
            "avg_height":        round(float(np.mean(heights)), 2) if heights else 0.0,
            "confidence":        round(max_conf, 3),
            "is_weak":           is_weak,
            "extraction_method": "template_cell",
        }
        all_widths.extend(widths)
        all_heights.extend(heights)

    standard = LOWERCASE | UPPERCASE | DIGITS | PUNCTUATION
    missing  = sorted(standard - chars)
    weak     = sorted(c for c, e in per_character.items() if e["is_weak"])

    profile = {
        "profile_id":    profile_id,
        "created_at":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_method": "template",
        "source_images": [str(p) for p in source_images],
        "character_coverage": {
            "lowercase_pct":   round(len(lc) / 26 * 100, 1),
            "uppercase_pct":   round(len(uc) / 26 * 100, 1),
            "digits_pct":      round(len(dg) / 10 * 100, 1),
            "punctuation_pct": round(len(pu) / 10 * 100, 1),
            "total_characters": len(chars),
            "total_variants":   total_variants,
            "lowercase_complete":   len(lc) == 26,
            "uppercase_complete":   len(uc) == 26,
            "digits_complete":      len(dg) == 10,
        },
        "per_character": per_character,
        "style_metrics": {
            "avg_glyph_width":        round(float(np.mean(all_widths)),    2) if all_widths    else 0.0,
            "median_x_height":        128.0,
            "baseline_offset":        0.0,
            "slant_estimate_degrees": 0.0,
            "avg_stroke_width":       8.0,
            "ink_density":            round(float(np.mean(all_densities)), 4) if all_densities else 0.0,
        },
        "missing_characters": missing,
        "weak_characters":    weak,
        # Partial profiles are immediately usable — fallback_dummy fills gaps
        "usable":             len(lc) >= 1,
    }

    (profile_dir / "profile.json").write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Style analysis routes ──────────────────────────────────────────────────────

