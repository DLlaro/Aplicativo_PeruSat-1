from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QStackedLayout
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from napari.qt import QtViewer
import os

from constants import LOGO_SIZE
from logic.utils.config_manager import settings

class ViewerPanel(QWidget):
    def __init__(self, viewer_model):
        super().__init__()
        self.viewer_model = viewer_model
        self.main_stack = QStackedLayout(self)
        self._setup()
    
    def _setup(self):
        self.main_stack.addWidget(self._build_logo_page())   # index 0
        self.main_stack.addWidget(self._build_viewer_page()) # index 1
        self.main_stack.setCurrentIndex(0)

    def _build_logo_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        lbl_img = QLabel()
        logo_path = settings.logo_path_png

        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            pixmap = pixmap.scaled(LOGO_SIZE, LOGO_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_img.setPixmap(pixmap)
        else:
            lbl_img.setText("PeruSat Analyzer\n(Logo no encontrado)")
            lbl_img.setStyleSheet("font-size: 24px; color: #666;")

        lbl_img.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_img)
        return page

    def _build_viewer_page(self):
        # QtViewer stored as attribute so MainWindow can reference it if needed
        self.qt_viewer = QtViewer(self.viewer_model)
        return self.qt_viewer
    
    def show_logo(self):
        self.main_stack.setCurrentIndex(0)

    def show_viewer(self):
        self.main_stack.setCurrentIndex(1)