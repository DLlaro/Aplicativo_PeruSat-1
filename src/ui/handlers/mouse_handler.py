# mouse_handler.py
from __future__ import annotations
from typing import TYPE_CHECKING
from logic.utils.coordinate_utils import cursor_to_coords, rectangle_to_coords
from constants import PIXEL_SIZE_PERU_SAT

if TYPE_CHECKING:
    from ..main_window import MainWindow   # only for type checking, no at runtime

class MouseHandler:
    def __init__(self, main_window: MainWindow):
        self.mw = main_window

    def connect(self):
        self.mw.viewer_model.mouse_move_callbacks.append(self.on_mouse_move)
        self.mw.viewer_model.mouse_drag_callbacks.append(self.on_drag)

    def disconnect(self):
        self.mw.viewer_model.mouse_move_callbacks.remove(self.on_mouse_move)
        self.mw.viewer_model.mouse_drag_callbacks.remove(self.on_drag)

    def on_mouse_move(self, viewer, event):
        self._actualizar_coordenadas(viewer, event)

    def on_drag(self, viewer, event):
        yield from self._drag_handler(viewer, event)

    def _actualizar_coordenadas(self, viewer, event):
        """
        Se ejecuta cada vez que el mouse se mueve sobre el visor.
        Calcula coordenadas reales y actualiza la UI.
        """
        # 1. Validación básica
        if not self.mw.viewer_model.layers:
            self.mw.status_mgr.lbl_coords.setText("Sin imagen")
            return
            
        try:
            # 2. Obtener posición del cursor (Napari usa orden Y, X)
            # cursor.position devuelve una tupla de floats
            cursor_pos = self.mw.viewer_model.cursor.position
            
            # Napari a veces devuelve 3 coordenadas si hay capas 3D (Z, Y, X)
            # Tomamos las últimas dos que suelen ser Y, X
            y_px = cursor_pos[-2] 
            x_px = cursor_pos[-1]

            # 3. Conversión Geométrica (Usando tu lógica)
            # Devuelve (X_GEO, Y_GEO) -> invierte y devuelve (Lat(y), Lon(x))
            x_geo, y_geo, lat, lon  = cursor_to_coords(x_px, y_px, self.mw.loader.scale_factor, self.mw.loader.transform, self.mw.loader.crs)
            
            # --- MEJORA: GUARDAR DATOS CRUDOS ---
            # Guardamos esto para que la función de COPIAR (Ctrl+C) lo use directo
            self.lat_lon = (lat, lon) 
            # ------------------------------------

             # Notify keyboard handler so Ctrl+C works
            self.mw.keyboard_handler.update_coords(lat, lon)

            # Update UI through status_mgr
            self.mw.status_mgr.update_coords(x_geo, y_geo, lat, lon)

        except Exception as e:
            # Es útil ver el error en la consola si estás desarrollando
            print(f"Error coords: {e}") 
            self.mw.status_mgr.lbl_coords.setText("Fuera de rango")
            self.mw.status_mgr.lbl_coords_lat_lon.setText("- , -")

    def _drag_handler(self, viewer, event):
        """
        Maneja el arrastre del mouse para ROI u otras interacciones.
        Usa yield para separar press → move → release.
        """
        #only act if ROI mode is active
        if not self.mw.roi_manager.isActivated:
            return
        
        press_pos = event.position
        #self.roi_manager.on_drag_start(press_pos)   # adapt to your API

        yield  # ← everything above runs on PRESS

        while event.type == "mouse_move":
            move_pos = event.position
            
            #Calculate ROI dimensions
            start = press_pos          # defined before yield (on press)
            end = move_pos
            
            dy = abs(end[-2] - start[-2])/self.mw.loader.scale_factor   # height in pixels
            dx = abs(end[-1] - start[-1])/self.mw.loader.scale_factor   # width in pixels
            
            area_m2 = dx * dy * (PIXEL_SIZE_PERU_SAT ** 2)  # use real pixel size
            area_km2 = area_m2 / 1_000_000
            
            #Update a label in your widget instead of statusBar()
            self.mw.status_mgr.update_roi_area(dx, dy, area_km2)
            yield

        # ← everything below runs on RELEASE
        self.mw.roi_manager.coords = rectangle_to_coords(self.mw.roi_manager.layer, scale_factor= self.mw.loader.scale_factor)
        release_pos = event.position
        #self.roi_manager.on_drag_end(release_pos)    # adapt to your API