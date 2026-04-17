"""
InkClone Render Pipeline — Full Demo
Generates handwritten document images from typed text.
"""

from render_engine import HandwritingRenderer, create_dummy_glyph_bank
from paper_backgrounds import (generate_blank_paper, generate_college_ruled,
                               generate_wide_ruled, generate_graph_paper, generate_legal_pad)
from compositor import composite, INK_COLORS
from artifact_simulator import simulate_scan, simulate_phone_photo, simulate_clean
import os

def run_demo():
    print("=" * 60)
    print("InkClone Render Pipeline — Full Demo")
    print("=" * 60)

    # Step 1: Create glyph bank (using dummy glyphs for now)
    print("\n[1/5] Creating glyph bank...")
    bank = create_dummy_glyph_bank()
    print(f"✅ Glyph bank: {len(bank)} characters")

    # Step 2: Render text
    print("\n[2/5] Rendering text...")
    renderer = HandwritingRenderer(bank, seed=42)

    text = """The quick brown fox jumps over the lazy dog. Pack my box with five dozen jugs of liquid soap. She explained that nothing was impossible if you worked hard enough. The history of the American west was shaped by expansion and conflict. After the attack on Pearl Harbor the United States fully entered the war and quickly turned its economy into a wartime economy. Factories switched from making consumer goods to producing tanks planes ships and weapons. The government encouraged support through war bonds propaganda and scrap drives. Women entered the workforce in huge numbers especially in defense industries showing that they could do jobs that had usually been given to men."""

    text_img = renderer.render(text, neatness=0.5)
    text_img.save("output/demo_01_rendered_text.png")
    print(f"✅ Rendered: {text_img.size}")

    # Step 3: Generate backgrounds
    print("\n[3/5] Generating paper backgrounds...")
    papers = {
        "blank": generate_blank_paper(),
        "college_ruled": generate_college_ruled(),
        "legal_pad": generate_legal_pad(),
    }
    print(f"✅ Generated {len(papers)} paper types")

    # Step 4: Composite
    print("\n[4/5] Compositing...")
    composites = {}
    for paper_name, paper_img in papers.items():
        for ink_name in ["black", "blue"]:
            key = f"{paper_name}_{ink_name}"
            comp = composite(text_img, paper_img, ink_color=INK_COLORS[ink_name])
            comp.save(f"output/demo_02_{key}.png")
            composites[key] = comp
            print(f"✅ {key}: saved")

    # Step 5: Apply artifacts
    print("\n[5/5] Applying artifact simulation...")

    # Pick the college ruled + black ink as the main example
    main_composite = composites["college_ruled_black"]

    scan = simulate_scan(main_composite)
    scan.save("output/demo_03_scan.png")
    print("✅ Scan simulation: saved")

    photo = simulate_phone_photo(main_composite)
    photo.save("output/demo_03_phone_photo.png")
    print("✅ Phone photo simulation: saved")

    clean = simulate_clean(main_composite)
    clean.save("output/demo_03_clean.png")
    print("✅ Clean render: saved")

    # Also do legal pad with blue ink + scan
    legal_blue = composites["legal_pad_blue"]
    legal_scan = simulate_scan(legal_blue)
    legal_scan.save("output/demo_04_legal_pad_blue_scan.png")
    print("✅ Legal pad blue scan: saved")

    # Summary
    print("\n" + "=" * 60)
    output_files = [f for f in os.listdir("output") if f.startswith("demo_")]
    print(f"Generated {len(output_files)} demo files in output/:")
    for f in sorted(output_files):
        size = os.path.getsize(f"output/{f}")
        print(f"  {f} ({size:,} bytes)")
    print("=" * 60)
    print("\nDEMO COMPLETE. Check output/ folder for results.")
    print("Note: Using dummy rectangle glyphs. Replace with real")
    print("extracted handwriting glyphs for realistic output.")


if __name__ == "__main__":
    run_demo()
