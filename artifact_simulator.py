import cv2
import numpy as np
from PIL import Image
import math
import io

def simulate_scan(image: Image.Image,
                  contrast_boost: float = 1.2,
                  sharpen_amount: float = 0.3,
                  rotation_degrees: float = None,
                  jpeg_quality: int = 92) -> Image.Image:
    """Simulate a flatbed scanner with realistic effects."""
    
    arr = np.array(image).astype(float)

    # 1. Slight rotation
    if rotation_degrees is None:
        rotation_degrees = np.random.uniform(0.1, 0.5) * np.random.choice([-1, 1])
    h, w = arr.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, rotation_degrees, 1.0)
    arr = cv2.warpAffine(arr.astype(np.uint8), M, (w, h),
                         borderMode=cv2.BORDER_REPLICATE).astype(float)

    # 2. Contrast boost
    mean = arr.mean()
    arr = (arr - mean) * contrast_boost + mean
    arr = np.clip(arr, 0, 255)

    # 3. Unsharp mask
    blurred = cv2.GaussianBlur(arr.astype(np.uint8), (0, 0), 1.0)
    arr = arr + sharpen_amount * (arr - blurred)
    arr = np.clip(arr, 0, 255)

    # 4. Subtle page border shadow
    border_width = 5
    fade = 0.90
    arr[-border_width:, :] *= fade
    arr[:, -border_width:] *= fade
    arr = np.clip(arr, 0, 255)

    # 5. JPEG compression
    result = Image.fromarray(arr.astype(np.uint8))
    buffer = io.BytesIO()
    result.save(buffer, format='JPEG', quality=jpeg_quality)
    buffer.seek(0)
    result = Image.open(buffer).convert('RGB')

    return result


def simulate_phone_photo(image: Image.Image,
                         perspective_strength: float = 0.02,
                         gradient_strength: float = 0.08,
                         noise_sigma: float = 3.0,
                         blur_sigma: float = 0.4,
                         warmth_shift: int = 5,
                         jpeg_quality: int = 85) -> Image.Image:
    """Simulate phone camera with realistic effects including page curl, vignetting."""
    
    arr = np.array(image).astype(float)
    h, w = arr.shape[:2]

    # 1. Perspective warp (page curl simulation)
    offset = int(w * perspective_strength)
    
    # Create a curved warp instead of straight trapezoid
    src_pts = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    
    # Slight bottom curve (as if page is curled upward at bottom)
    curve_amount = int(w * 0.015)
    dst_pts = np.float32([
        [offset, 0],
        [w - offset, 0],
        [w - curve_amount, h],
        [curve_amount, h]
    ])
    
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    arr = cv2.warpPerspective(arr.astype(np.uint8), M, (w, h),
                              borderMode=cv2.BORDER_REPLICATE).astype(float)

    # 2. Realistic lighting gradient (stronger at edges)
    gradient_x = np.linspace(1.0, 1.0 - gradient_strength, w).reshape(1, w, 1)
    gradient_y = np.linspace(1.0, 1.0 - gradient_strength * 0.5, h).reshape(h, 1, 1)
    
    # Add corner vignetting (darkening at corners)
    corner_vignette = np.ones((h, w, 1), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            # Distance from center
            dy = abs(y - h/2) / (h/2)
            dx = abs(x - w/2) / (w/2)
            # Quadratic falloff from center
            dist = math.sqrt(dx*dx + dy*dy)
            corner_vignette[y, x, 0] *= (1.0 - dist * 0.4)
    
    arr = arr * gradient_x * gradient_y * corner_vignette
    arr = np.clip(arr, 0, 255)

    # 3. White balance / warmth shift
    arr[:, :, 0] = np.clip(arr[:, :, 0] + warmth_shift, 0, 255)  # warmer red
    arr[:, :, 2] = np.clip(arr[:, :, 2] - warmth_shift // 2, 0, 255)  # cooler blue

    # 4. Gaussian noise (camera sensor noise)
    noise = np.random.normal(0, noise_sigma, arr.shape)
    arr = arr + noise
    arr = np.clip(arr, 0, 255)

    # 5. Slight blur (camera focus/lens)
    if blur_sigma > 0:
        arr = cv2.GaussianBlur(arr.astype(np.uint8), (0, 0), blur_sigma).astype(float)

    # 6. Shadow on left edge (holding fingerprint + natural shadow)
    shadow_width = 60
    shadow = np.linspace(0.85, 1.0, shadow_width).reshape(1, shadow_width, 1)
    arr[:, :shadow_width] *= shadow
    
    # Shadow on top edge (finger/hand in frame)
    shadow_height = 40
    shadow_top = np.linspace(0.90, 1.0, shadow_height).reshape(shadow_height, 1, 1)
    arr[:shadow_height, :] *= shadow_top
    
    arr = np.clip(arr, 0, 255)

    # 7. JPEG compression
    result = Image.fromarray(arr.astype(np.uint8))
    buffer = io.BytesIO()
    result.save(buffer, format='JPEG', quality=jpeg_quality)
    buffer.seek(0)
    result = Image.open(buffer).convert('RGB')

    return result


def simulate_clean(image: Image.Image) -> Image.Image:
    """Return clean render (no artifacts)."""
    return image.convert('RGB') if image.mode != 'RGB' else image.copy()


if __name__ == "__main__":
    print("Testing improved artifact simulator...")

    import os
    test_path = "output/composite_college_ruled_black.png"
    
    if not os.path.exists(test_path):
        # Create a test image
        img = Image.new('RGB', (2400, 3200), (250, 248, 245))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        for y in range(200, 3000, 80):
            draw.text((220, y), "Test text for artifact simulation", fill=(20, 20, 20))
    else:
        img = Image.open(test_path)

    print(f"Input image: {img.size}")

    # Test scan simulation
    scan_result = simulate_scan(img)
    scan_result.save("output/improvements/artifact_scan_improved.png")
    print(f"✅ Scan simulation: {scan_result.size}, {scan_result.mode}")
    assert scan_result.mode == "RGB"

    # Test improved phone photo simulation
    photo_result = simulate_phone_photo(img)
    photo_result.save("output/improvements/artifact_phone_improved.png")
    print(f"✅ Phone photo simulation: {photo_result.size}, {photo_result.mode}")
    assert photo_result.mode == "RGB"

    # Test clean render
    clean_result = simulate_clean(img)
    clean_result.save("output/improvements/artifact_clean.png")
    print(f"✅ Clean render: {clean_result.size}, {clean_result.mode}")

    # Verify differences
    clean_arr = np.array(clean_result).astype(float)
    scan_arr = np.array(scan_result).astype(float)
    photo_arr = np.array(photo_result).astype(float)

    scan_diff = np.abs(clean_arr - scan_arr).mean()
    photo_diff = np.abs(clean_arr - photo_arr).mean()
    print(f"Scan diff from clean: {scan_diff:.2f}")
    print(f"Photo diff from clean: {photo_diff:.2f}")
    assert scan_diff > 0.5, "Scan should differ from clean"
    assert photo_diff > 0.5, "Photo should differ from clean"

    print("\n✅ All artifact simulator improvements tested!")
