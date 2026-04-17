import numpy as np
from PIL import Image, ImageFilter

def composite(text_image: Image.Image,
              background: Image.Image,
              ink_color: tuple = (0, 0, 0),
              opacity: float = 1.0) -> Image.Image:
    """
    Composite rendered handwriting onto a paper background.

    text_image: RGBA image from renderer (transparent background, ink in alpha)
    background: RGB paper background image
    ink_color: (R, G, B) tuple for ink color
    opacity: global opacity multiplier (0-1)

    Algorithm:
    1. Resize text_image to match background if sizes differ
    2. Extract alpha channel from text_image
    3. Scale alpha by opacity
    4. For each pixel: output = background * (1 - alpha) + ink_color * alpha
    5. Apply slight ink-paper interaction: at boundaries, blend slightly

    Returns: RGB PIL Image
    """
    # Ensure same size
    if text_image.size != background.size:
        text_image = text_image.resize(background.size, Image.LANCZOS)

    # Ink bleed: blur alpha channel slightly to simulate ink spreading into paper fibers
    r, g, b, a = text_image.split()
    a = a.filter(ImageFilter.GaussianBlur(radius=0.4))
    text_image = Image.merge('RGBA', (r, g, b, a))

    # Convert to numpy arrays
    bg = np.array(background).astype(float)
    text_arr = np.array(text_image).astype(float)

    # Extract and normalize alpha
    alpha = text_arr[:, :, 3] / 255.0 * opacity
    alpha = alpha[:, :, np.newaxis]  # broadcast to 3 channels

    # Create ink color layer with per-character color variation (±6 per RGB channel)
    ink = np.full_like(bg, ink_color, dtype=float)
    noise = np.random.randint(-6, 7, ink.shape).astype(float)
    ink = np.clip(ink + noise, 0, 255)

    # Alpha compositing
    result = bg * (1.0 - alpha) + ink * alpha
    result = np.clip(result, 0, 255).astype(np.uint8)

    return Image.fromarray(result, 'RGB')


# Predefined ink colors
INK_COLORS = {
    "black": (10, 10, 10),
    "blue": (15, 25, 110),
    "dark_blue": (5, 15, 80),
    "green": (10, 60, 35),
    "red": (130, 15, 15),
    "pencil": (80, 80, 80),
}


if __name__ == "__main__":
    from render_engine import HandwritingRenderer, create_dummy_glyph_bank
    from paper_backgrounds import generate_college_ruled, generate_blank_paper, generate_legal_pad

    print("Testing compositor...")

    # Create test handwriting
    bank = create_dummy_glyph_bank()
    renderer = HandwritingRenderer(bank, seed=42)
    text = "The quick brown fox jumps over the lazy dog. " * 8
    text += "Pack my box with five dozen jugs of liquid soap."
    text_img = renderer.render(text)

    # Test with different papers and ink colors
    tests = [
        ("college_ruled_black", generate_college_ruled(), "black"),
        ("college_ruled_blue", generate_college_ruled(), "blue"),
        ("blank_black", generate_blank_paper(), "black"),
        ("legal_pad_blue", generate_legal_pad(), "dark_blue"),
        ("blank_pencil", generate_blank_paper(), "pencil"),
    ]

    for name, paper, color_name in tests:
        color = INK_COLORS[color_name]
        result = composite(text_img, paper, ink_color=color)
        path = f"output/composite_{name}.png"
        result.save(path)
        print(f"✅ Saved {name}: {result.size}, {result.mode}")
        assert result.mode == "RGB"
        assert result.size == paper.size

    print("\n✅ All compositor tests passed!")
