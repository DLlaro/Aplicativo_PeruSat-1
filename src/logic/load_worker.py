from PySide6.QtCore import QThread, Signal
import rasterio
import random
from logic.roi_tiler import roi_to_tiles
from logic.image_loader import SatelliteLoader

from constants import MAX_LIMIT_RENDER, MAX_LIMIT_RENDER_UNLOCK

class LoadWorker(QThread):
    # En PySide6 se usa Signal en lugar de pyqtSignal
    metadata_ready = Signal(int, int)  # Envía W, H
    finished = Signal(object)         # Envía la imagen (numpy array)
    error = Signal(str)               # Envía el error
    progress_update = Signal(int, str) # Nueva señal para el % real
    status_msg = Signal(str)

    def __init__(self, 
                 file_path: str,
                 coords: tuple = None, 
                 loader: SatelliteLoader= None,  
                 escala: int = None,
                 unlock: bool = False,
                 mode: str= 'load', 
                 output_dir: str = None):
        super().__init__()
        self.coords = coords
        self.mode = mode
        self.loader = loader
        self.file_path = file_path
        self.output_path = output_dir
        self.escala = escala
        self.unlock = unlock

    def run(self):
        try:
            if self.mode == 'load':
                self._load_image()
            elif self.mode == 'tiling':
                self._do_tiling()
        except Exception as e:
            print(e)
            self.error.emit(str(e))

    def _load_image(self):
        """Extrae la lógica de carga a un método separado"""
        rand1 = random.randint(1, 5)
        self.progress_update.emit((5 + rand1), "Cargando")
        
        with rasterio.open(self.file_path) as src:
            self.loader.path = self.file_path
            self.loader.transform = src.transform
            self.loader.crs = src.crs
            self.loader.original_shape = (src.height, src.width)
            print("unlock", self.unlock)
            if self.unlock:
                max_render = MAX_LIMIT_RENDER_UNLOCK
            else:
                max_render = MAX_LIMIT_RENDER

            requested_scale = 1.0 / self.escala

            if (int(src.height * requested_scale)) > max_render or (int(src.width * requested_scale)) > max_render:
                scale = (max_render - 500) / max(src.width, src.height)
                self.status_msg.emit(f"Se ha ajustado la escala de {requested_scale:.2f} a {scale:.2f} para evitar problemas de visualización.")
            else:
                scale = requested_scale
            
            self.loader.scale_factor = scale
            new_h, new_w = int(src.height * scale), int(src.width * scale)
            self.metadata_ready.emit(new_w, new_h)

            rand2 = random.randint(1, 5)
            self.progress_update.emit((10 + rand2), "Leyendo Metadata:")

            data = src.read(
                [1, 2, 3],
                out_shape=(3, new_h, new_w),
                resampling=rasterio.enums.Resampling.bilinear
            )
            self.progress_update.emit(40, "Metadata leída:")

        def calc_total_progress(p, i):
            total = 40 + int(p * 0.6)
            self.progress_update.emit(total, f"Leyendo Banda {i+1}:")
            
        img_vis = self.loader._normalize_image(data, progress_callback=calc_total_progress)
        
        if self.mode == 'load':
            self.finished.emit(img_vis)
        
        return img_vis
    
    def _do_tiling(self):
        """Lógica de tiling"""
        try:
            self.progress_update.emit(0, "Preprocesamiento del ROI")
    
            roi_to_tiles(
                tuple= self.coords, 
                tif_path = self.file_path, 
                out_dir= self.output_path, 
                tile_size=512, 
                overlap = 0, 
                progress_callback=self._on_tiling_progress)

            self.progress_update.emit(100,"Tiling Completado!")
            self.finished.emit(self.output_path)
        # self.tiling_finished.emit(result)  # Nueva señal para tiling
        except Exception as e:
            self.error.emit(f"Error en tiling: {str(e)}")
            

    def _on_tiling_progress(self, current, total, message=None):
        """Callback que recibe progreso de roi_to_tiles"""
        if total > 0:
            progress = int((current / total) * 100)
            progress = max(0, min(progress, 100))  # 0-100
            self.progress_update.emit(progress, message)