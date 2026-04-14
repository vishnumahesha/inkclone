"""
InkClone Web Interface Backend
FastAPI server for handwriting document generation
"""

import sys
import os
from pathlib import Path
from io import BytesIO
import base64
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Add parent directory to path to import inkclone modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from render_engine import HandwritingRenderer, create_dummy_glyph_bank
from paper_backgrounds import (generate_blank_paper, generate_college_ruled,
                               generate_wide_ruled, generate_graph_paper, generate_legal_pad)
from compositor import composite, INK_COLORS
from artifact_simulator import simulate_scan, simulate_phone_photo, simulate_clean

# Create FastAPI app
app = FastAPI(title="InkClone", description="Handwriting document generator")

# Initialize glyph bank
GLYPH_BANK = create_dummy_glyph_bank()

# Paper and artifact mappings
PAPERS = {
    "blank": generate_blank_paper,
    "college_ruled": generate_college_ruled,
    "wide_ruled": generate_wide_ruled,
    "graph": generate_graph_paper,
    "legal_pad": generate_legal_pad,
}

ARTIFACTS = {
    "clean": simulate_clean,
    "scan": simulate_scan,
    "phone": simulate_phone_photo,
}

class GenerateRequest(BaseModel):
    text: str
    paper: str = "college_ruled"
    ink: str = "black"
    artifact: str = "scan"
    neatness: float = 0.5
    seed: int = None

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main HTML interface"""
    return get_html_page()

@app.post("/generate")
async def generate_document(request: GenerateRequest):
    """Generate a handwritten document"""
    try:
        # Validate inputs
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        if request.paper not in PAPERS:
            raise HTTPException(status_code=400, detail=f"Invalid paper type: {request.paper}")
        
        if request.ink not in INK_COLORS:
            raise HTTPException(status_code=400, detail=f"Invalid ink color: {request.ink}")
        
        if request.artifact not in ARTIFACTS:
            raise HTTPException(status_code=400, detail=f"Invalid artifact type: {request.artifact}")
        
        if not 0.0 <= request.neatness <= 1.0:
            raise HTTPException(status_code=400, detail="Neatness must be between 0.0 and 1.0")
        
        # Step 1: Render text
        renderer = HandwritingRenderer(GLYPH_BANK, seed=request.seed)
        text_img = renderer.render(request.text, neatness=request.neatness)
        
        # Step 2: Generate paper
        paper = PAPERS[request.paper]()
        
        # Step 3: Composite
        result = composite(text_img, paper, ink_color=INK_COLORS[request.ink])
        
        # Step 4: Apply artifact simulation
        final = ARTIFACTS[request.artifact](result)
        
        # Step 5: Convert to base64 for response
        img_buffer = BytesIO()
        final.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        
        return JSONResponse({
            "success": True,
            "image": f"data:image/png;base64,{img_base64}",
            "width": final.width,
            "height": final.height,
            "paper": request.paper,
            "ink": request.ink,
            "artifact": request.artifact,
            "neatness": request.neatness,
        })
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating document: {str(e)}")

def get_html_page():
    """Return the HTML interface"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InkClone — Handwriting Document Generator</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            max-width: 1400px;
            width: 100%;
        }
        
        @media (max-width: 1000px) {
            .container {
                grid-template-columns: 1fr;
            }
        }
        
        .panel {
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }
        
        .panel h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        
        .panel .subtitle {
            color: #666;
            margin-bottom: 25px;
            font-size: 14px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            color: #333;
            font-weight: 600;
            margin-bottom: 8px;
            font-size: 14px;
        }
        
        textarea {
            width: 100%;
            min-height: 120px;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 14px;
            resize: vertical;
            transition: border-color 0.3s;
        }
        
        textarea:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        select {
            width: 100%;
            padding: 10px 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            background: white;
            cursor: pointer;
            transition: border-color 0.3s;
        }
        
        select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        
        .slider-group {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        input[type="range"] {
            flex: 1;
            height: 6px;
            border-radius: 3px;
            background: #ddd;
            outline: none;
            -webkit-appearance: none;
        }
        
        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #667eea;
            cursor: pointer;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        }
        
        input[type="range"]::-moz-range-thumb {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #667eea;
            cursor: pointer;
            border: none;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        }
        
        .neatness-value {
            min-width: 40px;
            text-align: right;
            color: #667eea;
            font-weight: 600;
            font-size: 14px;
        }
        
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 10px;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .loading {
            display: none;
            text-align: center;
            color: #666;
            margin: 20px 0;
            font-size: 14px;
        }
        
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #ddd;
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 10px;
            vertical-align: middle;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .output-section h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 20px;
        }
        
        .preview-container {
            background: #f5f5f5;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            min-height: 300px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .preview-container img {
            max-width: 100%;
            max-height: 600px;
            border-radius: 8px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }
        
        .preview-info {
            color: #999;
            font-size: 14px;
            margin-top: 15px;
        }
        
        .error {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 8px;
            margin: 15px 0;
            font-size: 14px;
            display: none;
        }
        
        .error.show {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Input Panel -->
        <div class="panel">
            <h1>InkClone</h1>
            <p class="subtitle">Transform text into handwritten documents</p>
            
            <form id="generateForm">
                <div class="form-group">
                    <label for="textInput">Your Text</label>
                    <textarea id="textInput" placeholder="Type the text you want to render as handwriting..." required></textarea>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label for="paperSelect">Paper Type</label>
                        <select id="paperSelect">
                            <option value="college_ruled">College Ruled</option>
                            <option value="blank">Blank</option>
                            <option value="wide_ruled">Wide Ruled</option>
                            <option value="graph">Graph</option>
                            <option value="legal_pad">Legal Pad</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="inkSelect">Ink Color</label>
                        <select id="inkSelect">
                            <option value="black">Black</option>
                            <option value="blue">Blue</option>
                            <option value="dark_blue">Dark Blue</option>
                            <option value="green">Green</option>
                            <option value="red">Red</option>
                            <option value="pencil">Pencil</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label for="artifactSelect">Effect</label>
                        <select id="artifactSelect">
                            <option value="scan">Scan</option>
                            <option value="phone">Phone Photo</option>
                            <option value="clean">Clean</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Neatness</label>
                    <div class="slider-group">
                        <input type="range" id="neatnessSlider" min="0" max="100" value="50" step="1">
                        <span class="neatness-value" id="neatnessValue">0.50</span>
                    </div>
                    <p class="preview-info">0 = Messy, 1 = Neat</p>
                </div>
                
                <div class="error" id="errorMessage"></div>
                
                <button type="submit" id="generateBtn">Generate Document</button>
                <div class="loading" id="loading">
                    <span class="spinner"></span>
                    <span>Generating your document...</span>
                </div>
            </form>
        </div>
        
        <!-- Output Panel -->
        <div class="panel output-section">
            <h2>Preview</h2>
            <div class="preview-container" id="previewContainer">
                <p style="color: #999;">Your generated document will appear here</p>
            </div>
        </div>
    </div>
    
    <script>
        const form = document.getElementById('generateForm');
        const textInput = document.getElementById('textInput');
        const paperSelect = document.getElementById('paperSelect');
        const inkSelect = document.getElementById('inkSelect');
        const artifactSelect = document.getElementById('artifactSelect');
        const neatnessSlider = document.getElementById('neatnessSlider');
        const neatnessValue = document.getElementById('neatnessValue');
        const generateBtn = document.getElementById('generateBtn');
        const loading = document.getElementById('loading');
        const errorMessage = document.getElementById('errorMessage');
        const previewContainer = document.getElementById('previewContainer');
        
        // Update neatness display
        neatnessSlider.addEventListener('input', (e) => {
            neatnessValue.textContent = (parseInt(e.target.value) / 100).toFixed(2);
        });
        
        // Handle form submission
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const text = textInput.value.trim();
            if (!text) {
                showError('Please enter some text');
                return;
            }
            
            try {
                showError('');
                generateBtn.disabled = true;
                loading.style.display = 'block';
                previewContainer.innerHTML = '<p style="color: #999;">Generating...</p>';
                
                const response = await fetch('/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        text: text,
                        paper: paperSelect.value,
                        ink: inkSelect.value,
                        artifact: artifactSelect.value,
                        neatness: parseInt(neatnessSlider.value) / 100,
                    })
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Failed to generate document');
                }
                
                const data = await response.json();
                
                if (data.success) {
                    previewContainer.innerHTML = `
                        <div>
                            <img src="${data.image}" alt="Generated document">
                            <div class="preview-info">
                                <strong>${data.paper}</strong> • ${data.ink} ink • ${data.artifact}
                            </div>
                        </div>
                    `;
                } else {
                    throw new Error(data.error || 'Unknown error');
                }
            } catch (error) {
                showError(error.message);
                previewContainer.innerHTML = '<p style="color: #999;">Failed to generate document</p>';
            } finally {
                generateBtn.disabled = false;
                loading.style.display = 'none';
            }
        });
        
        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.classList.toggle('show', !!message);
        }
        
        // Auto-generate on load for demo
        window.addEventListener('load', () => {
            textInput.value = 'The quick brown fox jumps over the lazy dog';
        });
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
