from pyproj import Transformer
import numpy as np

def cursor_to_coords(x_napari: float, y_napari: float, scaled_factor: float, transform, crs) -> tuple[float, float, float, float]:
        """
        Convierte coordenadas del cursor en Napari a coordenadas reales UTM y Lat/Lon.

        Args:
            x_napari: Coordenada x de la posición del cursor
            y_napari: Coordenada y de la posición del cursor
            
        Returns:
            tuple: (real_x, real_y, lat, lon)
        """
        real_x = x_napari / scaled_factor
        real_y = y_napari / scaled_factor

        utm_x, utm_y = transform * (real_x, real_y)

        # Convertir píxeles a coordenadas geográficas
        lat, lon = _pixel_to_latlon(real_x, real_y, transform, crs)

        return (utm_x, utm_y, lat, lon)

def _pixel_to_latlon(pixel_x: float, pixel_y: float, transform, crs) -> tuple[float, float]:
        """
        Convierte coordenadas de píxel a latitud/longitud.
        
        Args:
            pixel_x: Coordenada X en píxeles (imagen original)
            pixel_y: Coordenada Y en píxeles (imagen original)
        
        Returns:
            tuple: (lat, lon)
        """
        # Aplicar transformación afín del GeoTIFF
        x_geo, y_geo = transform * (pixel_x, pixel_y)
        
        # Reproyectar a WGS84 (Lat/Lon)
        transformer = Transformer.from_crs(
            crs, 
            "EPSG:4326", 
            always_xy=True #devuelve lon, lat
        )
        lon, lat = transformer.transform(x_geo, y_geo)
        
        return (lat, lon)

def get_rectangle_area_km2(original_shape, transform) -> float:
        dy = original_shape[0] 
        dx = original_shape[1]

        dy_real = dy * abs(transform.e)
        dx_real = dx * abs(transform.a)

        return (dy_real * dx_real)/ 1_000_000