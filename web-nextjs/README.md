# InkClone Pro - Premium Web Interface

**Built with UI UX Pro Max skill + 21st.dev components**

## Features

✨ **Premium Design**
- Glassmorphism UI with backdrop blur
- Gradient backgrounds and text effects
- Framer Motion animations
- Professional typography (Inter font)

🎨 **UI Components**
- Responsive grid layout
- Animated buttons and cards
- Real-time preview
- Smooth transitions

⚡ **Performance**
- Next.js App Router
- TypeScript for type safety
- Tailwind CSS for styling
- Component-based architecture

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
npm start
```

## Architecture

```
/app
├── layout.tsx          # Root layout with fonts
├── page.tsx            # Main interface (glassmorphism)
├── globals.css         # Tailwind + custom styles
└── api/generate/
    └── route.ts        # API proxy to FastAPI backend

/components/ui
├── button.tsx          # Animated button with variants
└── card.tsx            # Glass card components

/lib
└── utils.ts            # Class merging utilities
```

## Design System

### Colors
- **Primary**: Blue gradient (blue-600 to purple-600)
- **Background**: Multi-layer gradients (slate-50 to indigo-50)
- **Glass**: White with 70% opacity + backdrop blur

### Typography
- **Font**: Inter (Google Fonts)
- **Gradient text**: Blue to purple gradient
- **Hierarchy**: 5xl hero, 2xl cards, base body

### Animation
- **Framer Motion**: Scale animations on interaction
- **CSS**: Fade-in, slide-up, glow effects
- **Timing**: 0.5s transitions, smooth easing

## Backend Integration

Connects to existing FastAPI backend at `http://127.0.0.1:8000/generate`

Start backend first:
```bash
cd ~/Projects/inkclone
source venv/bin/activate
python3 web/app.py
```

Then start Next.js:
```bash
cd web-nextjs
npm run dev
```

## Premium Features

1. **Glass Morphism Cards** - Modern design trend
2. **Gradient Text Effects** - Eye-catching headings  
3. **Animated Interactions** - Micro-animations on hover/click
4. **Professional Layout** - Two-column responsive grid
5. **Real-time Validation** - Dynamic button states
6. **Smooth Transitions** - All state changes animated

Built with UI UX Pro Max design intelligence! 🎨