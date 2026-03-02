import glob
import os
from typing import Callable, TypeAlias

import geopandas as gpd
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

ProgressCallback: TypeAlias = Callable[[int, str, str, bool], None]


def raster_to_vector(
    mask_path: str,
    out_dir: str,
    background_value: int = 0,
    progress_callback: ProgressCallback = None,
):
    """
    Convierte mascaras raster en capas vectoriales GPKG.
    """
    os.makedirs(out_dir, exist_ok=True)

    if progress_callback:
        progress_callback(0, "Vectorizando...")

    path_list = []
    tif_paths = sorted(glob.glob(os.path.join(mask_path, "*.tif")))
    total = len(tif_paths)

    for count, tif in enumerate(tif_paths, start=1):
        nombre = os.path.splitext(os.path.basename(tif))[0]
        salida = os.path.join(out_dir, f"{nombre}.gpkg")

        with rasterio.open(tif) as src:
            mask = src.read(1)
            transform = src.transform
            crs = src.crs

        mask_bool = mask != background_value
        shapes_generator = shapes(mask, mask=mask_bool, transform=transform)
        geoms = [
            {"geometry": shape(geom), "class_value": int(value)}
            for geom, value in shapes_generator
        ]

        if geoms:
            gdf = gpd.GeoDataFrame(geoms, crs=crs)
        else:
            gdf = gpd.GeoDataFrame(columns=["class_value", "geometry"], geometry="geometry", crs=crs)

        gdf.to_file(salida, driver="GPKG")
        print(f"Vectorizado guardado en {salida}")
        path_list.append(salida)

        if progress_callback and total > 0:
            progress = int((count / total) * 100)
            progress_callback(progress, "Generando capa vectorial:")

    return path_list
