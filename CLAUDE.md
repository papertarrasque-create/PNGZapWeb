# PNGZap

## What This Is
PNGZap is a single-purpose web app that removes dominant background colors from PNGs and outputs transparent PNGs. Built for character art, tokens, icons — artwork with clean backgrounds (usually white) that need to go transparent for use in VTTs, compositing, or design work.

## Design Philosophy
- **Anti-Foundry**: Narrow scope, deep feel. This does one thing and does it well.
- **No black boxes**: Every processing step should be understandable. Flood fill, color distance, alpha math — no ML, no magic.
- **Aesthetic is meaning**: The UI should feel like a tool that respects the art passing through it. Clean, purposeful, not decorative.

## Architecture

### Stack
- **Backend**: Python (Flask), Pillow for image processing
- **Frontend**: Single-page HTML/CSS/JS — no framework, no build step
- **No external services**: Everything runs locally

### Processing Pipeline
1. User uploads a PNG via drag-and-drop or file picker
2. Backend auto-detects the dominant border color by sampling the image edges (top/bottom/left/right rows of pixels)
3. Flood-fill transparency is applied from all four image edges inward
4. Color distance tolerance is user-adjustable (slider, default ~30 out of 100)
5. Edge pixels within tolerance get partial alpha (feathering) — not binary on/off
6. Result is returned as a downloadable transparent PNG

### Key Algorithm: Edge Flood Fill
- NOT global color replacement (that would destroy interior whites — highlights, eyes, reflections)
- Flood fill starting from every border pixel whose color is within tolerance of the detected background color
- The fill propagates inward through contiguous pixels that are also within tolerance
- This naturally enters interior gaps (e.g., space between an arm and torso) because those regions connect to the border
- Pixels at the boundary of the fill region get proportional alpha based on their color distance from the target — this is what prevents harsh jagged edges

### Color Distance
- Use Euclidean distance in RGB space: `sqrt((r1-r2)² + (g1-g2)² + (b1-b2)²)`
- Max possible distance is ~441 (black to white). Tolerance slider maps to a threshold on this scale.
- Tolerance 0 = exact match only. Tolerance 100 = very aggressive removal.
- Default tolerance of 30 maps to roughly a distance threshold of ~80-90, which handles typical anti-aliased edges on white backgrounds.

### Alpha Feathering
- Pixels whose color distance is below the threshold get alpha proportional to how close they are to the threshold boundary
- `alpha = (distance / threshold)` — closer to background = more transparent, closer to threshold edge = more opaque
- This creates smooth transitions rather than jagged cutoffs

## UI Requirements

### Layout
- Single page, centered
- Drop zone / file picker at top
- Once image is loaded: side-by-side or toggle before/after view
- Transparent areas shown on a checkerboard pattern
- Tolerance slider below the preview
- Download button

### Visual Identity
- Tool aesthetic — think graph paper, precision, utility
- Blue-on-white as an accent palette (not dominant — this is a tool, not a brand)
- Monospace type for labels and controls
- Minimal chrome. The art is the hero, the UI gets out of the way.
- The drop zone should feel inviting but not flashy

### Interaction
- Drag and drop OR click to browse
- Tolerance slider updates the preview in real-time (or near real-time with debounce)
- Single "Download" button produces `[original-filename]_transparent.png`
- No login, no state, no history

## File Structure
```
pngzap/
├── CLAUDE.md
├── app.py              # Flask backend
├── requirements.txt    # flask, pillow
├── static/
│   ├── style.css
│   └── app.js
└── templates/
    └── index.html
```

## Development Notes
- Pillow's `ImageDraw.floodfill` is too limited for this — we need a custom flood fill that tracks visited pixels and applies graduated alpha
- For performance on larger images, consider using a deque-based BFS rather than recursive fill
- The tolerance slider should debounce (300ms) before triggering a re-process to avoid hammering the backend
- Max upload size: 10MB should cover most character art PNGs
- Preserve original image dimensions and color depth in output

## What This Is NOT
- Not a general-purpose image editor
- Not a photo background remover (no AI/ML subject detection)
- Not a batch processor (single image at a time)
- Not a hosted service (runs locally)
