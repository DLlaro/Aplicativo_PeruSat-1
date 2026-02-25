import glob
import os
import rasterio
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape
import numpy as np

from typing import TypeAlias, Callable

ProgressCallback: TypeAlias = Callable[[int, str, str, bool], None]

def raster_to_vector(mask_path: str, 
                     out_dir: str, 
                     background_value: int = 0, 
                     progress_callback: ProgressCallback = None):
    """
    Convierte una máscara raster a un vector (GPKG o Shapefile).

    Args
    ----------
    mask_path: str
        Ruta al archivo raster de la máscara.
    out_dir: str
        Directorio donde guardar los archivos vectoriales (GPKG).
    background_value: int
        Valor del fondo a ignorar (por defecto 0).

    Return
    ----------
    path_list: dict
        Diccionario con las rutas de los archivos gpkg creados
    """
    os.makedirs(out_dir, exist_ok=True)

    count = 0

    if progress_callback:
        progress_callback(0, "Vectorizando...")

    path_list = []

    for tif in glob.glob(f"{mask_path}/*.tif"):
        nombre = os.path.splitext(os.path.basename(tif))[0]
        salida = f"{out_dir}/{nombre}.gpkg"
        with rasterio.open(tif) as src:
            mask = src.read(1)
            transform = src.transform
            crs = src.crs

        # Crear máscara booleana ignorando el fondo
        mask_bool = mask != background_value
        shapes_generator = shapes(mask, mask=mask_bool, transform=transform)

        # Convertir a GeoDataFrame
        geoms = [{'geometry': shape(geom), 'class_value': int(value)} 
                for geom, value in shapes_generator]

        gdf = gpd.GeoDataFrame(geoms, crs=crs)

        # Guardar a archivo vectorial
        gdf.to_file(f"{salida}", driver="GPKG")
        print(f"Vectorizado guardado en {salida}")
        path_list.append(salida)

        count += 1

        if progress_callback:
                progress = int((count / len(glob.glob(f"{mask_path}/*.tif"))) * 100)
                progress_callback(progress, f"Generando capa vectorial:")

    return path_list