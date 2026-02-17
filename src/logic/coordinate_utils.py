from pyproj import Transformer
import numpy as np

def cursor_to_coords(x_napari: float, y_napari: float, scale_factor: float, transform, crs) -> tuple[float, float, float, float]:
        """
        Convierte coordenadas del cursor en Napari a coordenadas reales UTM y Lat/Lon.

        Args:
            x_napari: Coordenada x de la posición del cursor
            y_napari: Coordenada y de la posición del cursor
            
        Returns:
            tuple: (real_x, real_y, lat, lon)
        """
        real_x = x_napari / scale_factor
        real_y = y_napari / scale_factor

        # Convertir píxeles a coordenadas geográficas
        lat, lon = _pixel_to_latlon(real_x, real_y, transform, crs)

        return (real_x, real_y, lat, lon)

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
            always_xy=True
        )
        lon, lat = transformer.transform(x_geo, y_geo)
        
        return (lat, lon)