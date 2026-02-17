from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QDialogButtonBox, QLabel, QLineEdit, QPushButton, QStyle)

AREA_LIMITE = 20

class AnalyzeDialog(QDialog):
    def __init__(self, parent, area: str,callback=None):
        super().__init__(parent)

        self.setWindowTitle("Configuración de Analisis")
        self.resize(450, 90)
        self.callback = callback
        self.selected_path = None

        QBtn = (
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.pushBtn = QPushButton("...", self)
        if self.callback:
            self.pushBtn.clicked.connect(self.on_button_clicked)

        # Layout horizontal para lineEdit y pushBtn
        top_layout = QHBoxLayout()
        self.lineEdit = QLineEdit()

        top_layout.addWidget(self.lineEdit, 8)
        top_layout.addWidget(self.pushBtn, 2)

        # Layout vertical principal
        main_layout = QVBoxLayout()

        area = float(area)

        area_lb = QLabel(f"Área a analizar: {area:.2f} km².")
        main_layout.addWidget(area_lb)

        if(area > AREA_LIMITE):
            mensaje = f"\nAdvertencia: Extensión grande, puede tardar más tiempo del esperado."
            content_layout = QHBoxLayout()

            # Ícono
            icon_label = QLabel()
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            icon_label.setPixmap(icon.pixmap(20, 20))
            content_layout.addWidget(icon_label, 1)

            # Mensaje
            message_label = QLabel(mensaje)
            message_label.setWordWrap(True)
            content_layout.addWidget(message_label, 9)

            # Agregar al layout principal
            main_layout.addLayout(content_layout)
        
        main_layout.addWidget(QLabel("Carpeta guardar:"))
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.buttonBox)
        
        self.setLayout(main_layout)

    def on_button_clicked(self):
        if self.callback:
            result = self.callback()
            if result:
                self.selected_path = result
                self.lineEdit.setText(result) #setear el path al qline

    def accept(self):
        """Sobrescribir accept para capturar el valor del QLineEdit"""
        self.selected_path = self.lineEdit.text()
        super().accept()