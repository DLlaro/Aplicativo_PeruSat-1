from PySide6.QtCore import Signal
import os
import tempfile
from logic.workers.base_worker import BaseWorker
from logic.image_loader import SatelliteLoader
from logic.modelo.model_architecture import BuildingRoadModel
from logic.prediccion import (roi_to_tiles, predict_tiles_multiclase, 
                              stitch_tiles_by_class, raster_to_vector, load_vector_to_napari)

class TilingWorker(BaseWorker):
    finished = Signal(object)

    def __init__(self, 
                 loader: SatelliteLoader,
                 coords: tuple,
                 polygon: None,
                 modelo: BuildingRoadModel, 
                 output_dir: str) -> None:
        super().__init__()
        self.loader = loader
        self.coords = coords
        self.polygon = polygon
        self.modelo = modelo
        self.output_path = output_dir

    def run(self) -> None:
        """
        Obtiene el nombre del archivo y lo usa como identificador
        para la creacion de carpetas usadas durante el procesamiento.

        1. Se crean los parches/tiles
        2. Se generan las inferencias
        3. Se reconstruye el tif del ROI con las máscaras predichas
        4. Se convierte el tif reconstruido en una capa vectorial
        5. Se carga la capa vectorial en el visor de napari
        """
        try: 
            TIF_ID = os.path.basename(self.loader.path).split(".")[0]

            base_output = os.path.join(self.output_path, TIF_ID)
            gpkg_output = os.path.join(self.output_path, TIF_ID, "GPKG")
            os.makedirs(gpkg_output, exist_ok=True)

            with tempfile.TemporaryDirectory() as tmp:
                paths = {
                    'tiles':  os.path.join(base_output, "Tiles"),
                    'masks':  os.path.join(base_output, "Masks_Pred"),
                    'recons': os.path.join(base_output, "Reconstruccion"),
                    'gpkg':   gpkg_output   # permanente
                }

                for path in paths.values():
                    os.makedirs(path, exist_ok=True)

                print("\n[1/5] Generando tiles...")
                roi_to_tiles(coords = self.coords,
                            tif_name = TIF_ID,
                            loader = self.loader,
                            out_dir = paths['tiles'],
                            polygon_coords=self.polygon,
                            tile_size = 512, 
                            overlap = 0,
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
                if not gpkg_paths:
                    raise RuntimeError("No se generaron capas vectoriales para cargar en el visor.")

                buildings_path = next(
                    (p for p in gpkg_paths if os.path.basename(p).endswith("_buildings.gpkg")),
                    gpkg_paths[0]
                )
                shape = load_vector_to_napari(buildings_path, self.loader)

            result = {
                "shape": shape,
                "buildings_gpkg": buildings_path,
                "gpkg_paths": gpkg_paths,
                "base_output": base_output,
            }

            self.finished.emit(result)
        except Exception as e:
            print(e)
            self.error.emit(str(e))
