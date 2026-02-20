from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QSpinBox, QPushButton, QLineEdit, QFrame)

from logic.utils.utils import get_ram_info
from logic.utils.config_manager import settings
from constants import MAX_LIMIT_RENDER


class LoadDialog(QDialog):
    def __init__(self, parent=None, w = None, h = None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Carga")
        self.resize(350, 150)
        self.w = w
        self.h = h
        
        self._setup_ui()
        self._update_dimensions()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        gpu_info = settings.gpu_info
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
        self.spin_escala.setRange(10, 50)  # Default range without GPU
        self.spin_escala.setSingleStep(10)
        self.spin_escala.setSuffix("%")
        self.spin_escala.setValue(40)
        self.spin_escala.setToolTip("10-50%: Sin GPU, 10-100%: Con GPU")

        self.spin_escala.valueChanged.connect(self._on_spin_changed)

        scale_layout.addWidget(self.spin_escala)

        if settings.use_gpu:
            if not gpu_info["gpu_name"]=="CPU" and ram["available_mb"] >= 8192:
                print("GPU potente disponible")
                layout.addWidget(self._gpu_specs(frame, gpu_info))
                self._unlock_scale()  
        elif self.w < MAX_LIMIT_RENDER and self.h < MAX_LIMIT_RENDER:
            self._unlock_scale()
        else:
            self._lock_scale()

        
        ## Redimension 
        # Scale factor
        diemensiones_layout = QVBoxLayout()

        diemensiones_layout.addWidget(QLabel("Original:"))
        original_shape_layout = QHBoxLayout()
        original_w = QLineEdit(str(self.w))
        original_w.setReadOnly(True)
        original_h = QLineEdit(str(self.h))
        original_h.setReadOnly(True)

        original_shape_layout.addWidget(QLabel("Ancho:"))
        original_shape_layout.addWidget(original_w)
        original_shape_layout.addWidget(QLabel("Alto:"))
        original_shape_layout.addWidget(original_h)

        diemensiones_layout.addLayout(original_shape_layout)

        diemensiones_layout.addWidget(QLabel("Redimensión:"))
        redimension_shape_layout = QHBoxLayout()
        self.redim_w = QLineEdit(str(self.w))
        self.redim_w.setReadOnly(True)
        self.redim_h = QLineEdit(str(self.h))
        self.redim_h.setReadOnly(True)

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
        self.spin_escala.setRange(10, 100)
        self.spin_escala.setToolTip("100%: Original, 10-90: Reducido")

    def _lock_scale(self):
        current = self.spin_escala.value()
        self.spin_escala.setRange(10, 50)
        
        # Adjust current value if it's out of range
        if current < 50:
            self.spin_escala.setValue(40)
        
        self.spin_escala.setToolTip("10-50%: Sin GPU")

    def _on_spin_changed(self):
        self._update_dimensions()

    def _update_dimensions(self):
        scale = self.spin_escala.value() / 100
        new_w = int(self.w * scale)
        new_h = int(self.h * scale)

        self.redim_w.setText(str(new_w))
        self.redim_h.setText(str(new_h))
    
    def get_values(self):
        """Returns (escala, use_gpu)"""
        return self.spin_escala.value()