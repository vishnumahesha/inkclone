import pytest
import os
import numpy as np
from PIL import Image

def test_paper_blank():
    from paper_backgrounds import generate_blank_paper
    img = generate_blank_paper()
    assert img.size == (2400, 3200)
    assert img.mode == "RGB"
    arr = np.array(img)
    assert arr.mean() > 200, "Blank paper should be mostly white"

def test_paper_college_ruled():
    from paper_backgrounds import generate_college_ruled
    img = generate_college_ruled()
    assert img.size == (2400, 3200)
    arr = np.array(img)
    assert arr.std() > 2.0, "Ruled paper should have visible lines"

def test_paper_legal():
    from paper_backgrounds import generate_legal_pad
    img = generate_legal_pad()
    arr = np.array(img)
    assert arr[:,:,0].mean() > arr[:,:,2].mean() + 15, "Legal pad should be yellow"

def test_renderer_basic():
    from render_engine import HandwritingRenderer, create_dummy_glyph_bank
    bank = create_dummy_glyph_bank()
    renderer = HandwritingRenderer(bank, seed=42)
    img = renderer.render("hello world")
    assert img.mode == "RGBA"
    alpha = np.array(img)[:,:,3]
    assert alpha.sum() > 0, "Should render some ink"

def test_renderer_long_text():
    from render_engine import HandwritingRenderer, create_dummy_glyph_bank
    bank = create_dummy_glyph_bank()
    renderer = HandwritingRenderer(bank, seed=42)
    text = "The quick brown fox. " * 30
    img = renderer.render(text)
    alpha = np.array(img)[:,:,3]
    assert (alpha > 0).sum() > 10000, "Long text should have many ink pixels"

def test_renderer_neatness():
    from render_engine import HandwritingRenderer, create_dummy_glyph_bank
    bank = create_dummy_glyph_bank()
    r1 = HandwritingRenderer(bank, seed=42)
    r2 = HandwritingRenderer(bank, seed=42)
    img_neat = r1.render("test text", neatness=1.0)
    img_messy = r2.render("test text", neatness=0.0)
    # Both should render successfully
    assert np.array(img_neat)[:,:,3].sum() > 0
    assert np.array(img_messy)[:,:,3].sum() > 0

def test_compositor():
    from render_engine import HandwritingRenderer, create_dummy_glyph_bank
    from paper_backgrounds import generate_blank_paper
    from compositor import composite
    bank = create_dummy_glyph_bank()
    renderer = HandwritingRenderer(bank, seed=42)
    text_img = renderer.render("hello")
    paper = generate_blank_paper()
    result = composite(text_img, paper, ink_color=(0, 0, 0))
    assert result.mode == "RGB"
    assert result.size == paper.size

def test_artifact_scan():
    from artifact_simulator import simulate_scan
    img = Image.new('RGB', (800, 600), (250, 250, 250))
    result = simulate_scan(img)
    assert result.mode == "RGB"
    assert result.size[0] > 0

def test_artifact_phone():
    from artifact_simulator import simulate_phone_photo
    img = Image.new('RGB', (800, 600), (250, 250, 250))
    result = simulate_phone_photo(img)
    assert result.mode == "RGB"

def test_full_pipeline():
    """End-to-end test: text -> render -> composite -> artifact"""
    from render_engine import HandwritingRenderer, create_dummy_glyph_bank
    from paper_backgrounds import generate_college_ruled
    from compositor import composite, INK_COLORS
    from artifact_simulator import simulate_scan

    bank = create_dummy_glyph_bank()
    renderer = HandwritingRenderer(bank, seed=42)
    text_img = renderer.render("Full pipeline test sentence here.")
    paper = generate_college_ruled()
    comp = composite(text_img, paper, ink_color=INK_COLORS["black"])
    final = simulate_scan(comp)

    assert final.mode == "RGB"
    assert final.size == (2400, 3200)
    final.save("output/test_full_pipeline.png")
    assert os.path.exists("output/test_full_pipeline.png")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
