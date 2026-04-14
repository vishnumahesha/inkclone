#!/usr/bin/env python3
"""
Ink Effects - Post-processing for rendered glyphs

Applies realistic ink effects to text before compositing:
- Ballpoint: ink blobs and skip artifacts
- Gel pen: smooth, dark, slight smearing
- Pencil: light, grainy texture
- Felt tip: thick strokes, soft edges
"""

import numpy as np
from PIL import Image
import cv2

class InkEffects:
    """Post-processing effects for rendered glyphs."""
    
    @staticmethod
    def apply_ballpoint_effect(image):
        """Add occasional ink blobs and skip artifacts (ballpoint pen)."""
        arr = np.array(image).astype(np.float32)
        
        if arr.shape[2] != 4:
            raise ValueError("Image must be RGBA")
        
        # Ink blobs at random stroke starts
        h, w = arr.shape[:2]
        num_blobs = np.random.randint(2, 6)
        
        for _ in range(num_blobs):
            by = np.random.randint(h // 4, 3*h // 4)
            bx = np.random.randint(w // 4, 3*w // 4)
            blob_size = np.random.randint(3, 8)
            
            y_start = max(0, by - blob_size)
            y_end = min(h, by + blob_size)
            x_start = max(0, bx - blob_size)
            x_end = min(w, bx + blob_size)
            
            arr[y_start:y_end, x_start:x_end, 3] = np.clip(
                arr[y_start:y_end, x_start:x_end, 3] * 1.3, 0, 255
            )
        
        # Skip artifacts
        num_skips = np.random.randint(1, 3)
        for _ in range(num_skips):
            skip_y = np.random.randint(h // 4, 3*h // 4)
            skip_x_start = np.random.randint(0, w // 2)
            skip_len = np.random.randint(5, 20)
            skip_x_end = min(w, skip_x_start + skip_len)
            
            arr[skip_y, skip_x_start:skip_x_end, 3] = arr[skip_y, skip_x_start:skip_x_end, 3] * 0.3
        
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGBA')
    
    @staticmethod
    def apply_gel_pen_effect(image):
        """Smooth, dark strokes with slight smearing (gel pen)."""
        arr = np.array(image).astype(np.float32)
        
        if arr.shape[2] != 4:
            raise ValueError("Image must be RGBA")
        
        arr[:, :, 3] = np.clip(arr[:, :, 3] * 1.15, 0, 255)
        
        alpha = arr[:, :, 3]
        alpha_blurred = cv2.GaussianBlur(alpha, (3, 3), 0.5)
        alpha = (alpha * 0.7 + alpha_blurred * 0.3)
        arr[:, :, 3] = alpha
        
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGBA')
    
    @staticmethod
    def apply_pencil_effect(image):
        """Light, grainy texture (pencil)."""
        arr = np.array(image).astype(np.float32)
        
        if arr.shape[2] != 4:
            raise ValueError("Image must be RGBA")
        
        arr[:, :, 3] = np.clip(arr[:, :, 3] * 0.7, 0, 255)
        
        h, w = arr.shape[:2]
        grain = np.random.normal(1.0, 0.15, (h, w))
        grain = np.clip(grain, 0.7, 1.3)
        
        arr[:, :, 3] = arr[:, :, 3] * grain
        
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGBA')
    
    @staticmethod
    def apply_felt_tip_effect(image):
        """Thick strokes with soft edges (felt tip marker)."""
        arr = np.array(image).astype(np.float32)
        
        if arr.shape[2] != 4:
            raise ValueError("Image must be RGBA")
        
        alpha = arr[:, :, 3].astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        alpha_thick = cv2.dilate(alpha, kernel, iterations=1)
        alpha_soft = cv2.GaussianBlur(alpha_thick.astype(np.float32), (3, 3), 1.0)
        
        arr[:, :, 3] = alpha_soft
        
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGBA')


def test_ink_effects():
    """Test all ink effects with comparison output."""
    import os
    
    print("Testing ink effects...")
    os.makedirs("output/ink_effects", exist_ok=True)
    
    # Create test glyph
    test_img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    arr = np.array(test_img)
    
    y_range = np.arange(20, 80)
    for y in y_range:
        x_left = 30 + (80 - y) // 3
        x_right = 70 - (80 - y) // 3
        arr[y, max(0, x_left):min(100, x_right), :3] = 0
        arr[y, max(0, x_left):min(100, x_right), 3] = 200
    
    test_img = Image.fromarray(arr, 'RGBA')
    test_img.save("output/ink_effects/0_original.png")
    print("✅ Saved original")
    
    effects = [
        ("ballpoint", InkEffects.apply_ballpoint_effect),
        ("gel_pen", InkEffects.apply_gel_pen_effect),
        ("pencil", InkEffects.apply_pencil_effect),
        ("felt_tip", InkEffects.apply_felt_tip_effect),
    ]
    
    for name, effect_func in effects:
        result = effect_func(test_img)
        result.save(f"output/ink_effects/{name}.png")
        print(f"✅ Saved {name}")
    
    print("\n✅ Ink effects tested!")


if __name__ == "__main__":
    test_ink_effects()
