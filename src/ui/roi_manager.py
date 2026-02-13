import numpy as np
from pyproj import Transformer
from logic.image_loader import SatelliteLoader

class ROIManager:
    def __init__(self, viewer_model, loader, onToggleCallback= None):
        """
        Maneja la logica de dibujo para la región de interés (ROI)

        Args:       
            viewer_model: modelo de Napari (para añadir capas)
            loader: image_loader (saber escala real)
        """
        self.viewer = viewer_model
        self.loader = loader
        self.layer = None # Capa de formas
        self._updating = False
        self.on_toggle_callback = onToggleCallback
        self.isActivated = False

    def activar_herramienta(self):
        """Preparar el visor para dibujar"""
        #1. Crear capa si no existe
        self.isActivated = not self.isActivated

        # Si existe la función de aviso, la ejecutamos
        if self.on_toggle_callback:
            self.on_toggle_callback(self.isActivated)

        if self.isActivated:
            if 'ROI' not in self.viewer.layers:
                self.layer = self.viewer.add_shapes(
                    name = 'ROI',
                    edge_color = 'red',
                    face_color = [1, 0, 0, 0.2],
                    edge_width = 2,
                    ndim = 2
                )
                #conectar evento de cambio de datos
                self.layer.events.data.connect(self._forzar_unico)
            else:
                self.layer = self.viewer.layers['ROI']
            
            #2. Poner en modo rectángulo
            self.layer.mode = 'add_rectangle'
            self.viewer.cursor.style = 'crosshair'

            #3. Seleccionar capa
            self.viewer.layers.selection.active = self.layer
        else: 
            self.viewer.cursor.style = 'standard'

            self.limpiar()
            return

    def _forzar_unico(self, event):
        """Si hay mas de un rectangulo, borra el anterior"""
        if self.layer is None or self._updating: return

        if len(self.layer.data) > 1:
            self._updating = True
            try:
                #Mantener solo el último
                self.layer.data = self.layer.data[-1:]
            finally:
                self._updating = False 
    
    def limpiar(self):
        """Borrar el ROI actual"""
        if 'ROI' in self.viewer.layers:
            self.viewer.layers.remove('ROI')
            self.layer = None

    def obtener_coordenadas_roi(self) -> tuple[float, float, float, float]:
        """
        Obtiene las coordenadas del ROI desde el cursor y la capa de shapes.
        
        Returns:
            tuple: (w, h, lat, lon) o None si no hay ROI válido
        """
        x, y, w, h = self.loader.extraer_roi_real(
            self.roi_manager.layer
        )

        if w is None:
            return None
        
        return (x, y, w, h)