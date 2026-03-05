import rasterio
import rasterio.errors
from rasterio.enums import Resampling
from affine import Affine
from pyproj import CRS
import numpy as np
from numpy.typing import NDArray
from numpy import float32, uint8
import os

from logic.utils.config_manager import settings
from logic.utils import get_rectangle_area_km2, rectangle_to_coords
from typing import  Optional, Tuple

class SatelliteLoader:
    def __init__(self) -> None:
        """
        Args
        -----
        self.path: str
            ruta absoluta de la imagen
        self.original_shape : tuple
            H x W de la imagen entera (incluye el nodata)
        self.scaled_shape: tuple
            H x W de la imagen escalada 
        self.transform : Affine
            Matriz de transformacion afin de la imagen
        self.crs: CRS
            Sistema de coordenadas referenciado de la imagen
        self.bands: list
            list de bandas `(arbitrariamente se coloco 3 bandas)`
        self.global_hi: list
            Lista de los valores del percentil 98 del conjunto de train usados para normalizar
        self.global_lo: list
            Lista de los valores del percentil 2 del conjunto de train usados para normalizar
        """
        self.path: str = ""
        self.original_shape: Optional[Tuple[int, int]] = None  # (H, W)
        self.scaled_shape: Optional[Tuple[int, int]] = None
        self.scale_factor: float = 1.0
        self.transform : Affine
        self.crs : CRS
        self.bands: list
        self.global_lo: Optional[NDArray[float32]] = None
        self.global_hi: Optional[NDArray[float32]] = None
    
    def load_metadata(self, path: str) -> Tuple[int, int]:
        """
        Lee los metadatos básicos del raster (height y width).

        Parameters
        -----
        path : str | Path
            Ruta al archivo raster.

        Returns
        -----
        Tuple[int, int]
            (height, width)
        """
        try:
            with rasterio.open(path) as src:
                self.path = path
                self.original_shape = (src.height, src.width)
                self.transform = src.transform
                self.crs = src.crs
                self.bands = [1,2,3]

            res_x = abs(self.transform.a)
            res_y = abs(self.transform.e)

            if not (0.69 <= res_x <= 0.71 and 0.69 <= res_y <= 0.71):
                raise ValueError(
                    f"Resolución espacial distinta de 0.7m/px"
                    f"\n(X = {res_x}, Y = {res_y})"
                )
            return self.original_shape

        except rasterio.errors.RasterioIOError as e:
            raise RuntimeError(f"No se pudo abrir el raster: {e}") from e
        
    def get_original_shape(self) -> Tuple[int, int]:
        """
        Devuelve el shape original del raster (H x W)

        Raises
        ------
        ValueError
            Si aún no se ha cargado metadata.
        """
        if self.original_shape is None:
            raise ValueError("No se ha cargado metadata todavía.")

        return self.original_shape
    
    def get_res_px_per_side(self) -> tuple:
        """
        Obtener la resolucion de los pixeles del alto y ancho de la imagen

        returns
        -----
        (res_x, res_y) : tuple
            Valores de la resolucion del eje x y y de la imagen
        """
        if self.original_shape is None:
            raise ValueError("No se ha cargado metadata todavía.")
        res_x = abs(self.transform.a)
        res_y = abs(self.transform.e)

        return res_x, res_y
    
    def get_image_area_km2(self) -> float:
        return get_rectangle_area_km2(self.original_shape, self.transform)
    
    def get_image_coords(self) -> NDArray[np.float64]:
        if self.scaled_shape is None:
            raise ValueError("No hay preview cargada para construir la extension completa.")
        h, w = self.original_shape
        return 0, 0, h, w # se resta uno para evitar index out of bounds

    def get_preview(self,
                    escala_input: int = 50,
                    progress_callback = None) -> Optional[NDArray[float32]]:
        """
        Lee una imagen reescalada (downsampled) del raster para una visualización rápida, 
        calcula los percentiles 2-98.
        Devuelve una imagen lista para el visor Napari (Y, X, B) normalizada entre 0-255 float32.

        args
        ----------
        escala_input: int
            Valor ingresado por el usuario 0-100 para la reduccion de la imagen al cargar en el visor
        bands: list
            Bandas del raster a leer (RGB)
        progress_callback: ProgressCallback
            Funcion para la actualizacion de la barra de progreso

        return
        ----------
        data : NDArray[float32]
            Arreglo numpy de la imagen normalizada a 0-1
        """
        try:
            with rasterio.open(self.path) as src:    
                self.scale_factor = escala_input /100
                self.scaled_shape = int(src.height * self.scale_factor), int(src.width * self.scale_factor)
                
                if progress_callback:
                    progress_callback(10, msg = "Reescalando...", infinite = True)

                # Lectura y reescalado de la imagen a nuevas dimensiones
                data = src.read(
                    self.bands,
                    out_shape = (3, self.scaled_shape[0], self.scaled_shape[1]),
                    resampling = Resampling.bilinear
                )

                data = np.transpose(data, (1, 2, 0))  # (3, H, W) → (H, W, 3)
                self.load_global_percentiles() ##Cargar percentiles
                
                data = self._normalize_percentiles_per_band(data, progress_callback= progress_callback) / 255 # division entre 255 porque visor requiere valores entre 0-1

            return data

        except Exception as e:
            print(f"Error en image loader: {e}")
            return

    def load_global_percentiles(self) -> None:
        self.global_lo = np.load(os.path.join(settings.base_path, "assets", "valores_normalizados", "percentiles_lo.npy"))
        self.global_hi = np.load(os.path.join(settings.base_path, "assets", "valores_normalizados", "percentiles_hi.npy"))

    def _normalize_percentiles_per_band(self, x: NDArray,
                                    nodata_value: int =0,
                                    progress_callback = None) -> NDArray[uint8]:
        """
        Normaliza la imagen por banda del raster usando los percentiles calculados

        Args
        ----------
        x: NDArray
            (height, width, n_bands) for numpy
        nodata_value: int
            valor de NoData en el raster (0 para PeruSat-1)
        progress_callback: ProgressCallback
            Funcion para la actualizacion de la barra de progreso
        """
        if self.global_hi is None or self.global_lo is None:
            raise ValueError("Los percentiles globales no se han cargado correctamente.")
        
        if x.dtype == np.uint8 and x.max() <= 255:
            return x
        
        x_norm = np.zeros_like(x, dtype = np.float32)
        for b in range(x.shape[-1]):
            print("x.shape[-1]: ", x.shape[-1])

            band = x[..., b]
            if nodata_value is not None:
                valid = band != nodata_value
                x_norm[..., b][valid] = np.clip((band[valid] - self.global_lo[b]) / (self.global_hi[b] - self.global_lo[b] + 1e-6), 0, 1)
            else:
                x_norm[..., b] = np.clip((band - self.global_lo[b]) / (self.global_hi[b] - self.global_lo[b] + 1e-6), 0, 1)
            
            if progress_callback:
                progress = int(((b+1)/x.shape[-1])*100)
                progress_callback(progress, msg = f"Normalizando banda{b}")

        out = (x_norm * 254 + 1).astype(np.uint8)## convertir valores cercanos a 0 a 1 para que no sean tratados como nodata
        
        if nodata_value is not None:
            # Un pixel es valido si al menos una banda es distinta de nodata
            valid_mask = np.all(x != nodata_value, axis=-1)
            out[~valid_mask] = 0
        
        return out
