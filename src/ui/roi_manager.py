from napari.components import ViewerModel 
from typing import Callable
from logic.image_loader import SatelliteLoader
from logic.utils import get_rectangle_area_km2

import numpy as np

class ROIManager:
    def __init__(self,
                 onViewerCallback: Callable[[],None] = None,
                 onToggleCallback: Callable[[bool], None] = None, 
                 onDataChanged: Callable[[bool], None] = None):
        """
        Maneja la logica de dibujo para la región de interés (ROI)

        Args:       
            viewer_model: modelo de Napari (para añadir capas)

        """
        self.layer = None # Capa de formas
        self._updating = False
        self.on_viewer_callback = onViewerCallback
        self.on_toggle_callback = onToggleCallback
        self.on_data_changed_callback = onDataChanged # Guardamos el callback
        self._is_activated = False
        self.loader: SatelliteLoader = None
        self.area_km2 = 0.0
        self._coords_roi: tuple = None
        self.polygon_coords = None

    @property
    def isActivated(self):
        """
        Devuelve el estado del modo dibujo del ROI

        Return
        -----
        :bool
            - True → Esta activo
            - False → Esta desactivado
        """
        return self._is_activated
    
    @isActivated.setter
    def isActivated(self, value: bool):
        self._is_activated = value

    @property
    def coords_roi(self) -> None:
        """
        Devuelve las coordenadas del roi x, y, w, h 
        
        Returns
        -----
        coords_roi: tuple
            - x → coordenada x de la esquina superior izquierda
            - y → coordenada y de la esquina superior izquierda
            - w → ancho del roi
            - h → alto del roi
        """
        return self._coords_roi
    
    @coords_roi.setter
    def coords_roi(self, value) -> None:
        self._coords_roi = value

    def activar_herramienta(self, mode: str = "add_rectangle") -> None:
        """
        Alternar el modo de dibujo del ROI
        
        Args
        ----------
        isActivated: bool
            - True → El modo dibujo esta activado
            - False → El modo dibujo esta desactivado
        """
        self.isActivated = not self.isActivated

        if self.on_toggle_callback:
            self.on_toggle_callback(self.isActivated, mode)
        if self.isActivated:
            self._activar_modo_dibujo(mode)
            self.on_viewer_callback(mode)
        else:
            self._desactivar_modo_dibujo()

    def _activar_modo_dibujo(self, mode:str) -> None:
        if mode == "add_entire_image":
            #napari acepta las coordenadas (y,x)
            h, w = self.loader.scaled_shape
            coords = np.array([(0,0), (h,0), (h,w), (0,w)])
            print(coords)
            self.set_roi_to_coords(coords)
            self.on_viewer_callback("activar", mode, coords)
        else:
            self.on_viewer_callback(mode)


    def _desactivar_modo_dibujo(self) -> None:
        """Sale del modo de dibujo"""
        self.on_viewer_callback("desactivar")

    def _on_data_changed(self, event):
        if self._updating:
            return
        
        layer = event.source  # ← viene del evento, no de self

        if len(layer.data) > 1 and layer.mode == "add_rectangle":
            self._updating = True
            try:
                layer.data = layer.data[-1:]
            finally:
                self._updating = False

        if self.on_data_changed_callback:
            self.on_data_changed_callback(len(layer.data) > 0)

    def limpiar(self) -> None:
        self.isActivated = False
        self._coords_roi = None
        self.polygon_coords = None
        self._tiene_datos = False

        if self.on_data_changed_callback:
            self.on_data_changed_callback(False)
        if self.on_toggle_callback:
            self.on_toggle_callback(False)
        if self.on_viewer_callback:
            self.on_viewer_callback("limpiar")  # ← le dice al viewer que limpie

    def set_roi_to_coords(self, layer_data: np.ndarray) -> None:
        """
        Extrae el bounding box del ultimo ROI dibujado en coordenadas de pixeles.
        
        Args
        ----
        layer_data: datos de la capa, shape (n_vertices, 2) → [y, x]
        """
        if layer_data is None or len(layer_data) == 0:
            return

        shape_data = np.array(layer_data)

        # Si vienen varios shapes → usar el último
        if shape_data.ndim == 3:
            shape_data = shape_data[-1]

        # shape_data ahora debe ser (n_vertices,2)
        y_coords = shape_data[:, 0]
        x_coords = shape_data[:, 1]

        sf = self.loader.scaled_factor

        raw_coords = (
            int(x_coords.min() / sf),
            int(y_coords.min() / sf),
            int((x_coords.max() - x_coords.min()) / sf),
            int((y_coords.max() - y_coords.min()) / sf),
        )

        self._update_valid_coords(raw_coords)

    def _update_valid_coords(
        self,
        raw_coords: tuple[int, int, int, int],
    ) -> None:
        """Clips coords to image bounds, updates state, returns clipped coords or None."""
        clipped = self._clip_coords_to_image(raw_coords)
        if clipped is None:
            self._coords_roi = None
            self.area_km2 = None
            return None

        self._coords_roi = clipped
        self.area_km2 = get_rectangle_area_km2((clipped[3], clipped[2]), self.loader.transform)

    def _clip_coords_to_image(
        self,
        raw_coords: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int] | None:
        """
        Clips a (x, y, w, h) rect to image bounds.

        Args:
            coords: (x, y, w, h) in pixel space.

        Returns:
            Clipped (x, y, w, h) or None if the intersection is empty.
        """
        x, y, w, h = raw_coords
        img_h, img_w = self.loader.original_shape

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(img_w, x + w)
        y2 = min(img_h, y + h)

        clipped_w = x2 - x1
        clipped_h = y2 - y1

        if clipped_w <= 0 or clipped_h <= 0:
            return None

        return (x1, y1, clipped_w, clipped_h)
    
    def validar_roi(self, min_area_km2=10) -> tuple[bool, str]:
        """
        Valida el ROI calculando la intersección real con la imagen.

        Calcula el área de solapamiento entre la caja dibujada y los límites 
        reales de la imagen. Si la selección es válida, actualiza
        self.coords_roi con las coordenadas recortadas listas para un crop seguro.

        Args
        ----------
        min_area_km2 : float, optional
            Área mínima aceptable en km² para el ROI (por defecto 10 km²).
            Se calcula usando solo los píxeles que caen dentro de la imagen.

        Return
        -------
        :bool, str
            - True, area_km2_str  → ROI válido. El string contiene el área útil
                                    en km² con 2 decimales, ej: "15.43".
            - False, mensaje      → ROI inválido. El string describe el motivo
                                    del rechazo.
        """
        if self.coords_roi is None:
            return (False, "No se han definido coordenadas.")

        # --- VALIDACIONES ---
        # A. Verificar si hay solapamiento
        if self.coords_roi[2] <= 0 or self.coords_roi[3] <= 0:
            return False, "El área seleccionada está completamente fuera de la imagen."

        # B. Verificar perdida por desborde por lado
        exceeded = self._calcular_overflow()
        if exceeded:
            lados = ", ".join(exceeded)
            return False, f"La selección se sale demasiado por: {lados}."

        if self.area_km2 < min_area_km2:
            return False, f"Área útil insuficiente: {self.area_km2:.2f} km²"

        return True, f"{self.area_km2:.2f}"
    
    def _calcular_overflow(self, tolerance= 512) -> tuple [bool, str]:
        """

        Args
        -----
        tolerance : int, optional
            Máximo de píxeles que la selección puede desbordar por cada lado
            individual (izquierda, derecha, arriba, abajo) antes de ser rechazada.
        """
        roi_x, roi_y, roi_w, roi_h = self.coords_roi
        img_h, img_w = self.loader.original_shape

        overflow_left   = max(0, -roi_x)          # píxeles fuera por la izquierda
        overflow_top    = max(0, -roi_y)           # píxeles fuera por arriba
        overflow_right  = max(0, roi_x + roi_w - img_w)   # píxeles fuera por la derecha
        overflow_bottom = max(0, roi_y + roi_h - img_h)   # píxeles fuera por abajo

        exceeded = []
        if overflow_left   > tolerance: exceeded.append(f"izquierda ({overflow_left}px)")
        if overflow_top    > tolerance: exceeded.append(f"arriba ({overflow_top}px)")
        if overflow_right  > tolerance: exceeded.append(f"derecha ({overflow_right}px)")
        if overflow_bottom > tolerance: exceeded.append(f"abajo ({overflow_bottom}px)")

        return exceeded
    
