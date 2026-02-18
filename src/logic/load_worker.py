from PySide6.QtCore import QThread, Signal
import rasterio
import random
from logic.prediccion.roi_tiler import roi_to_tiles
from logic.image_loader import SatelliteLoader
from tensorflow import keras
from logic.prediccion.prediccion import predict_tiles_multiclase
from logic.prediccion.reconstruccion import stitch_tiles_by_class
from logic.prediccion.to_gpkg import raster_to_vector
from logic.prediccion.limpiar_archivos import clean_temp_files
import os

from constants import MAX_LIMIT_RENDER, MAX_LIMIT_RENDER_UNLOCK, MODEL_NAME

class LoadWorker(QThread):
    # En PySide6 se usa Signal en lugar de pyqtSignal
    metadata_ready = Signal(int, int)  # Envía W, H
    finished = Signal(object)         # Envía la imagen (numpy array)
    error = Signal(str)               # Envía el error
    progress_update = Signal([int, str],[int, str, bool]) # Nueva señal para el % real
    status_msg = Signal(str)

    def __init__(self,
                 base_project_path: str,
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
        self.base_project_path = base_project_path
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

            TIF_ID = os.path.basename(self.file_path).split(".")[0]
            base_output = os.path.join(self.output_path, TIF_ID)

            paths = {
                'tiles': os.path.join(base_output, "Tiles"),
                'masks': os.path.join(base_output, "Masks_Pred"),
                'recons': os.path.join(base_output, "Reconstruccion"),
                'gpkg': os.path.join(base_output, "GPKG")
            }
            
            # Crear directorios si no existen
            for path in paths.values():
                print(path)
                os.makedirs(path, exist_ok=True)
    
            print("\n[1/5] Dividiendo imagen en tiles...")
            roi_to_tiles(
                coords = self.coords, 
                tif_name = TIF_ID,
                tif_path = self.file_path, 
                out_dir = paths['tiles'], 
                tile_size = 512, 
                overlap = 0, 
                progress_callback = self._on_tiling_progress)
            
            self.progress_update.emit(100,"Tiling Completado!")


            print("\n[2/5] Cargando modelo...")
            self.progress_update[int, str, bool].emit(100,"Tiling Completado!", True)
            model = keras.models.load_model(os.path.join(self.base_project_path, 'logic','modelo', MODEL_NAME), compile=False)
            print("Modelo cargado")

            print("\n[3/5] Generando predicciones...")
            predict_tiles_multiclase(paths['tiles'], paths['masks'], model, progress_callback=self._on_tiling_progress)

            print("\n[4/5] Reconstruyendo imagen completa...")
            stitch_tiles_by_class(TIF_ID, paths['tiles'], paths['masks'], paths['recons'], progress_callback=self._on_tiling_progress)

            print("\n[5/5] Vectorizando resultados...")
            raster_to_vector(paths['recons'], out_dir=paths['gpkg'], progress_callback=self._on_tiling_progress)
            
            #Eliminar tiles, masks, recons
            #clean_temp_files(paths)

            self.finished.emit("Termino")

        # self.tiling_finished.emit(result)  # Nueva señal para tiling
        except Exception as e:
            self.error.emit(f"Error en tiling: {str(e)}")
            

    def _on_tiling_progress(self, current, total, message=None):
        """Callback que recibe progreso de roi_to_tiles"""
        if total > 0:
            progress = int((current / total) * 100)
            progress = max(0, min(progress, 100))  # 0-100
            self.progress_update[int, str].emit(progress, message)