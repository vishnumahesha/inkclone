# InkClone

Convert your handwriting into a digital font. Upload photos of a filled template, extract character glyphs, and render any text in your handwriting.

## What It Does

InkClone transforms handwritten samples into reusable digital fonts. Fill out a template with your handwriting, scan or photograph it, and the tool extracts each character as a glyph. You can then render any text using your personal handwriting style.

## Tech Stack

- **Backend:** Python, FastAPI
- **Image Processing:** OpenCV
- **Deployment:** Railway

## Features

- Template-based character extraction
- Glyph isolation and preprocessing
- Text rendering in custom handwriting
- Support for multiple character variants
- Realistic spacing and kerning

## Live Demo

https://inkclone-production.up.railway.app

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Generate a template
python generate_template.py

# Extract glyphs from filled template
python extract_v6.py

# Render text with your handwriting
python cli.py render "Your text here"
```

## How It Works

1. **Template generation** - Creates a PDF grid with characters to fill in
2. **Character extraction** - Isolates each handwritten character from the scanned template
3. **Glyph processing** - Cleans, normalizes, and stores character images
4. **Text rendering** - Composes glyphs into natural-looking handwritten text
