from napari.components import ViewerModel 
from constants import (ROI_EDGE_COLOR, 
                       ROI_EDGE_WIDTH,
                       ROI_FACE_COLOR
                       )
from typing import Callable
from qtpy.QtCore import QTimer
from logic.image_loader import SatelliteLoader
from logic.utils import get_rectangle_area_km2

import numpy as np

class ROIManager:
    def __init__(self, viewer_model: ViewerModel, 
                 onToggleCallback: Callable[[bool], None] = None, 
                 onDataChanged: Callable[[bool], None] = None):
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
        self.coords_roi = None
        self.polygon_coords = None
        self.count = 0

        self._preparar_capas()

    @property
    def isActivated(self):
        return self._is_activated
    
    @isActivated.setter
    def isActivated(self, value: bool):
        self._is_activated = value

    def _preparar_capas(self) -> None:
        """
        Crea la capa una sola vez y la deja lista.
        Conecta la funcion _on_data_changed en caso no lo este.
        """
        if 'ROI' in self.viewer.layers:
            self.layer = self.viewer.layers['ROI']
        else:
            self.layer = self.viewer.add_shapes(
                name='ROI',
                edge_color=ROI_EDGE_COLOR,
                face_color=ROI_FACE_COLOR,
                edge_width=ROI_EDGE_WIDTH,
                ndim=2,
                visible=False
            )
        try:
            self.layer.events.data.connect(self._on_data_changed)
        except:
            pass

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
        # Notify UI of toggle state
        if self.isActivated:
            self._activar_modo_dibujo(mode)
        else:
            self._desactivar_modo_dibujo()

    def _activar_modo_dibujo(self, mode:str) -> None:
        if mode == "add_entire_image":
            #napari acepta las coordenadas (y,x)
            h, w = self.loader.scaled_shape
            coords = [[(0,0), (h,0), (h,w), (0,w)]]
            print(coords)
            self.set_roi_to_coords(coords)
            self.on_viewer_callback("activar", "add_rectangle", coords)
        else:
            self.on_viewer_callback("activar", mode)


    def _desactivar_modo_dibujo(self) -> None:
        """Sale del modo de dibujo"""
        self.viewer.cursor.style = 'standard'
        self.viewer.layers.selection.clear()

    def _on_data_changed(self, event):
        if self.layer is None or self._updating:
            return
        layer = event.source  # ← viene del evento, no de self

        if len(layer.data) > 1 and layer.mode == "add_rectangle":
            self._updating = True
            try:
                self.layer.data = self.layer.data[-1:]
            finally:
                self._updating = False

        ## LA logica del add_poligon se maneja al dar enter

        if self.on_data_changed_callback:
            self.on_data_changed_callback(len(self.layer.data) > 0)

    def on_polygon_confirm(self, scale):
        """Valida, limpia y prepara el ROI actual."""
        layer = self.layer
        
        if layer.mode == 'add_polygon':
            layer._finish_drawing()

        if len(layer.data) == 0:
            return None

        ultimo_poly = layer.data[-1]

        # Validación geométrica
        if len(ultimo_poly) < 3:
            layer.data = layer.data[:-1]
            return None

        # Limpieza de polígonos anteriores
        layer.data = [ultimo_poly]
        self.polygon_coords = ultimo_poly/scale # Guardamos el array real limpio
        
        # Reset visual
        layer.mode = 'pan_zoom'
        layer.mode = 'add_polygon'
        
        return self.polygon_coords

    def limpiar(self) -> None:
        """
        Limpia los datos de la capa ROI, desactiva modo dibujo y oculta la capa.
        """
        if self.layer is not None:
            self._updating = True
            try:
                self.layer.data = []  # Borra los rectángulos dibujados
                self.layer.visible = False # Oculta la capa
            finally:
                self._updating = False
        
        self.isActivated = False
        self.coords_roi = None
        self.polygon_coords = None

        if self.on_data_changed_callback:
            self.on_data_changed_callback(False)
        if self.on_toggle_callback:
            self.on_toggle_callback(False)
        if self.on_viewer_callback:
            self.on_viewer_callback("limpiar")  # ← le dice al viewer que limpie

    def set_roi_to_coords(self, layer_data: list) -> None:
        """
        Extrae el bounding box del ultimo ROI dibujado en coordenadas de pixeles.
        
        Args
        ----
        layer_data: datos de la capa, shape (n_vertices, 2) → [y, x]
        """
        if layer_data is None or len(layer_data) == 0:
            return

        shape_data = layer_data[-1]
        shape_data = np.array(shape_data)

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
            layer: Capa dibujada por el usuario en el visor
                    
        Returns:
            tuple: (real_x, real_y, real_w, real_h)
        """
        if self.layer is None:
            return None
        
        data = self.layer.data
        if not data or len(data) == 0:
                return None
        
        shape_data = data[-1]
        shape_data = np.array(shape_data)

        # shape_data tiene forma (n_vertices, 2) donde cada fila es [y, x]
        # Extraemos las coordenadas y calculamos el bounding box
        y_coords = shape_data[:, 0]
        x_coords = shape_data[:, 1]
        
        y_min, y_max = y_coords.min(), y_coords.max()
        x_min, x_max = x_coords.min(), x_coords.max()
        
        real_x = int(x_min / loader.scale_factor)
        real_y = int(y_min / loader.scale_factor)
        real_w = int((x_max - x_min) / loader.scale_factor)
        real_h = int((y_max - y_min) / loader.scale_factor)
        
        self.coords_roi= (real_x, real_y, real_w, real_h)
        self._actualizar_coords_validas(loader.original_shape, loader.transform)

    def _actualizar_coords_validas(self, shape, transform):
        true_w, true_h, inter_x1, inter_y1 = self._get_valid_shape_roi(shape)
        if true_w <= 0 or true_h <= 0:
            self.coords_roi = None
        
        self.coords_roi = (inter_x1, inter_y1, true_w, true_h)
        self.area_km2 = get_rectangle_area_km2((self.coords_roi[3], self.coords_roi[2]), transform)

    def _get_valid_shape_roi(self, shape) -> float :
        roi_x, roi_y, roi_w, roi_h = self.coords_roi
        img_h, img_w = shape

        inter_x1 = max(0, roi_x)
        inter_y1 = max(0, roi_y)
        inter_x2 = min(img_w, roi_x + roi_w)
        inter_y2 = min(img_h, roi_y + roi_h)

        # 3. Calcular dimensiones w,h del roi valido
        true_w = inter_x2 - inter_x1
        true_h = inter_y2 - inter_y1

        return true_w, true_h, inter_x1, inter_y1
    
    def validar_roi(self, min_area_km2=10, shape: tuple = None) -> bool | str:
        """
        Valida el ROI calculando la intersección real con la imagen.

        Calcula el área de solapamiento entre la caja dibujada y los límites 
        reales de la imagen. Si la selección es válida, actualiza
        self.coords_roi con las coordenadas recortadas listas para un crop seguro.

        Args
        ----------
        transfrom: 
            Matriz de transformación afin del raster
        min_area_km2 : float, optional
            Área mínima aceptable en km² para el ROI (por defecto 10 km²).
            Se calcula usando solo los píxeles que caen dentro de la imagen.
        original_shape : tuple[int, int]
            Dimensiones de la imagen original en formato (alto, ancho) en píxeles.
        tolerance : int, optional
            Máximo de píxeles que la selección puede desbordar por cada lado
            individual (izquierda, derecha, arriba, abajo) antes de ser rechazada.

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
        exceeded = self._calcular_overflow(shape)
        if exceeded:
            lados = ", ".join(exceeded)
            return False, f"La selección se sale demasiado por: {lados}."

        if self.area_km2 < min_area_km2:
            return False, f"Área útil insuficiente: {self.area_km2:.2f} km²"

        return True, f"{self.area_km2:.2f}"
    
    def _calcular_overflow(self, shape, tolerance= 512) -> tuple [bool, str]:
        roi_x, roi_y, roi_w, roi_h = self.coords_roi
        img_h, img_w = shape

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
    
