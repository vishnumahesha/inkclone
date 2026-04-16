"""
Coverage test runner - generates fallbacks and renders test image.
Run from ~/Projects/inkclone: python coverage_test_runner.py
"""
import sys
import os
from pathlib import Path

# Ensure we're in the right directory
script_dir = Path(__file__).parent
os.chdir(script_dir)

print("=== Step 1: Generate fallback glyphs ===")
from glyph_loader import generate_fallback_glyphs
generate_fallback_glyphs(Path('profiles/freeform_vishnu'))

print("\n=== Step 2: Render coverage test ===")
from glyph_loader import load_profile_glyphs
from render_engine import HandwritingRenderer
from paper_backgrounds import generate_college_ruled
from compositor import composite, INK_COLORS

Path('output').mkdir(exist_ok=True)

bank = load_profile_glyphs(Path('profiles/freeform_vishnu'))
renderer = HandwritingRenderer(bank, seed=42)
text_img = renderer.render(
    "Hello World! On July 4, 1776, the 13 colonies said: 'We are FREE.'",
    neatness=0.7
)
paper = generate_college_ruled()
result = composite(text_img, paper, ink_color=INK_COLORS['black'])
result.save('output/coverage_test.png')
size_bytes = os.path.getsize('output/coverage_test.png')
size_kb = size_bytes // 1024
print(f"Saved: {result.size}, {result.mode}")
print(f"File size: {size_kb}KB ({size_bytes} bytes)")

status = "PASS" if size_kb > 100 else "FAIL"
if size_kb > 100:
    print(f"PASS: {size_kb}KB > 100KB")
else:
    print(f"FAIL: {size_kb}KB <= 100KB")

# Append to DISPATCH_PROGRESS.md
progress_file = Path('DISPATCH_PROGRESS.md')
if progress_file.exists():
    content = progress_file.read_text()
    # Replace PENDING with actual values
    content = content.replace('[PENDING]KB', f'{size_kb}KB')
    content = content.replace('[PENDING]', status)
    progress_file.write_text(content)
    print(f"Updated DISPATCH_PROGRESS.md with {size_kb}KB {status}")

print("\nAll done!")
