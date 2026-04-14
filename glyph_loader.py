"""
Glyph Bank Loader

Loads real glyphs from extracted images or falls back to dummy glyphs.
Provides seamless integration between dummy and real glyph banks.
"""

import json
from pathlib import Path
from PIL import Image
from render_engine import create_dummy_glyph_bank

class GlyphLoader:
    """Loads glyph banks - real or dummy."""
    
    def __init__(self, real_glyphs_dir="real_glyphs"):
        self.real_glyphs_dir = Path(real_glyphs_dir)
        self.bank = None
        self.glyph_type = None
    
    def load_real_glyphs(self):
        """Load real extracted glyphs."""
        json_path = self.real_glyphs_dir / "glyph_bank.json"
        
        if not json_path.exists():
            print(f"⚠️  {json_path} not found")
            return None
        
        try:
            with open(json_path, 'r') as f:
                glyph_map = json.load(f)
            
            bank = {}
            for char, paths in glyph_map.items():
                bank[char] = []
                for path in paths:
                    try:
                        img = Image.open(path).convert('RGBA')
                        bank[char].append(img)
                    except Exception as e:
                        print(f"⚠️  Failed to load {path}: {e}")
            
            print(f"✅ Loaded {len(bank)} characters from real glyphs")
            self.bank = bank
            self.glyph_type = "real"
            return bank
        
        except Exception as e:
            print(f"⚠️  Error loading real glyphs: {e}")
            return None
    
    def load_dummy_glyphs(self):
        """Load dummy placeholder glyphs."""
        print("⚠️  Using dummy placeholder glyphs (rectangles)")
        self.bank = create_dummy_glyph_bank()
        self.glyph_type = "dummy"
        return self.bank
    
    def load_best_available(self):
        """Load best available glyph bank (real → dummy)."""
        # Try real glyphs first
        real = self.load_real_glyphs()
        if real:
            return real
        
        # Fall back to dummy
        print("Falling back to dummy glyphs...")
        return self.load_dummy_glyphs()
    
    def get_info(self):
        """Get information about loaded glyph bank."""
        if not self.bank:
            return "No glyph bank loaded"
        
        total_variants = sum(len(v) for v in self.bank.values())
        return {
            'type': self.glyph_type,
            'characters': len(self.bank),
            'total_variants': total_variants,
            'characters_list': sorted(self.bank.keys())
        }
    
    def has_real_glyphs(self):
        """Check if real glyphs are available."""
        json_path = self.real_glyphs_dir / "glyph_bank.json"
        return json_path.exists()


def load_glyphs(prefer_real=True):
    """
    Convenience function to load glyphs.
    
    Args:
        prefer_real: If True, try real glyphs first; fallback to dummy
    
    Returns:
        Glyph bank dictionary
    """
    loader = GlyphLoader()
    
    if prefer_real:
        return loader.load_best_available()
    else:
        return loader.load_dummy_glyphs()


if __name__ == "__main__":
    # Test loader
    print("╔════════════════════════════════════╗")
    print("║       GLYPH BANK LOADER TEST       ║")
    print("╚════════════════════════════════════╝")
    
    loader = GlyphLoader()
    
    # Check what's available
    print(f"\n📊 Real glyphs available: {loader.has_real_glyphs()}")
    
    # Load best available
    print("\n[1/3] Loading glyphs...")
    bank = loader.load_best_available()
    
    # Get info
    print("\n[2/3] Glyph bank info:")
    info = loader.get_info()
    for key, value in info.items():
        if key != 'characters_list':
            print(f"  {key}: {value}")
    
    # Show character coverage
    print(f"\n[3/3] Character coverage:")
    print(f"  Lowercase: {sum(1 for c in info['characters_list'] if c.islower())}")
    print(f"  Uppercase: {sum(1 for c in info['characters_list'] if c.isupper())}")
    print(f"  Digits: {sum(1 for c in info['characters_list'] if c.isdigit())}")
    print(f"  Punctuation: {sum(1 for c in info['characters_list'] if not c.isalnum())}")
    
    print("\n✅ Loader ready!")
