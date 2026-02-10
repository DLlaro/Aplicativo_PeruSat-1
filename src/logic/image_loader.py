import rasterio
from rasterio.enums import Resampling
import numpy as np

class SatelliteLoader:
    def __init__(self):
        self.src = None  # Guardamos la referencia al archivo abierto si la necesitamos luego
        self.path = None
        self.scale_factor = 1.0 # Cuánto redujimos la imagen

    def get_preview(self, file_path, target_width=5000, bands=[1, 2, 3]):
        """
        Lee una vista previa (downsampled) de la imagen para visualización rápida.
        Devuelve una imagen lista para Napari (Y, X, B) normalizada 0-255 uint8.
        """
        self.path = file_path
        
        try:
            with rasterio.open(file_path) as src:
                # 1. Calcular factor de escala para no explotar la RAM
                self.scale_factor = target_width / src.width
                if self.scale_factor > 1: self.scale_factor = 1
                
                new_h = int(src.height * self.scale_factor)
                new_w = int(src.width * self.scale_factor)
                
                print(f"[Logic] Leyendo {file_path} a resolución {new_w}x{new_h}...")

                # 2. Leer datos
                data = src.read(
                    bands,
                    out_shape=(len(bands), new_h, new_w),
                    resampling=Resampling.bilinear
                )
                
                # 3. Procesamiento Numérico (Normalización + NoData)
                img_vis = self._normalize_image(data)

                self.transform = src.transform
                self.crs = src.crs    
                return img_vis

        except Exception as e:
            print(f"Error en loader: {e}")
            raise e
        
    def pixel_to_coords(self, x_napari, y_napari):
        """
        Convierte coordenadas de la vista previa (Napari) a coordenadas reales (Lat/Lon o UTM).
        """
        if self.transform is None:
            return (0, 0)

        # 1. Deshacer el downsampling (Volver al tamaño original)
        x_real = x_napari / self.scale_factor
        y_real = y_napari / self.scale_factor

        # 2. Aplicar la matriz afín del GeoTIFF
        # La multiplicación matricial convierte (col, row) -> (x_geo, y_geo)
        x_geo, y_geo = self.transform * (x_real, y_real)
        
        return x_geo, y_geo

    def _normalize_image(self, data):
        """
        Normaliza cada banda independientemente (Stretch Histogram por canal).
        Entrada: (Bandas, Y, X)
        Salida: (Y, X, Bandas) normalizado 0-1 (o 0-255 si prefieres)
        """
        # 1. Crear contenedor vacío para el resultado (float para precisión)
        # Mantenemos la forma (Bandas, Y, X) para iterar fácil
        normalized_bands = np.zeros_like(data, dtype=np.float32)

        # 2. Iterar sobre cada banda (0=R, 1=G, 2=B)
        for i in range(data.shape[0]):
            band = data[i].astype(np.float32)
            
            # Máscara de datos válidos para ESTA banda
            valid_mask = band > 0
            
            if valid_mask.any():
                # Calcular percentiles SOLO de esta banda
                # Esto equilibra los colores (White Balancing automático)
                p2, p98 = np.percentile(band[valid_mask], (2, 98))
                
                # Clip (cortar extremos)
                band_clipped = np.clip(band, p2, p98)
                
                # Escalar de p2..p98 a 0..1
                denominador = p98 - p2
                if denominador == 0: denominador = 1  # Evitar div/0
                
                band_norm = (band_clipped - p2) / denominador
                
                # Limpiar el fondo (NoData) de nuevo
                band_norm[~valid_mask] = 0
                
                normalized_bands[i] = band_norm
            else:
                # Si la banda es todo 0 (negra)
                normalized_bands[i] = 0

        # 3. Transponer al final para Napari: (Bandas, Y, X) -> (Y, X, Bandas)
        img_final = np.transpose(normalized_bands, (1, 2, 0))
        
        return img_final