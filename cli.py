#!/usr/bin/env python3
"""
InkClone CLI — Unified handwriting replication system
Integrates glyph capture and document rendering into one product
"""

import sys
import os
import argparse
from pathlib import Path

# Import render pipeline modules
try:
    from paper_backgrounds import (generate_blank_paper, generate_college_ruled,
                                   generate_wide_ruled, generate_graph_paper, generate_legal_pad)
    from render_engine import HandwritingRenderer, create_dummy_glyph_bank
    from glyph_loader import load_glyphs
    from compositor import composite, INK_COLORS
    from artifact_simulator import simulate_scan, simulate_phone_photo, simulate_clean
except ImportError as e:
    print(f"Error importing render modules: {e}")
    print("Make sure all modules are in the same directory as cli.py")
    sys.exit(1)

# Import capture pipeline modules
try:
    from generate_template import generate_template
    from preprocess import preprocess_image
    from segment import segment_glyphs
except ImportError as e:
    print(f"Note: Capture modules not fully configured: {e}")
    print("Some commands may be limited")


class InkCloneCLI:
    """Main CLI interface for InkClone"""

    def __init__(self):
        self.glyph_bank = None
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)

    def cmd_template(self, args):
        """Generate a blank template PDF for capturing handwriting samples"""
        print("=" * 60)
        print("InkClone Template Generator")
        print("=" * 60)

        try:
            # Generate template (from capture pipeline)
            template_path = generate_template(
                output_path=str(self.output_dir / "template.pdf"),
                num_cells=args.num_cells,
                paper_type=args.paper_type
            )
            print(f"\n✅ Template generated: {template_path}")
            print(f"   Print this PDF and fill in your handwriting samples")
            print(f"   Then use: python3 cli.py create-profile <photo.jpg>")

        except Exception as e:
            print(f"❌ Error generating template: {e}")
            return 1

        return 0

    def cmd_create_profile(self, args):
        """Extract glyphs from a template photo to create handwriting profile"""
        print("=" * 60)
        print("InkClone Profile Creator")
        print("=" * 60)

        if not os.path.exists(args.photo):
            print(f"❌ Photo not found: {args.photo}")
            return 1

        try:
            # Preprocess the image
            print(f"\n[1/3] Preprocessing image...")
            preprocessed = preprocess_image(args.photo)
            print(f"✅ Image preprocessed")

            # Segment into glyphs
            print(f"[2/3] Segmenting glyphs...")
            glyphs = segment_glyphs(preprocessed)
            print(f"✅ Extracted {len(glyphs)} glyphs")

            # Save profile
            profile_path = self.output_dir / "profile.pkl"
            import pickle
            with open(profile_path, 'wb') as f:
                pickle.dump(glyphs, f)
            print(f"[3/3] Saving profile...")
            print(f"✅ Profile saved: {profile_path}")
            print(f"   Use this profile with: python3 cli.py generate")

            self.glyph_bank = glyphs
            return 0

        except Exception as e:
            print(f"❌ Error creating profile: {e}")
            import traceback
            traceback.print_exc()
            return 1

    def cmd_generate(self, args):
        """Generate a handwritten document from text"""
        print("=" * 60)
        print("InkClone Document Generator")
        print("=" * 60)

        if not args.text:
            print("❌ No text provided. Use: python3 cli.py generate 'your text here'")
            return 1

        # Load or create glyph bank
        if self.glyph_bank is None:
            # Try to load real glyphs first
            print(f"Loading glyph bank...")
            self.glyph_bank = load_glyphs(prefer_real=True)
            if self.glyph_bank is None:
                print("❌ Failed to load any glyphs")
                return 1

        try:
            print(f"\n[1/5] Rendering text...")
            renderer = HandwritingRenderer(self.glyph_bank, seed=args.seed)
            text_img = renderer.render(args.text, neatness=args.neatness)
            print(f"✅ Text rendered")

            print(f"[2/5] Generating {args.paper} paper...")
            papers = {
                "blank": generate_blank_paper,
                "college_ruled": generate_college_ruled,
                "wide_ruled": generate_wide_ruled,
                "graph": generate_graph_paper,
                "legal_pad": generate_legal_pad,
            }

            if args.paper not in papers:
                print(f"❌ Unknown paper type: {args.paper}")
                print(f"   Available: {', '.join(papers.keys())}")
                return 1

            paper = papers[args.paper]()
            print(f"✅ Paper generated")

            print(f"[3/5] Compositing...")
            if args.ink not in INK_COLORS:
                print(f"❌ Unknown ink color: {args.ink}")
                print(f"   Available: {', '.join(INK_COLORS.keys())}")
                return 1

            result = composite(text_img, paper, ink_color=INK_COLORS[args.ink],
                             opacity=args.opacity)
            print(f"✅ Composite created")

            print(f"[4/5] Applying {args.artifact} artifact simulation...")
            artifacts = {
                "clean": simulate_clean,
                "scan": simulate_scan,
                "phone": simulate_phone_photo,
            }

            if args.artifact not in artifacts:
                print(f"❌ Unknown artifact type: {args.artifact}")
                print(f"   Available: {', '.join(artifacts.keys())}")
                return 1

            final = artifacts[args.artifact](result)
            print(f"✅ Artifacts applied")

            print(f"[5/5] Saving output...")
            output_file = self.output_dir / f"document_{args.paper}_{args.ink}_{args.artifact}.png"
            final.save(output_file)
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            print(f"✅ Document saved: {output_file}")
            print(f"   Size: {size_mb:.2f} MB")
            print(f"   Paper: {args.paper}")
            print(f"   Ink: {args.ink}")
            print(f"   Artifact: {args.artifact}")
            print(f"   Neatness: {args.neatness}")

            return 0

        except Exception as e:
            print(f"❌ Error generating document: {e}")
            import traceback
            traceback.print_exc()
            return 1

    def cmd_test(self, args):
        """Run all tests"""
        print("=" * 60)
        print("InkClone Test Suite")
        print("=" * 60)

        try:
            import subprocess
            result = subprocess.run([sys.executable, "-m", "pytest", "test_all.py", "-v"],
                                  cwd=os.path.dirname(__file__))
            return result.returncode
        except Exception as e:
            print(f"❌ Error running tests: {e}")
            return 1

    def cmd_info(self, args):
        """Show project information"""
        print("=" * 60)
        print("InkClone — Handwriting Replication System")
        print("=" * 60)

        print("""
Commands:
  template              Generate a blank template PDF for handwriting samples
  create-profile FILE   Extract glyphs from a template photo
  generate TEXT         Generate a handwritten document from text
  test                  Run all tests
  info                  Show this information

Examples:
  python3 cli.py template --paper college_ruled
  python3 cli.py create-profile filled_template.jpg
  python3 cli.py generate 'Hello world' --paper blank --ink blue --artifact scan
  python3 cli.py test

Paper Types:
  blank, college_ruled, wide_ruled, graph, legal_pad

Ink Colors:
  black, blue, dark_blue, green, red, pencil

Artifact Simulations:
  clean (no artifacts)
  scan (flatbed scanner simulation)
  phone (phone camera simulation)

For help with a specific command:
  python3 cli.py <command> --help
        """)
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="InkClone — Unified handwriting replication system",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Template command
    template_parser = subparsers.add_parser('template', help='Generate template PDF')
    template_parser.add_argument('--num-cells', type=int, default=26, help='Number of character cells')
    template_parser.add_argument('--paper-type', default='college_ruled', help='Paper type')

    # Create profile command
    profile_parser = subparsers.add_parser('create-profile', help='Extract glyphs from photo')
    profile_parser.add_argument('photo', help='Path to template photo')

    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate handwritten document')
    generate_parser.add_argument('text', help='Text to render')
    generate_parser.add_argument('--paper', default='college_ruled',
                               choices=['blank', 'college_ruled', 'wide_ruled', 'graph', 'legal_pad'],
                               help='Paper type')
    generate_parser.add_argument('--ink', default='black',
                               choices=['black', 'blue', 'dark_blue', 'green', 'red', 'pencil'],
                               help='Ink color')
    generate_parser.add_argument('--artifact', default='scan',
                               choices=['clean', 'scan', 'phone'],
                               help='Artifact simulation')
    generate_parser.add_argument('--neatness', type=float, default=0.5,
                               help='Neatness level (0=messy, 1=neat)')
    generate_parser.add_argument('--opacity', type=float, default=1.0,
                               help='Ink opacity (0=transparent, 1=opaque)')
    generate_parser.add_argument('--seed', type=int, default=None,
                               help='Random seed for reproducibility')

    # Test command
    test_parser = subparsers.add_parser('test', help='Run test suite')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show information')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cli = InkCloneCLI()

    # Route to appropriate command
    if args.command == 'template':
        return cli.cmd_template(args)
    elif args.command == 'create-profile':
        return cli.cmd_create_profile(args)
    elif args.command == 'generate':
        return cli.cmd_generate(args)
    elif args.command == 'test':
        return cli.cmd_test(args)
    elif args.command == 'info':
        return cli.cmd_info(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
