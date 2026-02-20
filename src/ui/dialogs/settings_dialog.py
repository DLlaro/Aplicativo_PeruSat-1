from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QCheckBox, QPushButton, QFileDialog, QLabel, QHBoxLayout
from logic.utils.config_manager import settings

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración del Sistema")
        self.resize(400, 150)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Sección Modelo
        layout.addWidget(QLabel("<b>Modelo Keras:</b>"))
        h_layout = QHBoxLayout()
        self.lbl_path = QLineEdit(settings.model_path)
        self.lbl_path.setEnabled(False)
        btn_browse = QPushButton("Explorar...")
        btn_browse.clicked.connect(self.browse_model)
        h_layout.addWidget(self.lbl_path)
        h_layout.addWidget(btn_browse)
        layout.addLayout(h_layout)

        # Sección GPU
        layout.addWidget(QLabel("<b>Hardware:</b>"))
        self.chk_gpu = QCheckBox("Usar aceleración por GPU (NVIDIA)")
        self.chk_gpu.setChecked(settings.use_gpu)

        #Verificar existencia de GPU
        gpu = settings.gpu_info
        if gpu['gpu_name']=='CPU' or gpu["total_mb"]<=6144:
            self.chk_gpu.setText("Usar aceleración por GPU (NVIDIA) (No disponible)")
            self.chk_gpu.setEnabled(False)
        layout.addWidget(self.chk_gpu)

        self.chk_growth = QCheckBox("Activar Memory Growth (Recomendado)")
        self.chk_growth.setChecked(settings.gpu_memory_growth)
        layout.addWidget(self.chk_growth)

        # Botones Guardar/Cerrar
        btn_save = QPushButton("Guardar y Aplicar")
        btn_save.clicked.connect(self.save_settings)
        layout.addWidget(btn_save)

    def browse_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar Modelo", "", "Keras Model (*.keras)")
        if path:
            self.lbl_path.setText(path)

    def save_settings(self):
        settings.model_path = self.lbl_path.text()
        settings.use_gpu = self.chk_gpu.isChecked()
        settings.gpu_memory_growth = self.chk_growth.isChecked()
        self.accept()