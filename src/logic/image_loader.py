import rasterio
from rasterio.enums import Resampling

import random

import numpy as np
from numpy.typing import NDArray
from numpy import float32

from logic.utils.config_manager import settings

from constants import MAX_LIMIT_RENDER, MAX_LIMIT_RENDER_UNLOCK

from typing import TypeAlias, Callable

ProgressCallback: TypeAlias = Callable[[int, str, str, bool], None]

class SatelliteLoader:
    def __init__(self):
        self.path: str = None
        self.original_shape: tuple = None
        self.scale_factor: float = 1.0 # Cuanto redujimos la imagen
        self.transform = None
        self.crs = None
    
    def get_metadata(self, path: str = "") -> None:
        """Leer el height y width del raster 
        (se puede implementar para leer el metadata entero)
        
        args
        ----------
        path: str
            Ruta del raster
        
        return
        ----------
        tuple:
            Tupla que contiene el height y width del raster
        """
        try:
            with rasterio.open(path) as src:   
                self.path = path
                self.original_shape = (src.height, src.width)
                return self.original_shape

        except Exception as e:
            print(f"Error en image loader: {e}")
            raise e
        
    def get_original_shape(self) -> tuple[int, int]:
        """Obtener el alto y ancho del raster.
        
        :return: 
            tupla que contiene el alto (height) y ancho (width) del raster
        """
        return self.original_shape

    def get_preview(self,
                    escala_input: int = 50,
                    bands: list = [1, 2, 3],
                    progress_callback: ProgressCallback = None) -> NDArray[float32]:
        """
        Lee una vista previa (downsampled) de la imagen para visualización rápida.
        Devuelve una imagen lista para Napari (Y, X, B) normalizada 0-255 uint8.

        args
        ----------
        escala_input: int
            Valor ingresado por el usuario 0-100 para la reduccion de la imagen al cargar en el visor
        bands: list
            Bandas a leer (RGB)
        progress_callback: Callable[[int, str, str, bool], None]
            Funcion para la actualizacion de la barra de progreso

        return
        ----------
        NDArray[float32]
            Arreglo numpy de la imagen normalizada a 0-1
        """
        rand1 = random.randint(1, 5)
        progress_callback(2 + rand1, msg = "Cargando:")
        try:
            with rasterio.open(self.path) as src:
                self.transform = src.transform
                self.crs = src.crs
                #print("unlock", self.unlock)
                if settings.use_gpu:
                    max_render = MAX_LIMIT_RENDER_UNLOCK
                else:
                    max_render = MAX_LIMIT_RENDER

                escala_perct = escala_input/100

                if (int(src.height * escala_perct)) > max_render or (int(src.width * escala_perct)) > max_render:
                    scale = (max_render - 500) / max(src.width, src.height)
                    progress_callback(msg = f"Se ha ajustado la calidad de {escala_input}% a {scale*100:.0f}% para evitar problemas de visualización.", 
                                      type = 'dialog')
                else:
                    scale = escala_perct
                
                self.scale_factor = scale
                new_h, new_w = int(src.height * scale), int(src.width * scale)
                
                rand2 = random.randint(1, 5)
                progress_callback(10 + rand2, 
                                  msg = "Leyendo Metadata:")

                data = src.read(
                    bands,
                    out_shape = (3, new_h, new_w),
                    resampling = Resampling.bilinear
                )
                progress_callback(40, msg = "Metadata leída:")
                
            return self._normalize_image(data, progress_callback=progress_callback)

        except Exception as e:
            print(f"Error en image loader: {e}")
            raise e
        
    def _normalize_image(self, data: NDArray, progress_callback: ProgressCallback = None) -> NDArray[float32]:
        """
        Normaliza cada banda independientemente (Stretch Histogram por canal).
        
        Args
        ----------
        (Bandas, Y, X)
        Salida: (Y, X, Bandas) normalizado 0-1
        """
        # 1. Crear contenedor vacío para el resultado (float para precisión)
        # Mantenemos la forma (Bandas, Y, X) para iterar fácil
        normalized_bands = np.zeros_like(data, dtype=np.float32)

        # 2. Iterar sobre cada banda (0=R, 1=G, 2=B)
        for i in range(data.shape[0]):
            band = data[i].astype(np.float32)
            
            # Máscara de datos válidos para ESTA banda
            valid_mask = (band > 0) & (band < 4095)
            
            if valid_mask.any():
                # Calcular percentiles SOLO de esta banda
                # Esto equilibra los colores (White Balancing automático)
                p2, p98 = np.percentile(band[valid_mask], (2, 98))
                
                # Clip (cortar extremos)
                band_clipped = np.clip(band, p2, p98)
                
                # Escalar de p2..p98 a 0..1
                denominador = p98 - p2
                if denominador == 0: denominador = 1  # Evitar div/0
                
                band_norm = (band_clipped - p2) / denominador
                
                # Limpiar el fondo (NoData) de nuevo
                band_norm[~valid_mask] = 0
                
                normalized_bands[i] = band_norm
            else:
                # Si la banda es todo 0 (negra)
                normalized_bands[i] = 0
            
            # Notificar progreso 
            # cada una representa el 33% del proceso de normalización.
            if progress_callback:
                # Calculamos el porcentaje basado en la banda actual
                valor = 40 + int(((i + 1) / data.shape[0]) * 60)
                progress_callback(valor, msg = f"Banda {i}")

        # 3. Transponer al final para Napari: (Bandas, Y, X) -> (Y, X, Bandas)
        return np.transpose(normalized_bands, (1, 2, 0))