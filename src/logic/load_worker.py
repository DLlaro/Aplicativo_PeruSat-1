from PySide6.QtCore import QThread, Signal
import random
from logic.prediccion.roi_tiler import roi_to_tiles
from logic.image_loader import SatelliteLoader
from logic.prediccion.predict import predict_tiles_multiclase
from logic.prediccion.reconstruccion import stitch_tiles_by_class
from logic.prediccion.to_gpkg import raster_to_vector
from logic.prediccion.limpiar_archivos import clean_temp_files
from logic.prediccion.cargar_capa import load_vector_to_napari
import os

class LoadWorker(QThread):
    # En PySide6 se usa Signal en lugar de pyqtSignal
    metadata_ready = Signal(int, int)  # Envía W, H
    finished = Signal(object)         # Envía la imagen (numpy array)
    error = Signal(str)               # Envía el error
    progress_update = Signal(int, str, bool) # Nueva señal para el % real
    status_msg = Signal(str)

    def __init__(self,
                 file_path: str,
                 base_project_path: str = None,
                 coords: tuple = None, 
                 loader: SatelliteLoader= None,  
                 escala: int = None,
                 mode: str= 'load',
                 modelo = None, 
                 output_dir: str = None):
        super().__init__()
        self.coords = coords
        self.mode = mode
        self.loader = loader
        self.base_project_path = base_project_path
        self.file_path = file_path
        self.output_path = output_dir
        self.escala = escala
        self.modelo = modelo

    def run(self):
        try:
            if self.mode == 'metadata':
                self._read_metadata()
            if self.mode == 'load':
                self._load_image()
            elif self.mode == 'tiling':
                self._do_tiling()
        except Exception as e:
            print(e)
            self.error.emit(str(e))

    def progress(self, valor = 0, msg = "", new_w = 0, new_h = 0, type = 'bar'):
        if type == 'bar':
            self.progress_update.emit(valor, msg, False)
        if type == 'metadata':
            self.metadata_ready.emit(new_w, new_h)
        if type == 'dialog':
            self.status_msg.emit(msg)

    def _read_metadata(self):
        """Lee el metadata de la imagen"""
        shape = self.loader.get_metadata(self.file_path)
        self.finished.emit(shape)

        return shape
        
    def _load_image(self):
        """Extrae la lógica de carga a un método separado"""
        rand1 = random.randint(1, 5)
        self.progress_update.emit((5 + rand1), "Cargando", False)

        img_vis = self.loader.get_preview(file_path= self.file_path, 
                                escala_input= self.escala, 
                                progress_callback = self.progress)
        
        self.finished.emit(img_vis)
        
        return img_vis
    
    def _do_tiling(self):
        """Lógica de tiling"""
        try:
            self.progress_update.emit(0, "Preprocesamiento del ROI", False)

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
                os.makedirs(path, exist_ok=True)
    
            print("\n[1/5] Dividiendo imagen...")
            roi_to_tiles(
                coords = self.coords, 
                tif_name = TIF_ID,
                tif_path = self.file_path, 
                out_dir = paths['tiles'], 
                tile_size = 512, 
                overlap = 0, 
                progress_callback = self._on_tiling_progress)
            
            self.progress_update.emit(100,"Tiling Completado", False)

            print("\n[2/5] Cargando modelo...")
            self.progress_update.emit(0,"Cargando Modelo...", True)
            #model = keras.models.load_model(os.path.join(self.base_project_path, 'logic','modelo', MODEL_NAME), compile=False)
            print("Modelo cargado")

            print("\n[3/5] Generando predicciones...")
            predict_tiles_multiclase(paths['tiles'], paths['masks'], self.modelo, progress_callback=self._on_tiling_progress)

            print("\n[4/5] Reconstruyendo imagen completa...")
            stitch_tiles_by_class(TIF_ID, paths['tiles'], paths['masks'], paths['recons'], progress_callback=self._on_tiling_progress)

            print("\n[5/5] Vectorizando resultados...")
            gpkg_paths = raster_to_vector(paths['recons'], out_dir=paths['gpkg'], progress_callback=self._on_tiling_progress)

            #Eliminar tiles, masks, recons
            clean_temp_files(paths)

            print("\nCargando puntos al visor")
            
            shape = load_vector_to_napari(gpkg_paths[1], self.loader)

            self.finished.emit(shape)
            
            return shape

        # self.tiling_finished.emit(result)  # Nueva señal para tiling
        except Exception as e:
            self.error.emit(f"Error en tiling: {str(e)}")

    def _on_tiling_progress(self, current, total, message=None):
        """Callback que recibe progreso de roi_to_tiles"""
        if total > 0:
            progress = int((current / total) * 100)
            progress = max(0, min(progress, 100))  # 0-100
            self.progress_update.emit(progress, message, False)