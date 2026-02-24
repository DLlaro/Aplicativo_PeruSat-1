import numpy as np
import geopandas as gpd
from affine import Affine
from logic.image_loader import SatelliteLoader

def load_vector_to_napari(gpkg_path: str = None, loader: SatelliteLoader = None):
    """
    Transforma una capa vectorial a coordenadas de píxel relativas al preview del visor.

    Lee un archivo GeoPackage, reproyecta las geometrías al sistema de coordenadas
    de píxel de la imagen de previsualización aplicando la escala del loader,
    y retorna las formas listas para renderizar en Napari.

    Args
    ----------
    gpkg_path : str
        Ruta al archivo GeoPackage (.gpkg) con las geometrías a transformar.
    loader : SatelliteLoader
        Instancia del loader con la imagen actualmente cargada. Se accede a:
        - loader.transform: 
            matriz affine original del raster.
        - loader.scale_factor: 
            factor de escala aplicado al preview(ej: 0.2 para escala 5).

    Return
    -------
    dict:
        - type: 'shapes'
        - data: list[np.ndarray] — coordenadas en píxeles (row, col)de cada polígono, listas para Napari.
        - shape_type: 'polygon'

    Notas
    -----
    - La matriz affine se re-escala según `1 / loader.scale_factor` para que
      las coordenadas geográficas mapeen correctamente al espacio de la preview
      y no al raster original.
    - Las geometrías vacías (`geom.is_empty`) son ignoradas.
    - Las coordenadas se convierten de (x, y) geográfico a (row, col) de píxel
      invirtiendo los ejes para cumplir con la convención de Napari.
    """
    gdf = gpd.read_file(gpkg_path)
    
    # 1. Obtener la matriz original
    aff_original = loader.transform 
    
    # 2. AJUSTE CRÍTICO: Modificar la matriz según la escala del preview
    # Re-escalamos la matriz para que coincida con la imagen pequeña
    factor = 1.0 / loader.scale_factor # Esto nos da el "salto" de píxeles (ej: 5)
    
    # La nueva matriz tiene píxeles más grandes (multiplicamos ancho y alto de píxel)
    aff_scaled = aff_original * Affine.scale(factor, factor)
    
    # 3. Inversa de la matriz re-escalada
    inv_transform = ~aff_scaled
    
    shapes_in_pixels = []
    for geom in gdf.geometry:
        if geom.is_empty: continue
        
        coords = np.array(geom.exterior.coords)
        # Ahora inv_transform nos dará coordenadas relativas a la PREVIEW
        pixel_coords = [inv_transform * (x, y) for x, y in coords]
        
        napari_coords = np.array([[p[1], p[0]] for p in pixel_coords])
        shapes_in_pixels.append(napari_coords)
        
    return {
        'type': 'shapes',
        'data': shapes_in_pixels,
        'shape_type': 'polygon'
    }