from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QSpinBox, QCheckBox, QPushButton)
from PySide6.QtCore import Qt

class LoadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Carga")
        self.resize(350, 150)
        
        self.escala = 5
        self.use_gpu = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # GPU checkbox FIRST — affects scale range
        self.chk_gpu = QCheckBox("Usar aceleración GPU (si disponible)")
        self.chk_gpu.setChecked(False)
        self.chk_gpu.toggled.connect(self._on_gpu_toggled)  # Connect signal
        layout.addWidget(self.chk_gpu)
        
        # Scale factor
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Factor de reducción:"))
        
        self.spin_escala = QSpinBox()
        self.spin_escala.setRange(5, 10)  # Default range without GPU
        self.spin_escala.setValue(5)
        self.spin_escala.setToolTip("2-10: Sin GPU, 1-10: Con GPU")
        scale_layout.addWidget(self.spin_escala)
        
        layout.addLayout(scale_layout)
        
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
    
    def _on_gpu_toggled(self, checked: bool):
        """Update scale range based on GPU checkbox"""
        if checked:
            # GPU enabled → allow factor 2 (1/2 resolution)
            self.spin_escala.setRange(1, 10)
            self.spin_escala.setToolTip("1: Original, 2-10: Reducido")
        else:
            # GPU disabled → minimum factor 5
            current = self.spin_escala.value()
            self.spin_escala.setRange(5, 10)
            
            # Adjust current value if it's now out of range
            if current < 5:
                self.spin_escala.setValue(5)
            
            self.spin_escala.setToolTip("5-10: Sin GPU")
    
    def get_values(self):
        """Returns (escala, use_gpu)"""
        return self.spin_escala.value(), self.chk_gpu.isChecked()