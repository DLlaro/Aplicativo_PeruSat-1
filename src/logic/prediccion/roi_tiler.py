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

from skimage.draw import polygon as skpolygon
from typing import TypeAlias, Callable

ProgressCallback: TypeAlias = Callable[[int, str, str, bool], None]

def roi_to_tiles(
    polygon: np.ndarray,
    scale_factor: float,
    tif_name: str,
    loader: SatelliteLoader,
    out_dir: str,
    tile_size: int = 512,
    overlap: float = 0.5,
    nodata_threshold: float = 0.9,
    black_tile_threshold: float = 5.0,
    progress_callback: ProgressCallback = None 
    ) -> None:
    """
    Extrae el área del roi demarcado para normalizar y 
    generar los parches.

    Args
    ----------
    coords: tuple
        Tupla con los valores de x, y, w, h del área válida (intersección de imagen y ROI) del ROI
    tif_name: str
        Nombre del raster
    tif_path: str
        Ruta de ubicacion del archivo raster
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
    progress_callback: Callable[[int, str, str, bool], None]
        Funcion para la actualizacion de la barra de progreso
    """
    print("scale factor", scale_factor)

    os.makedirs(out_dir, exist_ok=True)

    if progress_callback:
        progress_callback(0, "Generando tiles...")

    polygon_raster = polygon.copy().astype(float)
    polygon_raster[:, 0] *= scale_factor  # filas
    polygon_raster[:, 1] *= scale_factor  # cols

    polygon = np.round(polygon_raster).astype(int)

    with rasterio.open(loader.path) as src:
        min_row = max(0, int(np.floor(polygon[:, 0].min())))
        max_row = min(src.height, int(np.ceil(polygon[:, 0].max())) + 1)
        min_col = max(0, int(np.floor(polygon[:, 1].min())))
        max_col = min(src.width, int(np.ceil(polygon[:, 1].max())) + 1)

        x = min_col
        y = min_row
        W = max_col - min_col
        H = max_row - min_row
        if W <= 0 or H <= 0:
            raise ValueError("El poligono seleccionado no intersecta la imagen.")

        nodata_value = 0
        stride = max(1, int(tile_size * (1 - overlap)))

        y_end = y + H
        x_end = x + W

        metadata = {
            "tile_size": tile_size,
            "overlap": overlap,
            "stride": stride,
            "tiles": [],
            "transform": list(loader.transform),
            "crs": str(loader.crs),
            "width": x_end,
            "height": y_end,
            "nodata_value": nodata_value
        }

        features = []
        i = 0 

        ys = list(range(y, y_end, stride))
        xs = list(range(x, x_end, stride))
        if not ys:
            ys = [y]
        if not xs:
            xs = [x]

        last_y = max(y, y_end - tile_size)
        last_x = max(x, x_end - tile_size)
        if ys[-1] != last_y:
            ys.append(last_y)
        if xs[-1] != last_x:
            xs.append(last_x)

        total_tiles = len(ys) * len(xs)
        height = H
        width = W

        shifted_polygon = polygon.copy()
        shifted_polygon[:,0] -= min_row
        shifted_polygon[:,1] -= min_col

        mask = np.zeros((height, width), dtype=bool)

        rr, cc = skpolygon(
            shifted_polygon[:,0],
            shifted_polygon[:,1],
            mask.shape
        )

        mask[rr, cc] = True
        
        with tqdm(total= total_tiles, desc= f"Tiling GeoTIFF {tif_name}") as pbar:
            for yi in ys:
                for xi in xs:
                    patch_id = f"{tif_name}_{i:06d}"
                    # Definimos la ventana teórica (puede estar fuera de los límites del TIF)
                    window = Window(xi, yi, tile_size, tile_size)

                    mask_y0 = yi - min_row
                    mask_x0 = xi - min_col
                    mask_y1 = mask_y0 + tile_size
                    mask_x1 = mask_x0 + tile_size

                    # Intersección real con límites de máscara
                    y0 = max(mask_y0, 0)
                    x0 = max(mask_x0, 0)
                    y1 = min(mask_y1, mask.shape[0])
                    x1 = min(mask_x1, mask.shape[1])

                    if y0 >= y1 or x0 >= x1:
                        pbar.update(1)
                        continue

                    local_mask = np.zeros((tile_size, tile_size), dtype=bool)

                    # Coordenadas dentro del tile
                    tile_y0 = y0 - mask_y0
                    tile_x0 = x0 - mask_x0
                    tile_y1 = tile_y0 + (y1 - y0)
                    tile_x1 = tile_x0 + (x1 - x0)

                    # Copiar máscara global → máscara local
                    local_mask[tile_y0:tile_y1, tile_x0:tile_x1] = mask[y0:y1, x0:x1]

                    # Si no hay área válida real
                    if not local_mask.any():
                        pbar.update(1)
                        continue

                    # LEER CON BOUNDLESS: 
                    # Si xi o yi están fuera, o si la ventana excede el ancho/alto, 
                    # rasterio rellena automáticamente con fill_value (ceros).
                    tile = src.read(window=window, boundless=True, fill_value=0)

                    # Calcular fracción de nodata
                    # Como el tile ya tiene el tamaño final, el cálculo es directo
                    if nodata_value is not None:
                        nodata_mask = np.all(tile == nodata_value, axis=0)
                        nodata_fraction = float(nodata_mask.mean())
                    else:
                        nodata_fraction = 0.0

                    #if nodata_fraction > nodata_threshold:
                    #    continue
                    if len(loader.bands) >= 3:
                        tile_rgb = np.stack([tile[0], tile[1], tile[2]], axis=-1)
                    else:
                        raise ValueError("TIF must have at least 3 bands (RGB).")

                    tile_rgb_8bit = loader._normalize_percentiles_per_band(
                        tile_rgb,
                        nodata_value=nodata_value
                    )

                    tile_rgb_8bit[~local_mask] = 0

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
                        "count": len(loader.bands),
                        "dtype": rasterio.uint8,
                        "nodata": 0
                    })

                    with rasterio.open(tile_path, "w", **profile) as dst:
                        # rasterio usa (band, row, col)
                        dst.write(tile_rgb_8bit[:, :, 0], 1)
                        dst.write(tile_rgb_8bit[:, :, 1], 2)
                        dst.write(tile_rgb_8bit[:, :, 2], 3)

                    x_min, y_max = xy(loader.transform, yi, xi, offset='ul')
                    x_max, y_min = xy(loader.transform, yi + tile_size, xi + tile_size, offset='lr')

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
                    progress = int((pbar.n / total_tiles) * 100)
                    progress_callback(progress, "Generando tiles...")

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
