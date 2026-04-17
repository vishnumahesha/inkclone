import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import cv2
import math

DEFAULT_WIDTH = 2400
DEFAULT_HEIGHT = 3200
DPI = 150

# Index card dimensions: 3x5 inches @ 150 DPI
INDEX_CARD_WIDTH = int(5 * DPI)   # 750px
INDEX_CARD_HEIGHT = int(3 * DPI)  # 450px

# Sticky note dimensions: 3x3 inches @ 150 DPI  
STICKY_NOTE_WIDTH = int(3 * DPI)   # 450px
STICKY_NOTE_HEIGHT = int(3 * DPI)  # 450px

def _perlin_noise(width, height, scale=50, octaves=4):
    """Generate Perlin-like noise for paper texture."""
    result = np.zeros((height, width), dtype=np.float32)
    amplitude = 1.0
    frequency = 1.0 / scale
    max_amplitude = 0.0
    
    for _ in range(octaves):
        noise_width = max(1, int(width * frequency))
        noise_height = max(1, int(height * frequency))
        octave_noise = np.random.rand(noise_height, noise_width).astype(np.float32)
        octave_noise = cv2.resize(octave_noise, (width, height), interpolation=cv2.INTER_LINEAR)
        result += octave_noise * amplitude
        max_amplitude += amplitude
        frequency *= 2.0
        amplitude *= 0.5
    
    result = result / max_amplitude
    return result

def _add_fiber_texture(img, intensity=1.0):
    """Add realistic paper fiber texture with directional streaks."""
    height, width = img.shape[:2]
    fibers = np.zeros((height, width), dtype=np.float32)
    
    # Horizontal fiber streaks (paper fibers run mostly horizontal)
    for y in range(0, height, 3):
        streak_length = np.random.randint(200, 800)
        streak_x = np.random.randint(0, width - streak_length)
        opacity = np.random.uniform(0.02, 0.08)
        fibers[y, streak_x:streak_x+streak_length] += opacity
    
    # Vertical fiber streaks (some run vertical)
    for x in range(0, width, 5):
        streak_length = np.random.randint(100, 400)
        streak_y = np.random.randint(0, height - streak_length)
        opacity = np.random.uniform(0.01, 0.04)
        fibers[streak_y:streak_y+streak_length, x] += opacity
    
    # Blur to make fibers smooth
    fibers = cv2.GaussianBlur(fibers, (5, 5), 1.0)
    
    # Apply to image
    for c in range(3):
        img[:, :, c] = np.clip(
            img[:, :, c].astype(np.float32) - fibers * 50 * intensity,
            0, 255
        ).astype(np.uint8)
    
    return img

def generate_blank_paper(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT) -> Image.Image:
    """Generate realistic blank white paper."""
    img = np.ones((height, width, 3), dtype=np.uint8) * np.array([250, 248, 245], dtype=np.uint8)
    
    # Add subtle Perlin noise texture
    noise = _perlin_noise(width, height, scale=100, octaves=3)
    noise = (noise - 0.5) * 4
    
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.float32) + noise, 0, 255).astype(np.uint8)
    
    # Add slight brightness gradient
    gradient = np.linspace(1.0, 1.02, width)[np.newaxis, :]
    for c in range(3):
        img[:, :, c] = (img[:, :, c].astype(np.float32) * gradient).astype(np.uint8)
    
    # Add fiber texture
    img = _add_fiber_texture(img, intensity=0.5)
    
    pil_img = Image.fromarray(img, mode='RGB')
    
    # Add very faint random fiber lines
    draw = ImageDraw.Draw(pil_img, 'RGBA')
    for _ in range(50):
        y = np.random.randint(0, height)
        x_start = 0
        x_end = width
        opacity = int(255 * 0.05)
        draw.line([(x_start, y), (x_end, y)], fill=(200, 200, 200, opacity), width=1)
    
    return pil_img

def generate_college_ruled(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT) -> Image.Image:
    """Generate college ruled notebook paper with realistic improvements."""
    img = np.ones((height, width, 3), dtype=np.uint8) * np.array([252, 250, 247], dtype=np.uint8)
    
    # Add paper texture
    noise = _perlin_noise(width, height, scale=100, octaves=3)
    noise = (noise - 0.5) * 4
    
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.float32) + noise, 0, 255).astype(np.uint8)
    
    # Add subtle fiber texture
    img = _add_fiber_texture(img, intensity=0.3)
    
    pil_img = Image.fromarray(img, mode='RGB')
    draw = ImageDraw.Draw(pil_img)
    
    # Horizontal rules with wobble and color variation per line
    line_spacing = 42
    start_y = 120
    end_y = height - 100
    
    line_idx = 0
    for y in range(start_y, end_y, line_spacing):
        # Slight color variation per line (more realistic)
        color_offset = np.random.randint(-5, 6)
        base_color = (170, 200, 225)
        line_color = tuple(np.clip(np.array(base_color) + color_offset, 0, 255))
        
        # Create wobbled line
        wobble_freq = np.random.uniform(0.5, 2.0)
        wobble_amp = 0.3
        
        points = []
        for x in range(0, width, 5):
            wobble = wobble_amp * np.sin(x * wobble_freq / 100)
            points.append((x, y + wobble))
        
        for i in range(len(points) - 1):
            draw.line([points[i], points[i+1]], fill=line_color, width=1)
        
        line_idx += 1
    
    # Left margin line with wobble
    margin_x = 200
    margin_color = (220, 140, 140)
    wobble_freq = np.random.uniform(0.5, 1.5)
    wobble_amp = 0.4
    
    margin_points = []
    for y in range(0, height, 5):
        wobble = wobble_amp * np.sin(y * wobble_freq / 100)
        margin_points.append((margin_x + wobble, y))
    
    for i in range(len(margin_points) - 1):
        draw.line([margin_points[i], margin_points[i+1]], fill=margin_color, width=2)
    
    # Three hole punch marks (improved appearance)
    hole_radius = 10
    hole_positions = [
        (50, int(height * 0.25)),
        (50, int(height * 0.50)),
        (50, int(height * 0.75))
    ]
    
    for hx, hy in hole_positions:
        # Draw circle with gradient-like effect (darker edge)
        for r in range(hole_radius, 0, -1):
            shade = int(200 + r * 2)
            draw.ellipse(
                [(hx - r, hy - r), (hx + r, hy + r)],
                outline=(shade, shade, shade),
                width=1
            )
    
    return pil_img

def generate_wide_ruled(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT) -> Image.Image:
    """Generate wide ruled paper (8.7mm spacing)."""
    img = np.ones((height, width, 3), dtype=np.uint8) * np.array([252, 250, 247], dtype=np.uint8)
    
    noise = _perlin_noise(width, height, scale=100, octaves=3)
    noise = (noise - 0.5) * 4
    
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.float32) + noise, 0, 255).astype(np.uint8)
    
    img = _add_fiber_texture(img, intensity=0.3)
    pil_img = Image.fromarray(img, mode='RGB')
    draw = ImageDraw.Draw(pil_img)
    
    # Wider spacing
    line_spacing = 51
    line_color = (170, 200, 225)
    start_y = 120
    end_y = height - 100
    
    for y in range(start_y, end_y, line_spacing):
        wobble_freq = np.random.uniform(0.5, 2.0)
        wobble_amp = 0.3
        
        points = []
        for x in range(0, width, 5):
            wobble = wobble_amp * np.sin(x * wobble_freq / 100)
            points.append((x, y + wobble))
        
        for i in range(len(points) - 1):
            draw.line([points[i], points[i+1]], fill=line_color, width=1)
    
    # Margin line
    margin_x = 200
    margin_color = (220, 140, 140)
    wobble_freq = np.random.uniform(0.5, 1.5)
    wobble_amp = 0.4
    
    margin_points = []
    for y in range(0, height, 5):
        wobble = wobble_amp * np.sin(y * wobble_freq / 100)
        margin_points.append((margin_x + wobble, y))
    
    for i in range(len(margin_points) - 1):
        draw.line([margin_points[i], margin_points[i+1]], fill=margin_color, width=2)
    
    # Hole punches
    hole_radius = 10
    hole_positions = [
        (50, int(height * 0.25)),
        (50, int(height * 0.50)),
        (50, int(height * 0.75))
    ]
    
    for hx, hy in hole_positions:
        for r in range(hole_radius, 0, -1):
            shade = int(200 + r * 2)
            draw.ellipse(
                [(hx - r, hy - r), (hx + r, hy + r)],
                outline=(shade, shade, shade),
                width=1
            )
    
    return pil_img

def generate_graph_paper(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT) -> Image.Image:
    """Generate graph/grid paper."""
    img = np.ones((height, width, 3), dtype=np.uint8) * 255
    
    noise = _perlin_noise(width, height, scale=150, octaves=2)
    noise = (noise - 0.5) * 2
    
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.float32) + noise, 0, 255).astype(np.uint8)
    
    pil_img = Image.fromarray(img, mode='RGB')
    draw = ImageDraw.Draw(pil_img)
    
    grid_spacing = 30
    grid_color = (200, 210, 220)
    
    for y in range(0, height, grid_spacing):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)
    
    for x in range(0, width, grid_spacing):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    
    return pil_img

def generate_legal_pad(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT) -> Image.Image:
    """Generate yellow legal pad paper."""
    img = np.ones((height, width, 3), dtype=np.uint8) * np.array([255, 252, 205], dtype=np.uint8)
    
    noise = _perlin_noise(width, height, scale=80, octaves=3)
    noise = (noise - 0.5) * 6
    
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.float32) + noise, 0, 255).astype(np.uint8)
    
    # Add fiber texture
    img = _add_fiber_texture(img, intensity=0.4)
    
    # Add darker header area
    header_height = 150
    for y in range(header_height):
        darkness = (1.0 - y / header_height) * 10
        for c in range(3):
            img[y, :, c] = np.clip(img[y, :, c].astype(np.float32) - darkness, 0, 255).astype(np.uint8)
    
    pil_img = Image.fromarray(img, mode='RGB')
    draw = ImageDraw.Draw(pil_img)
    
    # Horizontal rules with color variation
    line_spacing = 51
    line_color = (140, 170, 200)
    start_y = 150 + 51
    end_y = height - 100
    
    for y in range(start_y, end_y, line_spacing):
        wobble_freq = np.random.uniform(0.5, 2.0)
        wobble_amp = 0.3
        
        color_offset = np.random.randint(-3, 4)
        var_color = tuple(np.clip(np.array(line_color) + color_offset, 0, 255))
        
        points = []
        for x in range(0, width, 5):
            wobble = wobble_amp * np.sin(x * wobble_freq / 100)
            points.append((x, y + wobble))
        
        for i in range(len(points) - 1):
            draw.line([points[i], points[i+1]], fill=var_color, width=1)
    
    # Heavy line at bottom of header
    draw.line([(0, 150), (width, 150)], fill=line_color, width=3)
    
    # Margin line
    margin_x = 200
    margin_color = (210, 120, 120)
    wobble_freq = np.random.uniform(0.5, 1.5)
    wobble_amp = 0.4
    
    margin_points = []
    for y in range(0, height, 5):
        wobble = wobble_amp * np.sin(y * wobble_freq / 100)
        margin_points.append((margin_x + wobble, y))
    
    for i in range(len(margin_points) - 1):
        draw.line([margin_points[i], margin_points[i+1]], fill=margin_color, width=2)
    
    return pil_img


if __name__ == "__main__":
    print("Testing improved paper backgrounds...")
    
    papers = {
        "blank": generate_blank_paper(),
        "college_ruled": generate_college_ruled(),
        "wide_ruled": generate_wide_ruled(),
        "graph": generate_graph_paper(),
        "legal_pad": generate_legal_pad(),
    }
    
    for name, img in papers.items():
        path = f"output/improvements/paper_{name}_improved.png"
        img.save(path)
        print(f"✅ Saved {name}: {img.size}, {img.mode}")
        
        assert img.size == (DEFAULT_WIDTH, DEFAULT_HEIGHT), f"{name} wrong size"
        assert img.mode == "RGB", f"{name} wrong mode"
        
        arr = np.array(img)
        assert arr.std() > 1.0, f"{name} looks too uniform"
    
    print("\n✅ All improved paper backgrounds generated!")

def generate_index_card(ruled=False):
    """Generate a 3x5 inch white index card with optional ruled lines."""
    width = INDEX_CARD_WIDTH
    height = INDEX_CARD_HEIGHT
    
    # White background
    arr = np.ones((height, width, 3), dtype=np.uint8) * 255
    pil_img = Image.fromarray(arr, 'RGB')
    draw = ImageDraw.Draw(pil_img)
    
    # Border
    border_color = (200, 200, 200)
    draw.rectangle([0, 0, width-1, height-1], outline=border_color, width=2)
    
    if ruled:
        # Horizontal ruled lines (8 lines on 3" = 0.375" spacing)
        line_spacing = int(height / 8)
        line_color = (220, 220, 220)
        
        for y in range(line_spacing, height, line_spacing):
            draw.line([(0, y), (width, y)], fill=line_color, width=1)
    
    return pil_img


def generate_sticky_note(size_inches=3):
    """Generate a sticky note (yellow paper with curl shadow)."""
    # 3x3 inches @ 150 DPI
    width = int(size_inches * DPI)
    height = int(size_inches * DPI)
    
    # Sticky note yellow background
    arr = np.ones((height, width, 3), dtype=np.uint8)
    arr[:, :, 0] = 255  # Red
    arr[:, :, 1] = 255  # Green
    arr[:, :, 2] = 200  # Blue (less blue = yellow)
    
    pil_img = Image.fromarray(arr, 'RGB')
    draw = ImageDraw.Draw(pil_img, 'RGBA')
    
    # Add subtle curl shadow on bottom right corner
    # Gradient shadow effect
    shadow_size = 40
    for i in range(shadow_size):
        alpha = int((1.0 - (i / shadow_size)) * 80)
        shadow_color = (100, 100, 100, alpha)
        
        # Bottom right corner
        x1 = width - shadow_size + i
        y1 = height - shadow_size
        x2 = width
        y2 = height - shadow_size + i
        
        draw.line([(x1, y1), (x2, y2)], fill=shadow_color, width=2)
    
    # Right edge shadow
    for i in range(20):
        alpha = int((1.0 - (i / 20)) * 40)
        shadow_color = (80, 80, 80, alpha)
        x = width - i
        draw.line([(x, 0), (x, height)], fill=shadow_color, width=1)
    
    # Bottom edge shadow
    for i in range(20):
        alpha = int((1.0 - (i / 20)) * 40)
        shadow_color = (80, 80, 80, alpha)
        y = height - i
        draw.line([(0, y), (width, y)], fill=shadow_color, width=1)
    
    return pil_img.convert('RGB')


def generate_dot_grid(dot_spacing_mm=5):
    """Generate white paper with light gray dots at specified spacing (default 5mm)."""
    width = DEFAULT_WIDTH
    height = DEFAULT_HEIGHT
    
    # White background
    arr = np.ones((height, width, 3), dtype=np.uint8) * 255
    pil_img = Image.fromarray(arr, 'RGB')
    draw = ImageDraw.Draw(pil_img)
    
    # Convert mm to pixels at 150 DPI
    # 1 inch = 25.4 mm = 150 pixels
    dot_spacing_px = int((dot_spacing_mm / 25.4) * DPI)
    dot_radius = 2
    dot_color = (200, 200, 200)
    
    # Draw dot grid
    for y in range(0, height, dot_spacing_px):
        for x in range(0, width, dot_spacing_px):
            draw.ellipse(
                [x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius],
                fill=dot_color
            )
    
    return pil_img


if __name__ == "__main__":
    print("Testing improved paper backgrounds...")
    
    papers = {
        "blank": generate_blank_paper(),
        "college_ruled": generate_college_ruled(),
        "wide_ruled": generate_wide_ruled(),
        "graph": generate_graph_paper(),
        "legal_pad": generate_legal_pad(),
        "index_card": generate_index_card(ruled=True),
        "sticky_note": generate_sticky_note(),
        "dot_grid": generate_dot_grid(),
    }
    
    for name, img in papers.items():
        path = f"output/{name}_sample.png"
        img.save(path)
        print(f"✅ Saved {name}: {img.size}, {img.mode}")
    
    print("\n✅ All paper backgrounds generated!")
