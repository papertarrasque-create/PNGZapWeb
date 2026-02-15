import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QTreeView, QLabel, QSlider, QPushButton, QFrame, QFileDialog, QSizePolicy,
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QDir, QMimeData,
)
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QBrush, QColor, QFileSystemModel, QDragEnterEvent,
    QDropEvent,
)
from PIL import Image
from processing import remove_background

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')
IMAGE_FILTERS = [f'*{ext}' for ext in IMAGE_EXTENSIONS]

ACCENT = '#2563eb'
ACCENT_HOVER = '#1d4ed8'


class ProcessingWorker(QThread):
    """Runs background removal off the main thread."""
    finished = pyqtSignal(object)  # emits a PIL Image

    def __init__(self, img, tolerance):
        super().__init__()
        self.img = img
        self.tolerance = tolerance

    def run(self):
        result = remove_background(self.img, self.tolerance)
        self.finished.emit(result)


def pil_to_qpixmap(pil_img):
    """Convert a PIL RGBA image to a QPixmap."""
    data = pil_img.tobytes('raw', 'RGBA')
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def checkerboard_pixmap(width, height, cell=8):
    """Generate a checkerboard QPixmap for transparency preview."""
    pm = QPixmap(width, height)
    pm.fill(QColor('#ffffff'))
    painter = QPainter(pm)
    dark = QColor('#e0e0e0')
    for y in range(0, height, cell):
        for x in range(0, width, cell):
            if (x // cell + y // cell) % 2:
                painter.fillRect(x, y, cell, cell, dark)
    painter.end()
    return pm


class ImageLabel(QLabel):
    """A QLabel that scales its pixmap to fit while keeping aspect ratio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_pixmap = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_source_pixmap(self, pm):
        self._source_pixmap = pm
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._source_pixmap and not self._source_pixmap.isNull():
            scaled = self._source_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)


class CheckerImageLabel(ImageLabel):
    """ImageLabel with a checkerboard background for transparency."""

    def set_source_pixmap(self, pm):
        if pm and not pm.isNull():
            checker = checkerboard_pixmap(pm.width(), pm.height())
            composite = QPixmap(pm.size())
            painter = QPainter(composite)
            painter.drawPixmap(0, 0, checker)
            painter.drawPixmap(0, 0, pm)
            painter.end()
            self._source_pixmap = composite
        else:
            self._source_pixmap = pm
        self._rescale()


class DropZone(QFrame):
    """Visible drop target when no image is loaded."""
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            DropZone {{
                border: 2px dashed #ccc;
                border-radius: 4px;
                background: #fafafa;
                min-height: 200px;
            }}
            DropZone:hover {{
                border-color: {ACCENT};
                background: #eff6ff;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg = QLabel('Drop image here\nor use the file browser')
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet('color: #666; font-size: 13px;')
        layout.addWidget(msg)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(IMAGE_EXTENSIONS):
                    event.acceptProposedAction()
                    self.setStyleSheet(self.styleSheet().replace('#ccc', ACCENT))
                    return

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.styleSheet().replace(ACCENT, '#ccc'))

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self.styleSheet().replace(ACCENT, '#ccc'))
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(IMAGE_EXTENSIONS):
                self.file_dropped.emit(path)
                return


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PNGZap Desktop')
        self.resize(1100, 700)

        self._current_path = None
        self._current_pil = None
        self._result_pil = None
        self._worker = None
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._process)

        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        # --- Left: File browser ---
        browser_frame = QWidget()
        browser_layout = QVBoxLayout(browser_frame)
        browser_layout.setContentsMargins(8, 8, 0, 8)

        browser_label = QLabel('FILE BROWSER')
        browser_label.setStyleSheet(
            'font-size: 10px; letter-spacing: 2px; color: #666; padding-bottom: 4px;'
        )
        browser_layout.addWidget(browser_label)

        self._fs_model = QFileSystemModel()
        self._fs_model.setRootPath(QDir.homePath())
        self._fs_model.setNameFilters(IMAGE_FILTERS + ['*/'])
        self._fs_model.setNameFilterDisables(False)

        self._tree = QTreeView()
        self._tree.setModel(self._fs_model)
        self._tree.setRootIndex(self._fs_model.index(QDir.homePath()))
        self._tree.setColumnHidden(1, True)  # size
        self._tree.setColumnHidden(2, True)  # type
        self._tree.setColumnHidden(3, True)  # date
        self._tree.setHeaderHidden(True)
        self._tree.clicked.connect(self._on_tree_click)
        self._tree.setDragEnabled(False)
        browser_layout.addWidget(self._tree)

        splitter.addWidget(browser_frame)

        # --- Right: Workspace + Batch ---
        right_frame = QWidget()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(8, 8, 8, 8)

        # Header
        header = QLabel('PNGZap')
        header.setStyleSheet('font-size: 18px; font-weight: bold; letter-spacing: 1px;')
        subtitle = QLabel('Drop an image. Remove the background.')
        subtitle.setStyleSheet('font-size: 11px; color: #666; margin-bottom: 8px;')
        right_layout.addWidget(header)
        right_layout.addWidget(subtitle)

        # Drop zone (visible when no image loaded)
        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self._load_image)
        right_layout.addWidget(self._drop_zone)

        # Preview container (hidden until image loaded)
        self._preview_widget = QWidget()
        self._preview_widget.setVisible(False)
        preview_layout = QVBoxLayout(self._preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # Side-by-side previews
        images_row = QHBoxLayout()

        # Original
        original_col = QVBoxLayout()
        orig_label = QLabel('ORIGINAL')
        orig_label.setStyleSheet('font-size: 10px; letter-spacing: 2px; color: #666;')
        self._original_img = ImageLabel()
        self._original_img.setFrameShape(QFrame.Shape.StyledPanel)
        self._original_img.setStyleSheet('border: 1px solid #e0e0e0; background: #fff;')
        original_col.addWidget(orig_label)
        original_col.addWidget(self._original_img, 1)
        images_row.addLayout(original_col)

        # Processed
        processed_col = QVBoxLayout()
        proc_label = QLabel('TRANSPARENT')
        proc_label.setStyleSheet('font-size: 10px; letter-spacing: 2px; color: #666;')
        self._processed_img = CheckerImageLabel()
        self._processed_img.setFrameShape(QFrame.Shape.StyledPanel)
        self._processed_img.setStyleSheet('border: 1px solid #e0e0e0;')
        processed_col.addWidget(proc_label)
        processed_col.addWidget(self._processed_img, 1)
        images_row.addLayout(processed_col)

        preview_layout.addLayout(images_row, 1)

        # Controls row
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 8, 0, 0)

        tol_label = QLabel('TOLERANCE')
        tol_label.setStyleSheet('font-size: 10px; letter-spacing: 2px; color: #666;')
        controls.addWidget(tol_label)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(30)
        self._slider.valueChanged.connect(self._on_tolerance_changed)
        controls.addWidget(self._slider, 1)

        self._tol_value = QLabel('30')
        self._tol_value.setStyleSheet(f'font-size: 12px; color: {ACCENT}; min-width: 24px;')
        self._tol_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self._tol_value)

        self._save_btn = QPushButton('Save')
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save)
        controls.addWidget(self._save_btn)

        preview_layout.addLayout(controls)

        # Status
        self._status = QLabel()
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet('font-size: 11px; color: #666; padding: 4px;')
        preview_layout.addWidget(self._status)

        right_layout.addWidget(self._preview_widget, 1)

        # --- Batch placeholder ---
        batch_frame = QFrame()
        batch_frame.setFrameShape(QFrame.Shape.StyledPanel)
        batch_frame.setStyleSheet(
            'QFrame { border: 1px solid #e0e0e0; border-radius: 2px; '
            'background: #f8f8f8; margin-top: 8px; }'
        )
        batch_layout = QVBoxLayout(batch_frame)
        batch_label = QLabel('BATCH PROCESSING')
        batch_label.setStyleSheet('font-size: 10px; letter-spacing: 2px; color: #666;')
        batch_hint = QLabel('Coming soon')
        batch_hint.setStyleSheet('font-size: 11px; color: #999;')
        batch_layout.addWidget(batch_label)
        batch_layout.addWidget(batch_hint)
        batch_frame.setFixedHeight(60)
        right_layout.addWidget(batch_frame)

        splitter.addWidget(right_frame)
        splitter.setStretchFactor(0, 1)  # browser gets 1 part
        splitter.setStretchFactor(1, 3)  # workspace gets 3 parts
        splitter.setSizes([250, 750])

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background: #fafafa;
                font-family: 'DejaVu Sans Mono', monospace;
                color: #1a1a1a;
            }}
            QTreeView {{
                font-size: 12px;
                background: #fff;
                border: 1px solid #e0e0e0;
                border-radius: 2px;
            }}
            QTreeView::item:selected {{
                background: {ACCENT};
                color: #fff;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: #e0e0e0;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px;
                height: 14px;
                margin: -5px 0;
                background: {ACCENT};
                border-radius: 7px;
            }}
            QPushButton {{
                font-family: 'DejaVu Sans Mono', monospace;
                font-size: 11px;
                padding: 6px 16px;
                background: {ACCENT};
                color: #fff;
                border: none;
                border-radius: 2px;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            QPushButton:hover {{
                background: {ACCENT_HOVER};
            }}
            QPushButton:disabled {{
                background: #94a3b8;
            }}
        """)

    # --- File browser ---

    def _on_tree_click(self, index):
        path = self._fs_model.filePath(index)
        if os.path.isfile(path) and path.lower().endswith(IMAGE_EXTENSIONS):
            self._load_image(path)

    # --- Image loading and processing ---

    def _load_image(self, path):
        self._current_path = path
        self._current_pil = Image.open(path).convert('RGBA')
        self._result_pil = None
        self._save_btn.setEnabled(False)

        self._original_img.set_source_pixmap(pil_to_qpixmap(self._current_pil))

        self._drop_zone.setVisible(False)
        self._preview_widget.setVisible(True)

        self._status.setText('Processing...')
        self._process()

    def _on_tolerance_changed(self, value):
        self._tol_value.setText(str(value))
        if self._current_pil:
            self._debounce.start()

    def _process(self):
        if not self._current_pil:
            return

        self._save_btn.setEnabled(False)
        self._status.setText('Processing...')

        # Cancel any running worker
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()

        tolerance = self._slider.value()
        self._worker = ProcessingWorker(self._current_pil.copy(), tolerance)
        self._worker.finished.connect(self._on_processed)
        self._worker.start()

    def _on_processed(self, result_img):
        self._result_pil = result_img
        self._processed_img.set_source_pixmap(pil_to_qpixmap(result_img))
        self._save_btn.setEnabled(True)
        self._status.setText('')

    # --- Save ---

    def _save(self):
        if not self._result_pil or not self._current_path:
            return

        stem = Path(self._current_path).stem
        default_name = f'{stem}_transparent.png'
        default_dir = str(Path(self._current_path).parent / default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Transparent PNG', default_dir, 'PNG Files (*.png)'
        )
        if path:
            self._result_pil.save(path, format='PNG')
            self._status.setText(f'Saved: {Path(path).name}')


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('PNGZap Desktop')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
