from flask import Flask, render_template, request, send_file
from PIL import Image
from collections import deque, Counter
import numpy as np
import math
import io

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process():
    if 'image' not in request.files:
        return 'No image uploaded', 400

    file = request.files['image']
    tolerance = int(request.form.get('tolerance', 30))
    tolerance = max(0, min(100, tolerance))

    img = Image.open(file.stream).convert('RGBA')
    result = remove_background(img, tolerance)

    buf = io.BytesIO()
    result.save(buf, format='PNG')
    buf.seek(0)

    return send_file(buf, mimetype='image/png', download_name='result.png')


def detect_background_color(pixels):
    """Sample border pixels to find the dominant background color."""
    h, w = pixels.shape[:2]

    border = np.concatenate([
        pixels[0, :, :3],         # top row
        pixels[h - 1, :, :3],     # bottom row
        pixels[:, 0, :3],         # left column
        pixels[:, w - 1, :3],     # right column
    ])

    colors = [tuple(int(c) for c in row) for row in border]
    return Counter(colors).most_common(1)[0][0]


def remove_background(img, tolerance):
    """Edge flood-fill background removal with alpha feathering."""
    pixels = np.array(img)
    h, w = pixels.shape[:2]

    bg_color = detect_background_color(pixels)
    bg_r, bg_g, bg_b = bg_color

    # Tolerance 0-100 maps to distance threshold 0-280
    # Default 30 -> threshold ~84, matching spec (~80-90)
    threshold = tolerance * 2.8
    if threshold < 1.0:
        threshold = 1.0

    visited = np.zeros((h, w), dtype=bool)
    result = pixels.copy()

    queue = deque()

    # Seed all border pixels
    for x in range(w):
        for y in (0, h - 1):
            if not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))

    # Phase 1: BFS flood fill from border
    _flood_fill(pixels, result, visited, queue, bg_r, bg_g, bg_b, threshold, h, w)

    # Phase 2: Detect and remove trapped background pockets
    # After border fill, interior gaps (between limbs, under weapons, etc.) are
    # still opaque because the subject blocks the path from the border. Scan for
    # connected regions of background-colored pixels that the border fill missed.
    # Small regions (highlights, eyes, teeth) are preserved; larger pockets get
    # the same transparency treatment as the border background.
    min_pocket = max(50, min(h, w) // 5)

    for sy in range(h):
        for sx in range(w):
            if visited[sy, sx]:
                continue

            r = int(pixels[sy, sx, 0])
            g = int(pixels[sy, sx, 1])
            b = int(pixels[sy, sx, 2])
            dist = math.sqrt((r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2)

            if dist > threshold:
                visited[sy, sx] = True
                continue

            # BFS to map this connected component of background-colored pixels
            component = [(sy, sx, dist)]
            visited[sy, sx] = True
            q = deque([(sy, sx)])

            while q:
                cy, cx = q.popleft()
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                        visited[ny, nx] = True
                        nr = int(pixels[ny, nx, 0])
                        ng = int(pixels[ny, nx, 1])
                        nb = int(pixels[ny, nx, 2])
                        ndist = math.sqrt(
                            (nr - bg_r) ** 2 + (ng - bg_g) ** 2 + (nb - bg_b) ** 2
                        )
                        if ndist <= threshold:
                            component.append((ny, nx, ndist))
                            q.append((ny, nx))

            # Large region = trapped background pocket, not an interior detail
            if len(component) >= min_pocket:
                for cy, cx, cdist in component:
                    new_alpha = int(255 * cdist / threshold)
                    result[cy, cx, 3] = min(int(pixels[cy, cx, 3]), new_alpha)

    return Image.fromarray(result)


def _flood_fill(pixels, result, visited, queue, bg_r, bg_g, bg_b, threshold, h, w):
    """BFS flood fill — shared by border fill and pocket removal."""
    while queue:
        y, x = queue.popleft()

        r = int(pixels[y, x, 0])
        g = int(pixels[y, x, 1])
        b = int(pixels[y, x, 2])
        dist = math.sqrt((r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2)

        if dist <= threshold:
            new_alpha = int(255 * dist / threshold)
            orig_alpha = int(pixels[y, x, 3])
            result[y, x, 3] = min(orig_alpha, new_alpha)

            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
