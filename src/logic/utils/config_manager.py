from PySide6.QtCore import QSettings
import os
import json
import sys

class AppConfig:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(AppConfig, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # --- DETECTOR DE RUTA
        if getattr(sys, 'frozen', False):
            # Si es un EXE, la base es donde está el ejecutable
            self.base_path = os.path.dirname(sys.executable)
            os.environ['GDAL_DATA'] = os.path.join(sys._MEIPASS, 'rasterio', 'gdal_data')
            os.environ['PROJ_LIB'] = os.path.join(sys._MEIPASS, 'rasterio', 'proj_data')
        else:
            # Si es código fuente (.py), la base es la raíz del proyecto
            # Subimos niveles si es necesario según dónde esté este archivo
            self.base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

        # El config.ini siempre debe estar al lado del ejecutable para que sea persistente
        ruta_config = os.path.join(self.base_path, "config.ini")
        
        self.settings = QSettings(ruta_config, QSettings.IniFormat)
        print(f"Configuración cargada desde: {ruta_config}")
        self._initialized = True

    @property
    def model_path(self):
        # Ruta por defecto dinámica (basada en donde se instaló la app)
        default_model = os.path.join(self.base_path, "logic", "modelo", "mi_modelo.h5")
        return self.settings.value("model/path", default_model)

    @model_path.setter
    def model_path(self, value):
        self.settings.setValue("model/path", value)

    @property
    def use_gpu(self):
        return str(self.settings.value("gpu/use_gpu", "False")).lower() == "true"

    @use_gpu.setter
    def use_gpu(self, value):
        self.settings.setValue("gpu/use_gpu", value)

    @property
    def gpu_info(self):
        # 1. Obtenemos el valor (por defecto un string de dict vacío '{}')
        data_str = self.settings.value("gpu/gpu_info", "{}")
        try:
            # 2. Convertimos el string JSON de vuelta a un diccionario de Python
            return json.loads(data_str)
        except (json.JSONDecodeError, TypeError):
            return {}

    @gpu_info.setter
    def gpu_info(self, value):
        if value is None:
            value = {"gpu_name": "CPU", "total_mb": 0, "libre_mb": 0, "usado_mb": 0}
        if isinstance(value, dict):
            self.settings.setValue("gpu/gpu_info", json.dumps(value))
        else:
            print("Error: El valor debe ser un diccionario.")

    @property
    def gpu_memory_growth(self):
        return str(self.settings.value("gpu/growth", "False")).lower() == "true"

    @gpu_memory_growth.setter
    def gpu_memory_growth(self, value):
        self.settings.setValue("gpu/growth", value)

    @property
    def logo_path(self):
        # Ejemplo de cómo obtener el logo siempre bien
        return os.path.join(self.base_path, "assets", "inei_logo.png")

settings = AppConfig()