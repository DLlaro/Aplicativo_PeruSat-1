import sys
import os
from PySide6.QtWidgets import QApplication

# Truco para añadir la carpeta 'src' al path de Python
# Así 'logic' y 'ui' se pueden importar entre sí sin problemas
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())