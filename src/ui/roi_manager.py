import numpy as np
from pyproj import Transformer
from constants import (PIXEL_SIZE_PERU_SAT, 
                       ROI_EDGE_COLOR, 
                       ROI_EDGE_WIDTH,
                       ROI_FACE_COLOR, 
                       MSG_ROI_ACTIVE, 
                       MSG_ROI_READY)

class ROIManager:
    def __init__(self, viewer_model, onToggleCallback= None, onDataChanged = None):
        """
        Maneja la logica de dibujo para la región de interés (ROI)

        Args:       
            viewer_model: modelo de Napari (para añadir capas)
        """
        self.viewer = viewer_model
        self.layer = None # Capa de formas
        self._updating = False
        self.on_toggle_callback = onToggleCallback
        self.on_data_changed_callback = onDataChanged # Guardamos el callback
        self.isActivated = False
        self.area_km2 = 0.0
        self.coords: tuple = None

    def activar_herramienta(self):
        """Toggle ROI drawing mode"""
        self.isActivated = not self.isActivated

        # Notify UI of toggle state
        if self.on_toggle_callback:
            self.on_toggle_callback(self.isActivated)

        if self.isActivated:
            self._activar_modo_dibujo()
        else:
            self._desactivar_modo_dibujo()

    def _activar_modo_dibujo(self):
        """Enter drawing mode"""
        # Create layer if it doesn't exist
        if 'ROI' not in self.viewer.layers:
            self.layer = self.viewer.add_shapes(
                name='ROI',
                edge_color=ROI_EDGE_COLOR,
                face_color=ROI_FACE_COLOR,
                edge_width=ROI_EDGE_WIDTH,
                ndim=2
            )
            # Connect events
            self.layer.events.data.connect(self._on_data_changed)
        else:
            self.layer = self.viewer.layers['ROI']

        # Set drawing mode
        self.layer.mode = 'add_rectangle'
        self.viewer.cursor.style = 'crosshair'
        self.viewer.layers.selection.active = self.layer

    def _desactivar_modo_dibujo(self):
        """Exit drawing mode"""
        self.viewer.cursor.style = 'standard'
        self.viewer.layers.selection.clear()

    def _on_data_changed(self, event):
        """Handle shape data changes"""
        if self.layer is None or self._updating:
            return

        # Keep only the most recent rectangle
        if len(self.layer.data) > 1:
            self._updating = True
            try:
                self.layer.data = self.layer.data[-1:]
            finally:
                self._updating = False

        # Notify MainWindow about data state
        if self.on_data_changed_callback:
            self.on_data_changed_callback(len(self.layer.data) > 0)

    def limpiar(self):
        """Clear ROI and reset state"""
        # Disconnect events before removing to avoid callbacks during cleanup
        if self.layer is not None:
            try:
                self.layer.events.data.disconnect(self._on_data_changed)
            except (ValueError, RuntimeError):
                pass  # Already disconnected

        # Remove layer
        if 'ROI' in self.viewer.layers:
            self.viewer.layers.remove('ROI')
        
        self.layer = None
        self.isActivated = False

        # Notify callbacks AFTER cleanup is complete
        if self.on_data_changed_callback:
            self.on_data_changed_callback(False)
        if self.on_toggle_callback:
            self.on_toggle_callback(False)
    
    def tiene_datos(self) -> bool:
        """Check if ROI has valid data"""
        return self.layer is not None and len(self.layer.data) > 0
    
    def validar_roi(self, min_area_km2=10, original_shape = None):
        """
        Valida que el ROI sea válido para análisis.
        
        Args:
            real_x: Coordenada X de la esquina superior izquierda
            real_y: Coordenada Y de la esquina superior izquierda
            real_w: Ancho del ROI en píxeles
            real_h: Alto del ROI en píxeles
            min_area: Área mínima requerida en píxeles cuadrados
            
        Returns:
            tuple: (es_valido: bool, mensaje_error: str)
        """
        real_x, real_y, real_w, real_h = self.coords

        # Área en kilómetros cuadrados (1 km2 = 1,000,000 m2)
        area_m2 = real_w * real_h * PIXEL_SIZE_PERU_SAT**2
        self.area_km2 = area_m2 / 1_000_000 
        
        if self.area_km2 < min_area_km2 :
            return (False, f"El ROI es pequeño ({self.area_km2:.2f} km²). "
                    f"Área mínima sugerida: {min_area_km2:.2f} km²")
        
        # 2. Verificar que el ROI esté dentro de los límites de la imagen
        img_height, img_width = original_shape

        # Verificar que las coordenadas sean válidas

        if real_x >= img_width or real_y >= img_height:
            return (False, f"ROI fuera de imagen: inicio ({real_x},{real_y}) vs límites ({img_width},{img_height})")

        if real_x + real_w > img_width or real_y + real_h > img_height:
            return (False, f"ROI excede límites: fin ({real_x+real_w},{real_y+real_h}) vs límites ({img_width},{img_height})")

        if real_w <= 0 or real_h <= 0:
            return (False, f"Dimensiones inválidas: ancho={real_w}, alto={real_h}")
        
        return (True, f"{self.area_km2:.2f}")