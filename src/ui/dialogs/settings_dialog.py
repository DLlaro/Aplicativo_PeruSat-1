from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QCheckBox, QPushButton, QFileDialog, QLabel, QHBoxLayout, QComboBox
from logic.utils.config_manager import settings

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración del Sistema")
        self.resize(420, 190)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Sección Modelo
        layout.addWidget(QLabel("<b>Modelo PyTorch:</b>"))
        h_layout = QHBoxLayout()
        self.lbl_path = QLineEdit(settings.model_path)
        self.lbl_path.setEnabled(False)
        btn_browse = QPushButton("Explorar...")
        btn_browse.clicked.connect(self.browse_model)
        h_layout.addWidget(self.lbl_path)
        h_layout.addWidget(btn_browse)
        layout.addLayout(h_layout)

        encoder_layout = QHBoxLayout()
        encoder_layout.addWidget(QLabel("Encoder:"))
        self.cmb_encoder = QComboBox()
        self.cmb_encoder.addItems(["resnet34", "resnet50"])
        self.cmb_encoder.setCurrentText(settings.model_encoder)
        encoder_layout.addWidget(self.cmb_encoder)
        layout.addLayout(encoder_layout)

        # Sección GPU
        layout.addWidget(QLabel("<b>Hardware:</b>"))
        self.chk_gpu = QCheckBox("Inferencia por GPU (NVIDIA)")
        self.chk_gpu.setChecked(settings.use_gpu_inference)

        self.chk_render_tot = QCheckBox("Desbloquear renderizado (GPU)")
        self.chk_render_tot.setChecked(settings.unlock_render)

        #Verificar existencia de GPU
        gpu_info = settings.gpu_info
        if gpu_info.get("gpu_name", "CPU") == 'CPU' or gpu_info.get("total_mb", 0) <= 6144:
            self.chk_gpu.setText("Inferencia por GPU (NVIDIA) (No disponible)")
            self.chk_gpu.setEnabled(False)
            self.chk_render_tot.setEnabled(False)


        layout.addWidget(self.chk_render_tot)
        layout.addWidget(self.chk_gpu)

        # Botones Guardar/Cerrar
        btn_save = QPushButton("Guardar y Aplicar")
        btn_save.clicked.connect(self.save_settings)
        layout.addWidget(btn_save)

    def browse_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar Modelo", "", "Torch weights (*.pth *.pt)")
        if path:
            self.lbl_path.setText(path)

    def save_settings(self):
        settings.model_path = self.lbl_path.text()
        settings.model_encoder = self.cmb_encoder.currentText()
        settings.use_gpu_inference = self.chk_gpu.isChecked()
        settings.unlock_render = self.chk_render_tot.isChecked()
        if settings.unlock_render:
            settings.max_render = 20000
        else:
            settings.max_render = 10000
        
        self.accept()
