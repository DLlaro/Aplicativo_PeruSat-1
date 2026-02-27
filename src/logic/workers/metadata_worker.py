from PySide6.QtCore import Signal
from logic.workers.base_worker import BaseWorker
from logic.image_loader import SatelliteLoader

class MetadataWorker(BaseWorker):
    finished = Signal(tuple)

    def __init__(self, loader: SatelliteLoader, file_path: str):
        super().__init__()
        self.loader = loader
        self.file_path = file_path

    def run(self):
        """
        Lee el metadata de la imagen
        
        Emit
        ----------
        shape: tuple
            Tupla con los valores alto (height) y ancho (width) del raster
        """
        try:
            shape = self.loader.load_metadata(self.file_path)
            self.finished.emit(shape)
        except Exception as e:
            self.error.emit(str(e))