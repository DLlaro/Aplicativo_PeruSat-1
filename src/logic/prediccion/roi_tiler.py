import os
import json
from tqdm import tqdm
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from shapely.geometry import box
from rasterio.transform import xy
from logic.image_loader import SatelliteLoader
import geopandas as gpd

from skimage.draw import polygon
from typing import Optional, TypeAlias, Callable

def roi_to_tiles(
    coords: tuple,
    tif_name: str,
    loader: SatelliteLoader,
    out_dir: str,
    polygon_coords = None,
    tile_size: int = 512,
    overlap: float = 0.5,
    nodata_threshold: float = 0.95,
    black_tile_threshold: float = 5.0,
    progress_callback = None 
):
    """
    Extrae el área del roi demarcado para normalizar y 
    generar los parches.

    Args
    ----------
    coords: tuple
        Tupla con los valores de x, y, w, h del área válida (intersección de imagen y ROI) del ROI
    tif_name: str
        Nombre del raster
    loader: str
        Loader de la imagen satelital
    out_dir: str
        Ruta de guardado de los parches
    tile_size: int
        Tamaño de los parches en pixeles
    overlap: float
        Porcentaje de cuanto se solapan los parches
    nodata_threshold: float
        Proporción antes de descartar parche
    black_tile_threshold: float
        Proporción de area oscura antes de descartar parche
    progress_callback: Callable[[int, str, bool], None] = None
        Funcion para la actualizacion de la barra de progreso
    """
    os.makedirs(out_dir, exist_ok=True)
    with rasterio.open(loader.path) as src:
        print(coords)
        x, y, W, H = coords
        bands = src.count
        transform = src.transform
        nodata_value = 0
        stride = int(tile_size * (1 - overlap))

        y_end = y + H
        x_end = x + W

        metadata = {
            "tile_size": tile_size,
            "overlap": overlap,
            "stride": stride,
            "tiles": [],
            "transform": list(transform),
            "crs": str(src.crs),
            "width": x_end,
            "height": y_end,
            "nodata_value": nodata_value
        }

        features = []
        i = 0 

        ys = range(y, y_end, stride)
        xs = range(x, x_end, stride)
        total_tiles = len(ys) * len(xs)
        
        with tqdm(total=total_tiles,
          desc=f"Tiling GeoTIFF {tif_name}") as pbar:
            for yi in ys:
                for xi in xs:
                    patch_id = f"{tif_name}_{i:06d}"

                    # Definimos la ventana teórica (puede estar fuera de los límites del TIF)
                    window = Window(xi, yi, tile_size, tile_size)
                    # LEER CON BOUNDLESS:
                    # Si xi o yi están fuera, o si la ventana excede el ancho/alto, 
                    # rasterio rellena automáticamente con fill_value (ceros).
                    tile = src.read(window=window, boundless=True, fill_value=0)

                    #ajustar coordenadas del polígono al sistema de referencia de la ventana
                    if polygon_coords is not None:
                        mask_ventana = np.zeros((tile_size, tile_size), dtype=bool)
                        coords_locales = polygon_coords - [yi, xi]
                        # Dibujar el polígono en la máscara de la ventana
                        # polygon() se encarga de calcular qué píxeles caen dentro
                        rr, cc = polygon(coords_locales[:, 0], coords_locales[:, 1], (tile_size, tile_size))
                        valid = (rr >= 0) & (rr < tile_size) & (cc >= 0) & (cc < tile_size)
                        mask_ventana[rr[valid], cc[valid]] = True
                        if not np.any(mask_ventana):
                            pbar.update(1)
                            continue

                        tile[:,~mask_ventana] = 0

                    # Calcular fracción de nodata
                    # Como el tile ya tiene el tamaño final, el cálculo es directo
                    if nodata_value is not None:
                        nodata_mask = np.all(tile == nodata_value, axis=0)
                        nodata_fraction = float(nodata_mask.mean())
                    else:
                        nodata_fraction = 0.0

                    if nodata_fraction > nodata_threshold:
                       pbar.update(1)
                       continue
                    if bands >= 3:
                        tile_rgb = np.stack([tile[0], tile[1], tile[2]], axis=-1)
                    else:
                        raise ValueError("TIF must have at least 3 bands (RGB).")

                    tile_rgb_8bit = loader._normalize_percentiles_per_band(tile_rgb, nodata_value)

                    # Detectar tiles negros
                    #mean_intensity = np.mean(tile_rgb_8bit)
                    #if mean_intensity < black_tile_threshold:
                    #    #print(f"Skipping tile_{patch_id} at ({x},{y}). Mean intensity {mean_intensity:.2f} < {black_tile_threshold}")
                    #    continue
                    
                    tile_transform = window_transform(window, src.transform)

                    tile_path = os.path.join(out_dir, f"patch_{patch_id}.tif")

                    profile = src.profile.copy()
                    profile.update({
                        "driver": "GTiff",
                        "height": tile_size,
                        "width": tile_size,
                        "transform": tile_transform,
                        "count": 3,
                        "dtype": rasterio.uint8,
                        "nodata": 0
                    })

                    with rasterio.open(tile_path, "w", **profile) as dst:
                        # rasterio usa (band, row, col)
                        dst.write(tile_rgb_8bit[:, :, 0], 1)
                        dst.write(tile_rgb_8bit[:, :, 1], 2)
                        dst.write(tile_rgb_8bit[:, :, 2], 3)


                    x_min, y_max = xy(transform, yi, xi, offset='ul')
                    x_max, y_min = xy(transform, yi + tile_size, xi + tile_size, offset='lr')

                    geom = box(x_min, y_min, x_max, y_max)

                    features.append({
                        "geometry": geom,
                        "tile_id": patch_id,
                        "img_path": os.path.basename(tile_path),
                        "pixel_x": xi,
                        "pixel_y": yi,
                        "nodata_frac": float(nodata_fraction)
                    })

                    metadata["tiles"].append({
                        "id": patch_id,
                        "x": xi,
                        "y": yi,
                        "path": tile_path,
                        "nodata_fraction": float(nodata_fraction)
                    })

                    i += 1
                    pbar.update(1)

                # Reportar progreso del tiling
                if progress_callback:
                    progress = int((pbar.n / total_tiles ) * 100)
                    progress_callback(progress, f"Generando tiles:")

    # ===== PASO 3: Guardar metadatos =====

    gdf = gpd.GeoDataFrame(
        features,
        crs = src.crs
    )
    gpkg_path = os.path.join(out_dir, "tiles_index.gpkg")
    gdf.to_file(gpkg_path, layer="tiles", driver="GPKG")

    with open(os.path.join(out_dir, "tiles_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    print("Tiling terminado.")
