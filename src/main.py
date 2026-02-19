import sys
import os
from PySide6.QtWidgets import QApplication

# Ruta absoluta de la carpeta 'src'
# Así 'logic' y 'ui' se pueden importar entre sí sin problemas
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.append(BASE_DIR)

from ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Cargar QSS desde assets
    qss_path = os.path.join(BASE_DIR, "assets", "styles", "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())