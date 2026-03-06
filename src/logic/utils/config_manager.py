from PySide6.QtCore import QSettings
import os
import json
import sys
import torch

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

        # --- GESTIÓN DE RUTAS ---
        if getattr(sys, 'frozen', False):
            # En el EXE: base_path es la carpeta donde está el ejecutable (para el .ini)
            self.base_path = os.path.dirname(sys.executable)
            # internal_path es donde están los assets y el código (sys._MEIPASS)
            self.internal_path = sys._MEIPASS 
        else:
            # En desarrollo (.py): ambas son la raíz del proyecto
            self.base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            self.internal_path = self.base_path

        # El config.ini se guarda siempre fuera del paquete para ser persistente
        ruta_config = os.path.join(self.base_path, "config.ini")
        self.settings = QSettings(ruta_config, QSettings.IniFormat)
        
        print(f"Configuración cargada desde: {ruta_config}")
        self._initialized = True

    @property
    def model_path(self):
        # Ruta por defecto dinámica (basada en donde se instaló la app)
        default_model = os.path.join(self.base_path, "logic", "modelo", "mi_modelo.pth")
        return self.settings.value("model/path", default_model)

    @model_path.setter
    def model_path(self, value):
        self.settings.setValue("model/path", value)

    @property
    def model_encoder(self):
        valid_encoders = {"resnet34", "resnet50"}
        value = str(self.settings.value("model/encoder", "")).strip().lower()
        if value in valid_encoders:
            return value

        # Fallback heuristico para configuraciones antiguas sin `model/encoder`.
        model_name = os.path.basename(str(self.model_path)).lower()
        if "resnet50" in model_name:
            return "resnet50"
        return "resnet34"

    @model_encoder.setter
    def model_encoder(self, value):
        valid_encoders = {"resnet34", "resnet50"}
        normalized = str(value).strip().lower()
        self.settings.setValue(
            "model/encoder",
            normalized if normalized in valid_encoders else "resnet34",
        )

    @property
    def use_gpu_inference(self):
        return str(self.settings.value("gpu/use_gpu_inference", "False")).lower() == "true"

    @use_gpu_inference.setter
    def use_gpu_inference(self, value):
        self.settings.setValue("gpu/use_gpu_inference", value)

    @property
    def unlock_render(self):
        return str(self.settings.value("unlock_render", "False")).lower() == "true"

    @unlock_render.setter
    def unlock_render(self, value):
        self.settings.setValue("unlock_render", value)

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
    def max_render(self):
        return int(self.settings.value("max_render", 10000))
    
    @max_render.setter
    def max_render(self, value):
        self.settings.setValue("max_render", value)
        
    @property
    def torch_device(self):
        return torch.device('cuda' if torch.cuda.is_available() and settings.use_gpu_inference else 'cpu')

    @property
    def logo_path(self):
        return os.path.join(self.internal_path, "assets", "inei_logo.ico")
    
    @property
    def logo_path_png(self):
        return os.path.join(self.internal_path, "assets", "inei_logo.png")
    
    @property
    def qss_path(self):
        return os.path.join(self.internal_path, "assets", "styles", "style.qss")

settings = AppConfig()
