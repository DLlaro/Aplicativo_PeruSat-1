import sys
import os
from PySide6.QtWidgets import QApplication

# Ruta absoluta de la carpeta 'src'
# Así 'logic' y 'ui' se pueden importar entre sí sin problemas
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.append(BASE_DIR)

from ui.main_window import MainWindow
import tensorflow as tf
from logic.utils.config_manager import settings
from logic.utils.utils import get_nvidia_info_tensorflow

def setup_hardware():
    settings.gpu_info = get_nvidia_info_tensorflow()
    if settings.use_gpu and settings.gpu_memory_growth:
        gpus = tf.config.list_physical_devices('GPU')
        if gpus:
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
            print("GPU configurada desde preferencias.")

if __name__ == "__main__":
    setup_hardware()
    app = QApplication(sys.argv)

    # Cargar QSS desde assets
    qss_path = os.path.join(BASE_DIR, "assets", "styles", "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())