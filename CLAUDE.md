# PNGZap

## What This Is
PNGZap is a single-purpose web app that removes dominant background colors from images and outputs transparent PNGs. Built for character art, tokens, icons — artwork with clean backgrounds (usually white) that need to go transparent for use in VTTs, compositing, or design work.

Accepts PNG, JPEG, GIF, BMP, TIFF, and WebP. Always outputs PNG with alpha channel.

## Design Philosophy
- **Anti-Foundry**: Narrow scope, deep feel. This does one thing and does it well.
- **No black boxes**: Every processing step should be understandable. Flood fill, color distance, alpha math — no ML, no magic.
- **Aesthetic is meaning**: The UI should feel like a tool that respects the art passing through it. Clean, purposeful, not decorative.

## Architecture

### Stack
- **Processing**: Python, Pillow for image processing, NumPy for pixel arrays — shared `processing.py` module
- **Web version** (`main` branch): Flask backend, single-page HTML/CSS/JS frontend
- **Desktop version** (`desktop` branch): PyQt6 native GUI, same processing engine
- **No external services**: Everything runs locally

### Processing Pipeline
1. User uploads an image via drag-and-drop or file picker
2. Backend converts to RGBA and auto-detects the dominant border color by sampling the image edges (mode of top/bottom/left/right pixel rows)
3. **Phase 1** — Border flood fill: BFS from all border pixels, propagating inward through pixels within tolerance of the background color
4. **Phase 2** — Pocket detection: Scans for connected regions of background-colored pixels that Phase 1 couldn't reach (enclosed by the subject). Regions above a size threshold are treated as trapped background and made transparent. Small regions (highlights, eyes, teeth) are preserved.
5. Alpha feathering is applied in both phases — edge pixels get proportional alpha, not binary on/off
6. Result is returned as a downloadable transparent PNG

### Key Algorithm: Two-Phase Flood Fill

**Phase 1 — Border Fill:**
- BFS flood fill starting from every border pixel whose color is within tolerance of the detected background color
- Propagates inward through contiguous pixels that are also within tolerance
- Naturally enters interior gaps that connect to the border (e.g., space between an arm and torso if there's a continuous path of background along the edge)

**Phase 2 — Interior Pocket Detection:**
- After Phase 1, some background regions remain because the subject completely encloses them (arm-torso gaps, between-leg areas, weapon overlaps)
- Scans all unvisited pixels for connected components of background-colored pixels
- Components larger than `max(50, min(height, width) // 5)` pixels are classified as trapped background pockets and made transparent
- Components below the threshold are left alone — these are typically interior details (highlights, eye whites, small reflections)

**Why two phases:** A single border flood fill can't reach enclosed background pockets. Global color replacement would destroy interior whites. The two-phase approach handles both: border fill for the main background, pocket detection for enclosed gaps, size threshold to protect small interior details.

### Color Distance
- Euclidean distance in RGB space: `sqrt((r1-r2)² + (g1-g2)² + (b1-b2)²)`
- Max possible distance is ~441 (black to white)
- Tolerance slider (0-100) maps to threshold via `tolerance * 2.8`
- Tolerance 0 = exact match only. Tolerance 100 = very aggressive (threshold ~280)
- Default tolerance of 30 → threshold ~84, handles typical anti-aliased edges on white backgrounds

### Alpha Feathering
- `alpha = 255 * (distance / threshold)` — closer to background = more transparent, closer to threshold edge = more opaque
- Applied in both Phase 1 and Phase 2
- Original alpha is respected: `result = min(original_alpha, new_alpha)`
- Creates smooth transitions rather than jagged cutoffs

## UI — Web Version

### Layout
- Single page, centered, max-width 960px
- Drop zone / file picker at top
- Side-by-side before/after preview (stacks vertically on mobile)
- Checkerboard pattern behind transparent areas
- Tolerance slider and download button below the preview

### Visual Identity
- Tool aesthetic — precision, utility
- Blue-on-white accent palette (`#2563eb`)
- Monospace type (DejaVu Sans Mono) for labels and controls
- Minimal chrome. The art is the hero, the UI gets out of the way.

### Interaction
- Drag and drop OR click to browse (any image type)
- Tolerance slider updates the preview with 300ms debounce
- In-flight requests are aborted when a new one starts (AbortController)
- Download button produces `[original-filename]_transparent.png`
- No login, no state, no history

## UI — Desktop Version

### Layout
- `QSplitter` — left panel (file browser), right panel (workspace + batch placeholder)
- File browser: `QTreeView` + `QFileSystemModel`, rooted at home, filtered to image files
- Workspace: drop zone (before image loaded) → side-by-side original/processed previews
- Checkerboard composited behind processed image for transparency
- Batch processing placeholder panel at bottom (coming soon)

### Interaction
- Click image in file browser tree → loads and processes
- Drag-and-drop from OS file manager onto the drop zone
- Tolerance slider (0-100, default 30) with 300ms debounce
- Save button → `QFileDialog`, defaults to `[filename]_transparent.png`
- Processing runs in `QThread` to keep UI responsive

## File Structure
```
PNGZap/
├── CLAUDE.md
├── processing.py           # Shared algorithm — remove_background, flood fill, color detection
├── app.py                  # Flask web backend (imports processing.py)
├── desktop.py              # PyQt6 desktop app (imports processing.py)
├── requirements.txt        # Web deps: flask, pillow, numpy
├── requirements-desktop.txt # Desktop deps: pyqt6, pillow, numpy
├── .gitignore
├── static/
│   ├── style.css
│   └── app.js
└── templates/
    └── index.html
```

## Running

### Web version
```
cd keepers/PNGZap
source venv/bin/activate
python app.py
# Open http://localhost:5000
```

### Desktop version
```
cd keepers/PNGZap
source venv/bin/activate
python desktop.py
```

## Repository
- **GitHub**: PNGZapWeb (papertarrasque)
- **Branch**: `main` — web version (Flask + browser UI)
- **Branch**: `desktop` — desktop version (PyQt6 native GUI)

## Desktop Version — Architecture Notes

### Key Classes in `desktop.py`
- **`MainWindow`** — Top-level `QMainWindow`. Owns the file browser, workspace, and batch placeholder. Manages image state (`_current_pil`, `_result_pil`), debounce timer, and worker lifecycle.
- **`ProcessingWorker(QThread)`** — Runs `remove_background()` off the main thread. Emits `finished` signal with the result PIL Image. Terminated and replaced if tolerance changes mid-process.
- **`ImageLabel(QLabel)`** — Scales a source pixmap to fit its bounds while keeping aspect ratio. Used for the original preview.
- **`CheckerImageLabel(ImageLabel)`** — Composites a checkerboard behind the pixmap before scaling. Used for the processed/transparent preview.
- **`DropZone(QFrame)`** — Visible drop target shown before any image is loaded. Emits `file_dropped(str)` signal. Accepts OS file manager drag-and-drop filtered to image extensions.

### Conversion Path
PIL Image → `pil_to_qpixmap()` (raw RGBA bytes → `QImage` → `QPixmap`) → `ImageLabel.set_source_pixmap()` → scaled on every resize.

### Visual Identity (shared with web)
- Accent: `#2563eb` / hover `#1d4ed8`
- Font: DejaVu Sans Mono
- Labels: 10px uppercase with letter-spacing (matches web's `.label` class)
- Minimal chrome — same philosophy, native widgets

### What's Stubbed
- **Batch processing panel**: `QFrame` with "Coming Soon" label at bottom of right panel. Fixed 60px height. Ready to be replaced with a real queue widget (list view + add/remove/run controls).

## Session History

### Session 1 (2026-02-15) — Web version built
- Built the complete web app: Flask backend, two-phase flood fill algorithm, single-page HTML/CSS/JS frontend
- Initial commit on `main` branch, pushed to GitHub (papertarrasque-create/PNGZapWeb)

### Session 2 (2026-02-15) — Desktop version
- Created `desktop` branch from `main`
- Extracted processing algorithm from `app.py` into shared `processing.py` — both versions import from it
- Built PyQt6 desktop app (`desktop.py`): file browser tree, drag-and-drop, side-by-side preview with checkerboard, tolerance slider with debounce, save dialog, threaded processing, batch placeholder
- Chose PyQt6 over tkinter (not installed on system) and PySide6 (same API, less common)
- Verified: imports clean, processing pipeline works end-to-end on test image, app launches without errors
- **Next up**: Batch processing implementation, potential UI polish after real-world use

## What This Is NOT
- Not a general-purpose image editor
- Not a photo background remover (no AI/ML subject detection)
- Not a batch processor yet (single image at a time, batch placeholder exists)
- Not a hosted service (runs locally)
