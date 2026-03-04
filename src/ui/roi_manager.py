from napari.components import ViewerModel 
from constants import (ROI_EDGE_COLOR, 
                       ROI_EDGE_WIDTH,
                       ROI_FACE_COLOR
                       )
from typing import Callable

from logic.image_loader import SatelliteLoader
from logic.utils import get_rectangle_area_km2

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

        self._preparar_capas()

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

    def activar_herramienta(self, isActivated: bool = None, mode: str = "add_rectangle") -> None:
        """
        Alternar el modo de dibujo del ROI
        
        Args
        ----------
        isActivated: bool
            - True → El modo dibujo esta activado
            - False → El modo dibujo esta desactivado
        """
        self.isActivated = isActivated if isActivated is not None else not self.isActivated

        # Notify UI of toggle state
        if self.on_toggle_callback:
            self.on_toggle_callback(self.isActivated)

        if self.isActivated:
            self._activar_modo_dibujo(mode)
        else:
            self._desactivar_modo_dibujo()

    def _activar_modo_dibujo(self, mode:str) -> None:
        if self.layer is None or 'ROI' not in self.viewer.layers:
            self._preparar_capas()

        self.layer.data = []

        self.layer.visible = True
        self.layer.mode = mode
        self.viewer.cursor.style = 'crosshair'
        self.viewer.layers.selection.active = self.layer

    def _desactivar_modo_dibujo(self) -> None:
        """Sale del modo de dibujo"""
        self.viewer.cursor.style = 'standard'
        self.viewer.layers.selection.clear()

    def _on_data_changed(self, event):

        if self.layer is None or self._updating:
            return
        
        if len(self.layer.data) > 1:
            self._updating = True
            try:
                self.layer.data = self.layer.data[-1:]
            finally:
                self._updating = False

        if self.on_data_changed_callback:
            self.on_data_changed_callback(len(self.layer.data) > 0)

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

        if self.on_data_changed_callback:
            self.on_data_changed_callback(False)
        if self.on_toggle_callback:
            self.on_toggle_callback(False)
    
    def tiene_datos(self) -> bool:
        """
        Check si la capa tiene datos datos 
        
        Return
        ----------
        :bool
            - True → Existen datos en la capa
            - False → No existen datos en la capa
        """
        return self.layer is not None and len(self.layer.data) > 0
    
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
    
