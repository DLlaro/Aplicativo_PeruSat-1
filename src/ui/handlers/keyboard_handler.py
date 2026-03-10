# ui/handlers/keyboard_handler.py

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QKeySequence, QShortcut

class KeyboardHandler:
    def __init__(self, main_window):
        self.mw = main_window
        self.lat_lon = None
    
    def connect(self):
        copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self.mw)
        create_polygon_shortcut = QShortcut(QKeySequence("Return"), self.mw)
        copy_shortcut.activated.connect(self._copiar_al_portapapeles)
        create_polygon_shortcut.activated.connect(self._on_enter_pressed)

    def update_coords(self, lat, lon):
        """Called by MouseHandler every time the cursor moves."""
        self.lat_lon = (lat, lon)

    def _copiar_al_portapapeles(self):
        if self.lat_lon is None:
            self.mw.statusBar().showMessage("Mueve el mouse sobre el mapa primero", 2000)
            return

        lat, lon = self.lat_lon
        texto = f"{lat:.6f}, {lon:.6f}"
        QApplication.clipboard().setText(texto)
        self.mw.statusBar().showMessage(f"Copiado: {texto}", 2000)
    
    def _on_enter_pressed(self):
        roi = self.mw.roi_manager

        if not roi.isActivated:
            return
        
        # transfiere responsabilidad al Manager
        coords = roi.on_polygon_confirm(self.mw.loader.scale_factor)

        if coords is None:
            self.mw.statusBar().showMessage("ROI inválido: Se requieren al menos 3 puntos.", 2000)