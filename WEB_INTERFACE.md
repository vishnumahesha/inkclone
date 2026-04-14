# InkClone Web Interface — Quick Start

## Start the Server

```bash
cd ~/Projects/inkclone
source venv/bin/activate
python3 web/app.py
```

**Output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

## Access the Interface

Open browser to: **http://127.0.0.1:8000**

## Features

✅ Type text in textarea  
✅ Select paper type (5 options)  
✅ Select ink color (6 options)  
✅ Choose artifact effect (scan, phone, clean)  
✅ Adjust neatness (0 = messy, 1 = neat)  
✅ Click "Generate Document"  
✅ View preview immediately (3-5 seconds)  

## Web Interface Architecture

### Frontend
- Single HTML file (embedded in FastAPI response)
- Inline CSS (responsive design)
- Vanilla JavaScript (no frameworks)
- Real-time error handling
- Base64 image display

### Backend
- FastAPI web framework
- Python image processing
- 2 endpoints: GET / (HTML), POST /generate (API)
- Generates PNG images on request
- Returns base64-encoded images

### Pipeline
```
User Input
    ↓
[FastAPI] → POST /generate
    ↓
[Render Pipeline]
  - render_engine (text → RGBA)
  - paper_backgrounds (paper texture)
  - compositor (text + paper)
  - artifact_simulator (scan/phone effects)
    ↓
[Response] → Base64 image
    ↓
[Frontend] → Display in browser
```

## API Usage

### GET / (HTML Interface)
```bash
curl http://127.0.0.1:8000/
# Returns: Complete HTML page with CSS and JavaScript
```

### POST /generate (Document Generator)
```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "paper": "college_ruled",
    "ink": "blue",
    "artifact": "scan",
    "neatness": 0.5
  }'
```

**Response:**
```json
{
  "success": true,
  "image": "data:image/png;base64,iVBORw0KGgo...",
  "width": 2400,
  "height": 3200,
  "paper": "college_ruled",
  "ink": "blue",
  "artifact": "scan",
  "neatness": 0.5
}
```

## Configuration

### Change Port
Edit `web/app.py` line 260:
```python
uvicorn.run(app, host="127.0.0.1", port=8000)  # Change 8000 to your port
```

### Allow Remote Access
Edit `web/app.py` line 260:
```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # 0.0.0.0 instead of 127.0.0.1
```

### Production Deployment
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 --timeout 30 web.app:app
```

## Parameters

### text (required)
The text to render as handwriting
- Max: ~500 characters per page
- Special characters supported

### paper (default: college_ruled)
Paper background type
- `blank` — White paper
- `college_ruled` — Standard ruled (7.1mm)
- `wide_ruled` — Wider spacing (8.7mm)
- `graph` — Grid paper
- `legal_pad` — Yellow legal pad

### ink (default: black)
Ink color
- `black` — Black ink
- `blue` — Blue ballpoint
- `dark_blue` — Dark blue
- `green` — Green ink
- `red` — Red ink
- `pencil` — Pencil gray

### artifact (default: scan)
Simulation effect
- `clean` — No effects (digital appearance)
- `scan` — Flatbed scanner (realistic)
- `phone` — Phone camera (natural looking)

### neatness (default: 0.5)
Handwriting style (0.0-1.0)
- `0.0` — Very messy/cursive
- `0.5` — Natural/average
- `1.0` — Very neat/clean

### seed (optional)
Random seed for reproducible output
- Same seed = identical result
- Default: Random seed each time

## Test Examples

### Example 1: Simple Letter
```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Dear friend, how are you?",
    "paper": "blank",
    "ink": "black",
    "artifact": "clean"
  }'
```

### Example 2: Formal Document
```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The quick brown fox jumps over the lazy dog",
    "paper": "college_ruled",
    "ink": "blue",
    "artifact": "scan",
    "neatness": 0.8
  }'
```

### Example 3: Messy Notes
```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Quick thoughts and ideas",
    "paper": "legal_pad",
    "ink": "pencil",
    "artifact": "phone",
    "neatness": 0.2
  }'
```

## Performance

- **First request**: 5-7 seconds (module loading)
- **Subsequent requests**: 3-5 seconds
- **Image size**: ~400 KB (base64 in response)

## Troubleshooting

### "Port already in use"
```bash
lsof -i :8000
kill -9 <PID>
```

### "Module not found"
```bash
cd ~/Projects/inkclone
source venv/bin/activate
python3 web/app.py
```

### "ModuleNotFoundError: No module named 'fastapi'"
```bash
pip install fastapi uvicorn
```

### Image not showing
- Check browser console for errors (F12)
- Verify API response has `"success": true`
- Try simpler text first

### Server crashes
- Check error log (first 50 lines printed on startup)
- Reduce text length
- Try `artifact: "clean"` (faster)

## Browser Compatibility

✅ Chrome/Edge (Chromium 90+)  
✅ Firefox (88+)  
✅ Safari (14+)  
✅ Mobile browsers (iOS Safari, Chrome)  

## Files

- `web/app.py` — FastAPI server (single file, 400+ lines)
- `web/README.md` — Detailed documentation
- All other modules in parent directory

## Next Steps

### For Development
1. Modify `get_html_page()` in `web/app.py` to customize UI
2. Add new paper types or effects in respective modules
3. Test API with curl or Postman

### For Production
1. Use Gunicorn or similar WSGI server
2. Configure CORS if needed (`pip install fastapi-cors`)
3. Add authentication if needed (JWT, OAuth2)
4. Set up SSL/TLS (nginx with cert)

### For Deployment
1. Docker container (see `web/README.md`)
2. Cloud platform (Heroku, AWS, GCP)
3. Local machine with systemd service

## Support

See `web/README.md` for detailed API documentation and customization guide.

---

**InkClone Web Interface** — Running on http://127.0.0.1:8000 🎨
