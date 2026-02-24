from PySide6.QtCore import Signal
from logic.workers.base_worker import BaseWorker
from logic.image_loader import SatelliteLoader

class LoadImageWorker(BaseWorker):
    finished = Signal(object)

    def __init__(self, loader: SatelliteLoader, escala: int):
        super().__init__()
        self.loader = loader
        self.escala = escala

    def run(self):
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
        try:
            img = self.loader.get_preview(
                escala_input=self.escala,
                progress_callback=self.progress
            )
            self.finished.emit(img)
        except Exception as e:
            self.error.emit(str(e))