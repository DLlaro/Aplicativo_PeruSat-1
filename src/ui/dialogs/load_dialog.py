from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QSpinBox, QPushButton, QLineEdit, QFrame)
from logic.utils.utils import get_ram_info
from logic.utils.config_manager import settings
from constants import MAX_LIMIT_RENDER


class LoadDialog(QDialog):
    def __init__(self, parent = None, shape: tuple = None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Carga")
        self.resize(450, 150)
        self.h = shape[0]
        self.w = shape[1]
        self.max_scale = min(((settings.max_render - 500) / max(self.w, self.h)*100), 100)
        
        self._setup_ui()
        self._update_dimensions()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        ram: dict = get_ram_info()

        # Crear contenedor
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)

        # Estilo gris suave
        frame.setObjectName("specs")

        layout.addWidget(self._ram_specs(frame, ram))

        # Scale factor
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Calidad de la imagen:"))
        
        self.spin_escala = QSpinBox()
        self.spin_escala.setRange(10, self.max_scale )  # Default range without GPU
        self.spin_escala.setSingleStep(5)
        self.spin_escala.setSuffix("%")
        self.spin_escala.setValue(self.max_scale/2)
        self.spin_escala.setToolTip(f"10%: Original, {self.max_scale}%: Max permitido")

        scale_layout.addWidget(self.spin_escala)

        gpu_available = (
            settings.use_gpu_inference
            and settings.gpu_info["gpu_name"] != "CPU"
            and ram["available_mb"] >= 8192
        )

        if gpu_available:
            print("GPU potente disponible")
            layout.addWidget(self._gpu_specs(frame, settings.gpu_info))

        if gpu_available and settings.unlock_render:
            self._unlock_scale()
        else:
            self._lock_scale()
        
        ## Redimension 
        # Scale factor
        diemensiones_layout = QVBoxLayout()

        diemensiones_layout.addWidget(QLabel("Original:"))
        original_shape_layout = QHBoxLayout()
        original_w = QLineEdit(str(self.w))
        original_w.setEnabled(False)
        original_h = QLineEdit(str(self.h))
        original_h.setEnabled(False)

        original_shape_layout.addWidget(QLabel("Ancho:"))
        original_shape_layout.addWidget(original_w)
        original_shape_layout.addWidget(QLabel("Alto:"))
        original_shape_layout.addWidget(original_h)

        diemensiones_layout.addLayout(original_shape_layout)

        diemensiones_layout.addWidget(QLabel("Redimensión:"))
        redimension_shape_layout = QHBoxLayout()
        self.redim_w = QLineEdit(str(self.w))
        self.redim_w.setEnabled(False)
        self.redim_h = QLineEdit(str(self.h))
        self.redim_h.setEnabled(False)

        redimension_shape_layout.addWidget(QLabel("Ancho:"))
        redimension_shape_layout.addWidget(self.redim_w)
        redimension_shape_layout.addWidget(QLabel("Alto:"))
        redimension_shape_layout.addWidget(self.redim_h)

        diemensiones_layout.addLayout(redimension_shape_layout)

        layout.addLayout(scale_layout)
        layout.addLayout(diemensiones_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Cargar")
        btn_cancel = QPushButton("Cancelar")
        
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)

        ##Connections
        self.spin_escala.valueChanged.connect(self._on_spin_changed)

    def _ram_specs(self, frame: QFrame, ram):
        frame_layout_ram = QVBoxLayout(frame)
        frame_layout_ram.addWidget(
            QLabel(f"<b>RAM:</b> Disponible = <b>{ram['available_mb']} MB</b> | "
                f"Total = <b>{ram['total_mb']} MB</b>")
        )
        return frame

    def _gpu_specs(self, frame: QFrame, gpu: dict):
        frame_layout_gpu = frame.layout()
        frame_layout_gpu.addWidget(QLabel(f"GPU: <b>{gpu['gpu_name']}</b>"))
        frame_layout_gpu.addWidget(
            QLabel(f"<b>VRAM:</b> Usado = <b>{gpu['usado_mb']} MB </b> | "
                f"Total = <b>{gpu['total_mb']} MB </b>")
        )
        return frame        
    
    def _unlock_scale(self):       
        self.spin_escala.setRange(10, self.max_scale)

    def _lock_scale(self):
        current = self.spin_escala.value()
        self.spin_escala.setRange(10, self.max_scale)
        
        if current < self.max_scale:
            self.spin_escala.setValue(self.max_scale/2)
        
        self.spin_escala.setToolTip("10-50%: Sin GPU")

    def _on_spin_changed(self):
        self._update_dimensions()

    def _update_dimensions(self):
        scale = self.spin_escala.value() / 100 # obtener el valor en decimal
        new_w = int(self.w * scale)
        new_h = int(self.h * scale)

        self.redim_w.setText(str(new_w))
        self.redim_h.setText(str(new_h))
    
    def get_values(self):
        """Returns (escala, use_gpu_inference)"""
        return self.spin_escala.value()