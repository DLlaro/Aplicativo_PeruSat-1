import sys
import os
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
import torch
from logic.utils.config_manager import settings
from logic.utils.utils import get_nvidia_info_torch

def setup_hardware():
    # 1. Actualizamos la info de hardware usando la nueva función de Torch
    settings.gpu_info = get_nvidia_info_torch()
    
    # 2. Verificamos si CUDA está disponible según las preferencias
    if settings.use_gpu and torch.cuda.is_available():
        gpu_name = settings.gpu_info.get("gpu_name", "NVIDIA")
        print(f"Hardware configurado: GPU {gpu_name} activa.")
        
        # Opcional: Limpiar caché por si acaso hubo una sesión previa
        torch.cuda.empty_cache()
    else:
        print("Hardware configurado: Trabajando en modo CPU.")

if __name__ == "__main__":
    setup_hardware()
    app = QApplication(sys.argv)

    # Cargar QSS desde assets
    qss_path = os.path.join(settings.base_path, "assets", "styles", "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
        print(f"QSS cargado exitosamente desde: {qss_path}")
    else:
        print(f"ERROR: No se encontró el QSS en: {qss_path}")
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())