import rasterio
from rasterio.enums import Resampling

import random
from tqdm import tqdm
import numpy as np
from numpy.typing import NDArray
from numpy import float32, uint8
from rasterio.windows import Window

from logic.utils.config_manager import settings

from constants import MAX_LIMIT_RENDER, MAX_LIMIT_RENDER_UNLOCK

from typing import TypeAlias, Callable,  Optional, Tuple

ProgressCallback: TypeAlias = Callable[[int, str, str, bool], None]

class SatelliteLoader:
    def __init__(self) -> None:
        self.path: str = None
        self.original_shape: Optional[Tuple[int, int]] = None  # (H, W)
        self.scaled_shape: Optional[Tuple[int, int]] = None
        self.scale_factor: float = 1.0
        self.transform = None
        self.crs = None
        self.global_lo: Optional[float] = None
        self.global_hi: Optional[float] = None
    
    def load_metadata(self, path: str) -> Tuple[int, int]:
        """
        Lee los metadatos básicos del raster (height y width).

        Parameters
        ----------
        path : str | Path
            Ruta al archivo raster.

        Returns
        -------
        Tuple[int, int]
            (height, width)
        """
        try:
            with rasterio.open(path) as src:
                self.path = path
                self.original_shape = (src.height, src.width)
                self.transform = src.transform
                self.crs = src.crs

            return self.original_shape

        except rasterio.errors.RasterioIOError as e:
            raise RuntimeError(f"No se pudo abrir el raster: {e}") from e
        
    def get_original_shape(self) -> Tuple[int, int]:
        """
        Devuelve el shape original del raster.

        Raises
        ------
        ValueError
            Si aún no se ha cargado metadata.
        """
        if self.original_shape is None:
            raise ValueError("No se ha cargado metadata todavía.")

        return self.original_shape

    def get_preview(self,
                    escala_input: int = 50,
                    bands: list = [1, 2, 3],
                    progress_callback: ProgressCallback = None) -> NDArray[float32]:
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
        NDArray[float32]
            Arreglo numpy de la imagen normalizada a 0-1
        """
        try:
            with rasterio.open(self.path) as src:
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
                self.scaled_shape = int(src.height * scale), int(src.width * scale)
                
                progress_callback(10, msg = "Leyendo Metadata:", infinite = True)

                # Lectura y reescalado de la imagen a nuevas dimensiones
                data = src.read(
                    bands,
                    out_shape = (3, self.scaled_shape[0], self.scaled_shape[1]),
                    resampling = Resampling.bilinear
                )

                data = np.transpose(data, (1, 2, 0))  # (3, H, W) → (H, W, 3)

                self.compute_global_percentiles_stream_per_band(progress_callback= progress_callback)

            return self._normalize_percentiles_per_band(data) / 255 # division entre 255 porque visor requiere valores entre 0-1

        except Exception as e:
            print(f"Error en image loader: {e}")
            raise e

    def compute_global_percentiles_stream_per_band(self,
        pmin: int = 2, 
        pmax: int = 98, 
        bands: list = [1,2,3], 
        nbins: int =10000, 
        progress_callback: ProgressCallback = None
    ) -> None:
        """
        Calcula los valores minimos y maximos de cada banda 
        en el raster reescalado

        Args
        -----------
        pmin: int
            percentil inferior
        pmax: int
            percentil superior
        bands: list
            bandas del raster a leer
        nbins: int
            numero de bins para el histograma
        progress_callback: ProgressCallback
            Funcion para la actualizacion de la barra de progreso
        """
        with rasterio.open(self.path) as src:
            nodata = 0
            block_size = 1024
            n_bands = len(bands)
            
            # Min/max por banda
            global_min = np.full(n_bands, np.inf)
            global_max = np.full(n_bands, -np.inf)
            
            ys = range(0, self.scaled_shape[0], block_size)
            xs = range(0, self.scaled_shape[1], block_size)

            total_tiles = len(ys) * len(xs)

            current_tile = 0
            # ===== SUB-PASO 1: Calcular min/max =====
            with tqdm(total=total_tiles,
            desc = f"Computing percentiles for GeoTIFF {self.path}") as pbar:
                for y in ys:
                    for x in xs:
                        win = Window(x, y, min(block_size, self.scaled_shape[1]-x), min(block_size, self.scaled_shape[0]-y))
                        block = src.read(bands, window=win).astype(np.float32)  # shape: (n_bands, rows, cols)
                        
                        for b in range(n_bands):
                            band_data = block[b]
                            if nodata is not None:
                                valid_values = band_data[band_data != nodata]
                            else:
                                valid_values = band_data.flatten()
                            
                            if valid_values.size > 0:
                                global_min[b] = min(global_min[b], valid_values.min())
                                global_max[b] = max(global_max[b], valid_values.max())
                        pbar.update(1)

                        current_tile += 1
                        # Progreso: 0-50% (primera mitad)
                        if progress_callback:
                            progress = int((current_tile / total_tiles) * 50)
                            progress_callback(progress, f"Calculando min/max...")
            
            # Histograma por banda
            hist = np.zeros((n_bands, nbins), dtype=np.int64)
            bin_edges = [np.linspace(global_min[b], global_max[b], nbins+1) for b in range(n_bands)]

            current_tile = 0
            # ===== SUB-PASO 2: Construir histograma =====
            with tqdm(total=total_tiles,
            desc = f"Computing histogrram for GeoTIFF {self.path}") as pbar:
                for y in ys:
                    for x in xs:
                        win = Window(x, y, min(block_size, self.scaled_shape[1]-x), min(block_size, self.scaled_shape[0]-y))
                        block = src.read(bands, window=win).astype(np.float32)
                        
                        for b in range(n_bands):
                            band_data = block[b]
                            if nodata is not None:
                                values = band_data[band_data != nodata]
                            else:
                                values = band_data.flatten()
                            
                            hist_block, _ = np.histogram(values, bins=bin_edges[b])
                            hist[b] += hist_block
                        pbar.update(1)

                        current_tile += 1
                    
                        # Progreso: 50-100% (segunda mitad)
                        if progress_callback:
                            progress = 50 + int((current_tile / total_tiles) * 50)
                            progress_callback(progress, f"Calculando histograma...")
            
            # Percentiles por banda
            lo = np.zeros(n_bands)
            hi = np.zeros(n_bands)
            
            for b in range(n_bands):
                cdf = np.cumsum(hist[b])
                if cdf[-1] == 0:
                    lo[b], hi[b] = 0, 0
                    continue
                cdf = cdf / cdf[-1]  # Normalizar a [0,1]
                idx_lo = np.searchsorted(cdf, pmin/100)
                idx_hi = np.searchsorted(cdf, pmax/100)
                lo[b] = bin_edges[b][min(idx_lo, len(bin_edges[b])-1)]
                hi[b] = bin_edges[b][min(idx_hi, len(bin_edges[b])-1)]
        
        self.global_lo, self.global_hi = lo, hi  # low, hi de la imagen reescalada (mas rapido)
    
    def _normalize_percentiles_per_band(self, x: NDArray,
                                    nodata_value: int =0
                                    ) -> NDArray[uint8]:
        """
        Normaliza la imagen por banda del raster usando los percentiles calculados

        Args
        ----------
        x: NDArray
            (height, width, n_bands) for numpy
        nodata_value: int
            valor de NoData en el raster
        """
        x_norm = np.zeros_like(x, dtype = np.float32)
        
        for b in range(x.shape[-1]):
            band = x[..., b]
            if nodata_value is not None:
                valid = band != nodata_value
                x_norm[..., b][valid] = np.clip((band[valid] - self.global_lo[b]) / (self.global_hi[b] - self.global_lo[b] + 1e-6), 0, 1)
            else:
                x_norm[..., b]= np.clip((band - self.global_lo[b]) / (self.global_hi[b] - self.global_lo[b] + 1e-6), 0, 1)
        
        out = (x_norm * 254 + 1).astype(np.uint8)## convertir valores cercanos a 0 a 1 para que no sean tratados como nodata
        
        if nodata_value is not None:
            valid_mask = np.all(x != nodata_value, axis=-1)
            out[~valid_mask] = 0
        
        return out
