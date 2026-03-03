from PySide6.QtCore import Signal

from logic.prediccion.vincular_ccpp import link_buildings_to_ccpp
from logic.workers.base_worker import BaseWorker


class CCPPLinkWorker(BaseWorker):
    finished = Signal(object)

    def __init__(
        self,
        buildings_path: str,
        ccpp_points_path: str,
        output_dir: str,
        prediction_raster_path: str | None = None,
    ):
        super().__init__()
        self.buildings_path = buildings_path
        self.ccpp_points_path = ccpp_points_path
        self.output_dir = output_dir
        self.prediction_raster_path = prediction_raster_path

    def run(self):
        try:
            result = link_buildings_to_ccpp(
                buildings_path=self.buildings_path,
                ccpp_points_path=self.ccpp_points_path,
                output_dir=self.output_dir,
                prediction_raster_path=self.prediction_raster_path,
                progress_callback=lambda value, msg: self.progress(value, msg),
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
