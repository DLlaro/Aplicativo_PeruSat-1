from PySide6.QtCore import Signal
import os
import tempfile
from logic.workers.base_worker import BaseWorker
from logic.image_loader import SatelliteLoader
from logic.modelo.model_architecture import BuildingRoadModel
from logic.prediccion import (compute_global_percentiles_stream_per_band,roi_to_tiles, predict_tiles_multiclase, 
                              stitch_tiles_by_class, raster_to_vector, load_vector_to_napari)
class TilingWorker(BaseWorker):
    finished = Signal(object)

    def __init__(self, 
                 loader: SatelliteLoader,
                 coords: tuple, 
                 modelo: BuildingRoadModel, 
                 output_dir: str):
        super().__init__()
        self.loader = loader
        self.coords = coords
        self.modelo = modelo
        self.output_path = output_dir

    def run(self):
        """
        Obtiene el nombre del archivo y lo usa como identificador
        para la creacion de carpetas usadas durante el procesamiento.

        1. Se crean los parches/tiles
        2. Se generan las predicciones
        3. Se reconstruye el tif del ROI con las máscaras predichas
        4. Se convierte el tif reconstruido en una capa vectorial
        5. Se carga la capa vectorial en el visor de napari
        """
        try: 
            TIF_ID = os.path.basename(self.loader.path).split(".")[0]
            gpkg_output = os.path.join(self.output_path, TIF_ID, "GPKG")
            os.makedirs(gpkg_output, exist_ok=True)

            with tempfile.TemporaryDirectory() as tmp:
                paths = {
                    'tiles':  os.path.join(tmp, "Tiles"),
                    'masks':  os.path.join(tmp, "Masks_Pred"),
                    'recons': os.path.join(tmp, "Reconstruccion"),
                    'gpkg':   gpkg_output   # permanente
                }

                for path in paths.values():
                    os.makedirs(path, exist_ok=True)

                print("\n[1/5] Calculando percentiles...")
                low , high = compute_global_percentiles_stream_per_band(tif_path = self.loader.path,
                                                           coords = self.coords,
                                                           progress_callback = self.progress)

                print("\n[1/5] Generando tiles...")
                roi_to_tiles(coords = self.coords, 
                            tif_name = TIF_ID,
                            tif_path = self.loader.path, 
                            out_dir = paths['tiles'], 
                            tile_size = 512, 
                            overlap = 0,
                            lo = low, 
                            hi = high,
                            progress_callback = self.progress)

                print("\n[2/5] Infiriendo...")
                predict_tiles_multiclase(paths['tiles'], 
                                         paths['masks'], 
                                         self.modelo, 
                                         progress_callback=self.progress)

                print("\n[3/5] Reconstruyendo...")
                stitch_tiles_by_class(TIF_ID, 
                                      paths['tiles'], 
                                      paths['masks'], 
                                      paths['recons'], 
                                      progress_callback=self.progress)

                print("\n[4/5] Vectorizando...")
                gpkg_paths = raster_to_vector(paths['recons'], 
                                              out_dir=paths['gpkg'], 
                                              progress_callback=self.progress)

                print("\n[5/5] Cargando resultados...")
                shape = load_vector_to_napari(gpkg_paths[1], self.loader)

            self.finished.emit(shape)
        except Exception as e:
            print(e)
            self.error.emit(str(e))
