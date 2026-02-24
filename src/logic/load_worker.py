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
    metadata_ready = Signal(int, int)  # Envía W, H
    finished = Signal(object)         # Envía la imagen (numpy array)
    error = Signal(str)               # Envía el error
    progress_update = Signal(int, str, bool) # Nueva señal para el % real
    status_msg = Signal(str)

    def __init__(self,
                 file_path: str,
                 loader: SatelliteLoader= None,
                 coords: tuple = None, 
                 escala: int = None,
                 mode: str= 'load',
                 modelo = None, 
                 output_dir: str = None):
        
        super().__init__()
        self.coords = coords
        self.mode = mode
        self.loader = loader
        self.file_path = file_path
        self.output_path = output_dir
        self.escala = escala
        self.modelo = modelo

    def run(self):
        """
        Instancia la tarea a realizar en base al modo configurado
        """
        try:
            if self.mode == 'metadata':
                self._read_metadata()
            elif self.mode == 'load':
                self._load_image()
            elif self.mode == 'tiling':
                self._do_tiling()
            else:
                self.error.emit(f"Modo desconocido: {self.mode}")
        except Exception as e:
            print(e)
            self.error.emit(str(e))

    def progress(self, valor: int = 0, msg: str = "", type: str = 'bar', infinite: bool = False):
        """
        Emite la señal a la barra de progreso y los mensajes del statusbar dependiendo del tipo

        Args
        ----------
        valor: int 
            Valor establecido en la barra de progreso 0-100
        msg: str
            Valor cargado a un costado de la barra de progreso
        type: str
            Selecciona si emite señal a la barra o al statusbar
        infinite: bool
            True → Estilo de barra de carga infinita
            False → Estilo de barra de carga progresiva (default)
        """
        if type == 'bar':
            self.progress_update.emit(valor, msg, infinite)
        if type == 'dialog':
            self.status_msg.emit(msg)

    def _read_metadata(self) -> None:
        """Lee el metadata de la imagen
        
        Emit
        ----------
        shape: tuple
            Tupla con los valores del height y width del raster
        """
        shape = self.loader.get_metadata(self.file_path)
        self.finished.emit(shape)
        
    def _load_image(self) -> None:
        """
        Carga la previsualización de la imagen satelital y emite el resultado.

        Ejecuta `SatelliteLoader.get_preview` con la escala configurada,
        reportando el progreso mediante el callback correspondiente.
        Al finalizar, emite la señal `finished` con la imagen resultante
        para que el hilo principal la procese.

        return
        ----------
        finished: np.ndarray:
            Imagen de previsualización lista para renderizar en el viewer.
        """
        img_vis = self.loader.get_preview(escala_input= self.escala, 
                                progress_callback = self.progress)
        
        self.finished.emit(img_vis)

    def _do_tiling(self):
        """Lógica de tiling
        
        """
        
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
            progress_callback = self.progress)

        print("\n[2/5] Cargando modelo...")
        #model = keras.models.load_model(os.path.join(self.base_project_path, 'logic','modelo', MODEL_NAME), compile=False)
        print("Modelo cargado")

        print("\n[3/5] Generando predicciones...")
        predict_tiles_multiclase(paths['tiles'], paths['masks'], self.modelo, progress_callback=self.progress)

        print("\n[4/5] Reconstruyendo imagen completa...")
        stitch_tiles_by_class(TIF_ID, paths['tiles'], paths['masks'], paths['recons'], progress_callback=self.progress)

        print("\n[5/5] Vectorizando resultados...")
        gpkg_paths = raster_to_vector(paths['recons'], out_dir=paths['gpkg'], progress_callback=self.progress)

        #Eliminar tiles, masks, recons
        clean_temp_files(paths)

        print("\nCargando puntos al visor")
        
        #Solo cargar la segunda capa (edificios)
        shape = load_vector_to_napari(gpkg_paths[1], self.loader)

        self.finished.emit(shape)
        
        return shape
