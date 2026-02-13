from PySide6.QtCore import QThread, Signal
import rasterio

class LoadWorker(QThread):
    # En PySide6 se usa Signal en lugar de pyqtSignal
    metadata_ready = Signal(int, int)  # Envía W, H
    finished = Signal(object)         # Envía la imagen (numpy array)
    error = Signal(str)               # Envía el error
    progress_update = Signal(int) # Nueva señal para el % real

    def __init__(self, loader, file_path, escala):
        super().__init__()
        self.loader = loader
        self.file_path = file_path
        self.escala = escala

    def run(self):
        try:
            # 1. Metadatos (0-10%)
            self.progress_update.emit(5)
            
            # Necesitamos abrir el archivo y LEER los datos
            with rasterio.open(self.file_path) as src:
                # Sincronizamos los metadatos en el loader para cálculos futuros
                self.loader.path = self.file_path
                self.loader.transform = src.transform
                self.loader.crs = src.crs
                
                scale = 1.0 / self.escala if self.escala > 0 else 1.0
                self.loader.scale_factor = scale
                
                new_h = int(src.height * scale)
                new_w = int(src.width * scale)
                self.metadata_ready.emit(new_w, new_h)
                self.progress_update.emit(10)

                # --- ESTO ES LO QUE FALTABA ---
                # 2. Lectura de píxeles (10-40%)
                # Aquí 'data' será un array de numpy con los números de la imagen
                data = src.read(
                    [1, 2, 3], # Bandas R, G, B
                    out_shape=(3, new_h, new_w),
                    resampling=rasterio.enums.Resampling.bilinear
                )
                self.progress_update.emit(40)

            # 3. Normalización (40-100%)
            def calc_total_progress(p):
                total = 40 + int(p * 0.6)
                self.progress_update.emit(total)
                
            # AHORA SÍ: pasamos 'data' (el array), NO la ruta (string)
            img_vis = self.loader._normalize_image(data, progress_callback=calc_total_progress)
            
            self.finished.emit(img_vis)
            
        except Exception as e:
            self.error.emit(str(e))