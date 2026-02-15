from flask import Flask, render_template, request, send_file
from PIL import Image
from processing import remove_background
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


if __name__ == '__main__':
    app.run(debug=True, port=5000)
