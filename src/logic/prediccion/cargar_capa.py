import numpy as np
import geopandas as gpd
from affine import Affine

def load_vector_to_napari(file_path, loader):


    gdf = gpd.read_file(file_path)
    
    # 1. Obtener la matriz original
    aff_original = loader.transform 
    
    # 2. AJUSTE CRÍTICO: Modificar la matriz según la escala del preview
    # 'loader.scale_factor' es el factor que calculaste (ej: 0.2 para escala 5)
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