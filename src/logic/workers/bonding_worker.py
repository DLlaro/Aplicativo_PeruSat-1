from PySide6.QtCore import Signal
from logic.workers.base_worker import BaseWorker
from logic.image_loader import SatelliteLoader

class BondingWorker(BaseWorker):
    finished = Signal(object)

    def __init__(self, loader: SatelliteLoader, escala: int):
        super().__init__()
        self.loader = loader
        self.escala = escala

    def run(self):
        return