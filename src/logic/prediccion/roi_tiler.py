import os
import json
from tqdm import tqdm
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from shapely.geometry import box
from rasterio.transform import xy
import geopandas as gpd

def compute_global_percentiles_stream_per_band(tif_path: str, coords: tuple, pmin=2, pmax=98, bands=[1,2,3], nbins=10000, progress_callback = None):
    with rasterio.open(tif_path) as src:
        x, y, h, w = coords
        nodata = 0
        block_size = 1024
        n_bands = len(bands)
        
        # Min/max por banda
        global_min = np.full(n_bands, np.inf)
        global_max = np.full(n_bands, -np.inf)

        y_end = y + h
        x_end = x + w
        
        ys = range(y, y+h, block_size)
        xs = range(x, x+w, block_size)
        total_tiles = len(ys) * len(xs)

        current_tile = 0
        # ===== SUB-PASO 1: Calcular min/max =====
        with tqdm(total=total_tiles,
          desc=f"Computing percentiles for GeoTIFF {tif_path}") as pbar:
            for yi in ys:
                for xi in xs:
                    win = Window(xi, yi, min(block_size, x_end-xi), min(block_size, y_end-yi))
                    block = src.read(bands, window=win).astype(np.float32)  # shape: (n_bands, rows, cols)
                    
                    for b in range(n_bands):
                        band_data = block[b]
                        if nodata is not None:
                            valid_values = band_data[band_data != nodata]
                        else:
                            valid_values = band_data.flatten()
                        
                        if valid_values.size > 0:
                            global_min[b] = min(global_min[b], valid_values.min())
                            global_max[b] = max(global_max[b], valid_values.max())
                    pbar.update(1)

                    current_tile += 1
                    # Progreso: 0-50% (primera mitad)
                    if progress_callback:
                        progress = int((current_tile / total_tiles) * 50)
                        progress_callback(progress, 100, f"Calculando rango")
        
        # Histograma por banda
        hist = np.zeros((n_bands, nbins), dtype=np.int64)
        bin_edges = [np.linspace(global_min[b], global_max[b], nbins+1) for b in range(n_bands)]

        current_tile = 0
        # ===== SUB-PASO 2: Construir histograma =====
        with tqdm(total=total_tiles,
          desc=f"Computing histogrram for GeoTIFF {tif_path}") as pbar:
            for yi in ys:
                for xi in xs:
                    win = Window(xi, yi, min(block_size, x_end-xi), min(block_size, y_end-yi))
                    block = src.read(bands, window=win).astype(np.float32)
                    
                    for b in range(n_bands):
                        band_data = block[b]
                        if nodata is not None:
                            values = band_data[band_data != nodata]
                        else:
                            values = band_data.flatten()
                        
                        hist_block, _ = np.histogram(values, bins=bin_edges[b])
                        hist[b] += hist_block
                    pbar.update(1)

                    current_tile += 1
                
                    # Progreso: 50-100% (segunda mitad)
                    if progress_callback:
                        progress = 50 + int((current_tile / total_tiles) * 50)
                        progress_callback(progress, 100, f"Calculando histograma")
        
        # Percentiles por banda
        lo = np.zeros(n_bands)
        hi = np.zeros(n_bands)
        
        for b in range(n_bands):
            cdf = np.cumsum(hist[b])
            if cdf[-1] == 0:
                lo[b], hi[b] = 0, 0
                continue
            cdf = cdf / cdf[-1]  # Normalizar a [0,1]
            idx_lo = np.searchsorted(cdf, pmin/100)
            idx_hi = np.searchsorted(cdf, pmax/100)
            lo[b] = bin_edges[b][min(idx_lo, len(bin_edges[b])-1)]
            hi[b] = bin_edges[b][min(idx_hi, len(bin_edges[b])-1)]
    
    return lo, hi  # Ahora son arrays de n_bands elementos

def normalize_percentiles_per_band(x: np.ndarray, lo: np.ndarray, hi: np.ndarray, nodata_value=0):
    """x shape: (height, width, n_bands)"""
    x = x.astype(np.float32)
    x_norm = np.zeros_like(x)
    
    for b in range(x.shape[-1]):
        band = x[..., b]
        if nodata_value is not None:
            valid = band != nodata_value
            x_norm[..., b][valid] = np.clip((band[valid] - lo[b]) / (hi[b] - lo[b] + 1e-6), 0, 1)
        else:
            x_norm[..., b]= np.clip((band - lo[b]) / (hi[b] - lo[b] + 1e-6), 0, 1)
    
    out = (x_norm * 254+1).astype(np.uint8)## convertir valores cercanos a 0 a 1 para que no sean tratados como nodata
    
    if nodata_value is not None:
        valid_mask = np.all(x != nodata_value, axis=-1)
        out[~valid_mask] = 0
    
    return out

def roi_to_tiles(
    coords: tuple,
    tif_name: str,
    tif_path: str,
    out_dir: str,
    tile_size: int = 512,
    overlap: float = 0.5,
    nodata_threshold: float = 0.9,
    black_tile_threshold: float = 5.0,
    progress_callback = None
):
    """
    Preprocesamiento del ROI a tiles
    Args:
    
    """
    os.makedirs(out_dir, exist_ok=True)

    if progress_callback:
        progress_callback(0, 100, "Paso 1/3: Calculando percentiles...")
    # Calcular percentiles globales
    lo, hi = compute_global_percentiles_stream_per_band(tif_path, coords, progress_callback = progress_callback)

    if progress_callback:
        progress_callback(100, 100, "Percentiles calculados")


    if progress_callback:
        progress_callback(0, 100, "Paso 2/3: Generando tiles...")
    with rasterio.open(tif_path) as src:
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

                    # Calcular fracción de nodata
                    # Como el tile ya tiene el tamaño final, el cálculo es directo
                    valid_pixels = tile_size * tile_size * bands
                    nodata_pixels = (tile == nodata_value).sum()
                    nodata_fraction = nodata_pixels / valid_pixels

                    #if nodata_fraction > nodata_threshold:
                    #    continue
                    if bands >= 3:
                        tile_rgb = np.stack([tile[0], tile[1], tile[2]], axis=-1)
                    else:
                        raise ValueError("TIF must have at least 3 bands (RGB).")

                    tile_rgb_8bit = normalize_percentiles_per_band(tile_rgb, lo, hi, nodata_value)

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
                    progress = int((i / total_tiles) * 100)
                    progress_callback(progress, 100, f"Generando tiles:")

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