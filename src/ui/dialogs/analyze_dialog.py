from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QVBoxLayout,
)

AREA_LIMITE = 20


class AnalyzeDialog(QDialog):
    def __init__(self, parent, area_km2: float, callback=None, has_roi: bool = True):
        super().__init__(parent)

        self.setWindowTitle("Configuracion de Analisis")
        self.resize(480, 140)
        self.callback = callback
        self.selected_path = None
        self.process_full_image = False

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
        main_layout.addWidget(QLabel(f"Area estimada: {float(area_km2):.2f} km2."))

        self.chk_full_image = QCheckBox("Procesar toda la imagen")
        self.chk_full_image.setChecked(not has_roi)
        main_layout.addWidget(self.chk_full_image)

        if not has_roi:
            self.chk_full_image.setEnabled(False)
            main_layout.addWidget(QLabel("No hay ROI dibujado: se procesara toda la imagen."))

        if float(area_km2) > AREA_LIMITE:
            mensaje = "Advertencia: extension grande, puede tardar mas tiempo del esperado."
            content_layout = QHBoxLayout()
            icon_label = QLabel()
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            icon_label.setPixmap(icon.pixmap(20, 20))
            content_layout.addWidget(icon_label, 1)
            message_label = QLabel(mensaje)
            message_label.setWordWrap(True)
            content_layout.addWidget(message_label, 9)
            main_layout.addLayout(content_layout)

        main_layout.addWidget(QLabel("Carpeta guardar:"))
        main_layout.addLayout(top_layout)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

        btn_ok.setDefault(True)
        btn_ok.setFocus()

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
