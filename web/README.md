# InkClone Web Interface

Simple web interface for the InkClone handwriting document generator.

## Features

- 🎨 Real-time document preview
- 📄 Multiple paper types (5 options)
- 🖌️ Multiple ink colors (6 options)
- 📸 Artifact simulations (scan, phone, clean)
- 🎚️ Neatness control (0.0 = messy, 1.0 = neat)
- ⚡ Fast generation (3-5 seconds per document)
- 📱 Responsive design (mobile-friendly)

## Architecture

### Frontend
- Single HTML file with inline CSS and JavaScript
- No build tools, no dependencies
- Responsive grid layout
- Real-time error handling

### Backend
- FastAPI web framework
- Python image processing pipeline
- RESTful API design
- Base64 image encoding for display

## Getting Started

### Prerequisites
```bash
cd ~/Projects/inkclone
pip install -r requirements.txt  # Installs FastAPI, Uvicorn, Pillow, etc.
```

### Start Server
```bash
cd ~/Projects/inkclone
source venv/bin/activate
python3 web/app.py
```

Server runs on `http://127.0.0.1:8000`

### Usage
1. Open browser to `http://127.0.0.1:8000`
2. Type text in textarea
3. Select paper type (college ruled, blank, graph, etc.)
4. Select ink color (black, blue, green, etc.)
5. Choose effect (scan, phone photo, clean)
6. Adjust neatness slider (0 = messy, 1 = neat)
7. Click "Generate Document"
8. View preview immediately

## API Endpoints

### GET /
Returns the HTML interface page.

**Example:**
```bash
curl http://127.0.0.1:8000/
```

### POST /generate
Generates a handwritten document.

**Request:**
```json
{
  "text": "Your text here",
  "paper": "college_ruled",
  "ink": "blue",
  "artifact": "scan",
  "neatness": 0.5,
  "seed": null
}
```

**Response:**
```json
{
  "success": true,
  "image": "data:image/png;base64,iVBORw0KGgoAAAANS...",
  "width": 2400,
  "height": 3200,
  "paper": "college_ruled",
  "ink": "blue",
  "artifact": "scan",
  "neatness": 0.5
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "paper": "blank",
    "ink": "black",
    "artifact": "clean"
  }'
```

## Paper Types

- **Blank** — Clean white paper with subtle texture
- **College Ruled** — Standard ruled notebook (7.1mm spacing)
- **Wide Ruled** — Wider spacing (8.7mm)
- **Graph** — Grid paper (30px spacing)
- **Legal Pad** — Yellow legal pad

## Ink Colors

- **Black** — Classic black ink
- **Blue** — Ballpoint blue
- **Dark Blue** — Darker blue
- **Green** — Green ink
- **Red** — Red ink
- **Pencil** — Gray pencil

## Artifact Simulations

- **Clean** — Digital appearance, no artifacts
- **Scan** — Flatbed scanner simulation (rotation, contrast, sharpening)
- **Phone** — Mobile camera simulation (perspective, noise, vignetting)

## Configuration

### Port
Change port in `web/app.py`:
```python
uvicorn.run(app, host="127.0.0.1", port=8000)  # Change 8000 to desired port
```

### Host
Allow external connections:
```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # Accessible from other machines
```

## Performance

- **Paper generation**: ~550ms
- **Text rendering**: 1-2s
- **Compositing**: 100-200ms
- **Artifact simulation**: 500-2000ms (depends on effect)
- **Total**: 3-5 seconds per document

## Files

- `app.py` — FastAPI backend (single file)
- Frontend is embedded in HTML served from `GET /`
- All page styling and interaction in inline CSS/JavaScript
- No external dependencies beyond FastAPI

## Customization

### Add New Paper Type
1. Add generator function to `paper_backgrounds.py`
2. Add to `PAPERS` dict in `app.py`
3. Update HTML dropdown (in `get_html_page()`)

### Add New Ink Color
1. Add to `INK_COLORS` dict in `compositor.py`
2. Update HTML dropdown (in `get_html_page()`)

### Modify UI
Edit the HTML in `get_html_page()` function in `app.py`:
- CSS styling in `<style>` tag
- Form controls in `<form>` tag
- JavaScript interactions in `<script>` tag

## Troubleshooting

### Port 8000 already in use
```bash
lsof -i :8000  # Find process using port
kill -9 <PID>  # Kill process
```

### Import errors
```bash
cd ~/Projects/inkclone
source venv/bin/activate
pip install -r requirements.txt
```

### Server crashes
```bash
tail -f /tmp/inkclone_web.log  # View server logs
```

### Slow image generation
- Reduce `neatness` (simpler, faster)
- Use `clean` artifact (no scan/phone effects)
- Shorter text (less rendering)

## Development

### File Structure
```
~/Projects/inkclone/
├── web/
│   ├── app.py          ← FastAPI server (start here)
│   └── README.md       ← This file
├── paper_backgrounds.py
├── render_engine.py
├── compositor.py
├── artifact_simulator.py
└── ... (other modules)
```

### Adding Features
1. Keep frontend in single HTML for simplicity
2. Add POST endpoints as needed
3. Use JSON for request/response
4. Return images as base64 data URLs

### Testing API
```bash
# Test endpoint
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "paper": "blank", "ink": "black"}'

# Pretty-print response
curl ... | python3 -m json.tool
```

## Deployment

### Local (Development)
```bash
python3 web/app.py
# Runs on http://127.0.0.1:8000
```

### Production (Gunicorn)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 --timeout 30 web.app:app
```

### Docker
Create `Dockerfile`:
```dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python3", "web/app.py"]
```

## Limitations

- Current: Uses dummy glyphs (placeholder rectangles)
- Not realistic until real handwriting glyphs extracted
- No multi-threaded processing (one request at a time)
- Base64 encoding adds ~30% size overhead

## License

Proprietary — Part of InkClone system

---

**InkClone Web Interface** — Transform text into handwritten documents 🎨
