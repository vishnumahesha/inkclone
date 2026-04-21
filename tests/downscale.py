#!/usr/bin/env python3
"""Downscale an image to ≤1500px on longest side, in-place."""
import sys
from PIL import Image

path = sys.argv[1]
img = Image.open(path)
w, h = img.size
max_dim = 1500
if max(w, h) > max_dim:
    scale = max_dim / max(w, h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img.save(path)
    print(f"Downscaled {path}: {w}x{h} → {img.size}")
else:
    print(f"OK {path}: {w}x{h}")
