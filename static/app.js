(function () {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const workspace = document.getElementById('workspace');
    const beforeImg = document.getElementById('before');
    const afterImg = document.getElementById('after');
    const toleranceSlider = document.getElementById('tolerance');
    const toleranceValue = document.getElementById('tolerance-value');
    const downloadBtn = document.getElementById('download-btn');
    const status = document.getElementById('status');

    let currentFile = null;
    let currentFilename = '';
    let debounceTimer = null;
    let processingBlob = null;
    let abortController = null;

    // Drop zone events

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleFile(file);
        } else {
            showStatus('Please drop an image file.', true);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) {
            handleFile(fileInput.files[0]);
        }
    });

    // Tolerance slider

    toleranceSlider.addEventListener('input', () => {
        toleranceValue.textContent = toleranceSlider.value;
        if (currentFile) {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => processImage(), 300);
        }
    });

    // Download

    downloadBtn.addEventListener('click', () => {
        if (!processingBlob) return;
        const name = currentFilename.replace(/\.[^.]+$/, '') + '_transparent.png';
        const url = URL.createObjectURL(processingBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
    });

    function handleFile(file) {
        currentFile = file;
        currentFilename = file.name;

        // Show original
        const reader = new FileReader();
        reader.onload = (e) => {
            beforeImg.src = e.target.result;
        };
        reader.readAsDataURL(file);

        workspace.classList.remove('hidden');
        processImage();
    }

    function processImage() {
        if (!currentFile) return;

        // Abort any in-flight request
        if (abortController) abortController.abort();
        abortController = new AbortController();

        showStatus('Processing...', false);
        downloadBtn.disabled = true;

        const formData = new FormData();
        formData.append('image', currentFile);
        formData.append('tolerance', toleranceSlider.value);

        fetch('/process', {
            method: 'POST',
            body: formData,
            signal: abortController.signal,
        })
            .then((response) => {
                if (!response.ok) throw new Error('Processing failed');
                return response.blob();
            })
            .then((blob) => {
                processingBlob = blob;
                if (afterImg.src.startsWith('blob:')) {
                    URL.revokeObjectURL(afterImg.src);
                }
                afterImg.src = URL.createObjectURL(blob);
                downloadBtn.disabled = false;
                hideStatus();
            })
            .catch((err) => {
                if (err.name !== 'AbortError') {
                    showStatus(err.message, true);
                }
            });
    }

    function showStatus(msg, isError) {
        status.textContent = msg;
        status.classList.remove('hidden', 'error');
        if (isError) status.classList.add('error');
    }

    function hideStatus() {
        status.classList.add('hidden');
    }
})();
