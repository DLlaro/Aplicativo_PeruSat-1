from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QVBoxLayout
)

from logic.image_loader import SatelliteLoader

AREA_LIMITE = 20


class AnalyzeDialog(QDialog):
    def __init__(self, parent, loader: SatelliteLoader, area_roi_km2: float, callback=None, has_roi: bool = True):
        super().__init__(parent)

        self.setWindowTitle("Configuracion de Analisis")
        self.resize(480, 140)
        self.callback = callback
        self.selected_path = None
        self.process_full_image = False
        self.area = 0

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Analizar")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)

        self.push_btn = QPushButton("...", self)
        if self.callback:
            self.push_btn.clicked.connect(self.on_button_clicked)

        top_layout = QHBoxLayout()
        self.line_edit = QLineEdit()
        top_layout.addWidget(self.line_edit, 8)
        top_layout.addWidget(self.push_btn, 2)

        main_layout = QVBoxLayout()
        self.lbl_area = QLabel(f"Area estimada: {area_roi_km2:.2f} km2.")
        main_layout.addWidget(self.lbl_area)

        self.chk_full_image = QCheckBox("Procesar toda la imagen")
        self.chk_full_image.setChecked(not has_roi)
        
        main_layout.addWidget(self.chk_full_image)
        self.chk_full_image.toggled.connect(
            lambda: self.update_area(area_roi_km2, loader)
        )

        if not has_roi:
            self.chk_full_image.setEnabled(False)
            main_layout.addWidget(QLabel("No hay ROI dibujado: se procesara toda la imagen."))

        main_layout.addWidget(QLabel("Carpeta guardar:"))
        main_layout.addLayout(top_layout)
        main_layout.addLayout(btn_layout)

        self.warning_layout = QHBoxLayout()
        main_layout.addLayout(self.warning_layout)
        
        self.setLayout(main_layout)

        self.update_area(area_roi_km2, loader)

        btn_ok.setDefault(True)
        btn_ok.setFocus()

    def update_area(self, area_roi_km2, loader: SatelliteLoader):
        if self.chk_full_image.isChecked():
            self.area = loader.get_image_area_km2()
        else:
            self.area = area_roi_km2
        self.lbl_area.setText(f"Area estimada: {self.area:.2f} km2.")
        self.extension_aviso()

    def extension_aviso(self):
        while self.warning_layout.count():
            item = self.warning_layout.takeAt(0)
            try:
                widget = item.widget() if item is not None else None
                if widget:
                    widget.deleteLater()
            except Exception as e:
                print(f"Error al eliminar widget de advertencia: {e}")


        # 2. Add new warning if necessary
        if self.area > AREA_LIMITE:
            icon_label = QLabel()
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            icon_label.setPixmap(icon.pixmap(20, 20))
            
            message_label = QLabel("Advertencia: extensión grande, puede tardar más tiempo.")
            message_label.setWordWrap(True)
            message_label.setStyleSheet("color: #B71C1C; font-weight: bold;")

            self.warning_layout.addWidget(icon_label)
            self.warning_layout.addWidget(message_label, 1) # Give message more space

    def on_button_clicked(self):
        if self.callback:
            result = self.callback()
            if result:
                self.selected_path = result
                self.line_edit.setText(result)

    def accept(self):
        self.selected_path = self.line_edit.text()
        self.process_full_image = self.chk_full_image.isChecked()
        super().accept()
