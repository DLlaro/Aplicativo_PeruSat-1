import rasterio
from rasterio.enums import Resampling
import numpy as np
from pyproj import Transformer
from rasterio import windows

class SatelliteLoader:
    def __init__(self):
        self.original_shape = None
        self.transform = None
        self.src = None  # Guardamos la referencia al archivo abierto si la necesitamos luego
        self.path = None
        self.scale_factor = 1.0 # Cuánto redujimos la imagen
    
    ### Update: Esta funcion es manejada por el load_worker
    def get_preview(self, file_path, input_escala=5, bands=[1, 2, 3]):
        """
        Lee una vista previa (downsampled) de la imagen para visualización rápida.
        Devuelve una imagen lista para Napari (Y, X, B) normalizada 0-255 uint8.
        """
        self.path = file_path
        
        try:
            with rasterio.open(file_path) as src:
                self.original_shape = (src.height, src.width) 

                # 1. Calcular factor de escala para no explotar la RAM
                if input_escala > 0:
                    self.scale_factor = 1.0 / input_escala
                else:
                    self.scale_factor = 1.0  # Por defecto resolución nativa
                
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
        
    def _normalize_image(self, data, progress_callback= None):
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
            valid_mask = (band > 0) & (band < 4095)
            
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
            
            # Notificar progreso: Por ejemplo, si son 3 bandas, 
            # cada una representa el 33% del proceso de normalización.
            if progress_callback:
                # Calculamos el porcentaje basado en la banda actual
                valor = int(((i + 1) / data.shape[0]) * 100)
                progress_callback(valor)

        # 3. Transponer al final para Napari: (Bandas, Y, X) -> (Y, X, Bandas)
        img_final = np.transpose(normalized_bands, (1, 2, 0))
        
        return img_final
    
    def cursor_to_coords(self, x_napari: float, y_napari: float) -> tuple[float, float, float, float]:
        """
        Convierte coordenadas del cursor en Napari a coordenadas reales UTM y Lat/Lon.

        Args:
            x_napari: Coordenada x de la posición del cursor
            y_napari: Coordenada y de la posición del cursor
            
        Returns:
            tuple: (real_x, real_y, lat, lon)
        """
        real_x = x_napari / self.scale_factor
        real_y = y_napari / self.scale_factor

        # Convertir píxeles a coordenadas geográficas
        lat, lon = self._pixel_to_latlon(real_x, real_y)

        return (real_x, real_y, lat, lon)
    
    def _pixel_to_latlon(self, pixel_x: float, pixel_y: float) -> tuple[float, float]:
        """
        Convierte coordenadas de píxel a latitud/longitud.
        
        Args:
            pixel_x: Coordenada X en píxeles (imagen original)
            pixel_y: Coordenada Y en píxeles (imagen original)
        
        Returns:
            tuple: (lat, lon)
        """
        # Aplicar transformación afín del GeoTIFF
        x_geo, y_geo = self.transform * (pixel_x, pixel_y)
        
        # Reproyectar a WGS84 (Lat/Lon)
        transformer = Transformer.from_crs(
            self.crs, 
            "EPSG:4326", 
            always_xy=True
        )
        lon, lat = transformer.transform(x_geo, y_geo)
        
        return (lat, lon)

    def roi_to_coords(self, layer) -> tuple[float, float, float, float]:
        """
        Extrae las coordenadas y dimensiones reales del ROI desde la capa.
        
        Args:
            layer: Capa de shapes de Napari
        
        Returns:
            tuple: (real_x, real_y, real_w, real_h)
        """
        shape_data = layer.data[-1]
        shape_data = np.array(shape_data)

         # shape_data tiene forma (n_vertices, 2) donde cada fila es [y, x]
        y_coords = shape_data[:, 0]
        x_coords = shape_data[:, 1]
        
        y_min, y_max = y_coords.min(), y_coords.max()
        x_min, x_max = x_coords.min(), x_coords.max()
        
        real_x = int(x_min / self.scale_factor)
        real_y = int(y_min / self.scale_factor)
        real_w = int((x_max - x_min) / self.scale_factor)
        real_h = int((y_max - y_min) / self.scale_factor)
        
        return (real_x, real_y, real_w, real_h)
    
    def validar_roi(self, real_x, real_y, real_w, real_h, min_area_km2=10):
        """
        Valida que el ROI sea válido para análisis.
        
        Args:
            real_x: Coordenada X de la esquina superior izquierda
            real_y: Coordenada Y de la esquina superior izquierda
            real_w: Ancho del ROI en píxeles
            real_h: Alto del ROI en píxeles
            min_area: Área mínima requerida en píxeles cuadrados
            
        Returns:
            tuple: (es_valido: bool, mensaje_error: str)
        """
        # 1. Verificar área mínima
        RES_IMAGEN = 0.7 #0.7 metros

        # Área en kilómetros cuadrados (1 km2 = 1,000,000 m2)
        area_m2 = real_w * real_h* RES_IMAGEN**2
        area_km2 = area_m2 / 1_000_000 
        
        if area_km2 < min_area_km2 :
            return (False, f"El ROI es demasiado pequeño ({area_km2:.2f} km²). "
                    f"Área mínima requerida: {min_area_km2:.2f} km²")
        
        # 2. Verificar que el ROI esté dentro de los límites de la imagen
        img_height, img_width = self.original_shape

        # Verificar que las coordenadas sean válidas
        if real_x < 0 or real_y < 0:
            return (False, f"Coordenadas negativas: x={real_x}, y={real_y}")

        if real_x >= img_width or real_y >= img_height:
            return (False, f"ROI fuera de imagen: inicio ({real_x},{real_y}) vs límites ({img_width},{img_height})")

        if real_x + real_w > img_width or real_y + real_h > img_height:
            return (False, f"ROI excede límites: fin ({real_x+real_w},{real_y+real_h}) vs límites ({img_width},{img_height})")

        if real_w <= 0 or real_h <= 0:
            return (False, f"Dimensiones inválidas: ancho={real_w}, alto={real_h}")
        
        return (True, f"{area_km2:.2f}")