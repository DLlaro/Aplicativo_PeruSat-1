import colorsys
import hashlib

import geopandas as gpd
import numpy as np
from affine import Affine

from logic.image_loader import SatelliteLoader


def _iter_polygons(geom):
    if geom is None or geom.is_empty:
        return
    gtype = geom.geom_type
    if gtype == "Polygon":
        yield geom
    elif gtype == "MultiPolygon":
        for poly in geom.geoms:
            yield poly
    elif gtype == "GeometryCollection":
        for sub in geom.geoms:
            yield from _iter_polygons(sub)


def _color_for_label(label: str, neutral_value: str = "0", alpha: float = 0.35):
    if label == neutral_value:
        return [0.70, 0.70, 0.70, alpha], [0.45, 0.45, 0.45, 1.0]

    digest = hashlib.md5(label.encode("utf-8")).hexdigest()
    hue = int(digest[:4], 16) / 65535.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 0.95)
    return [r, g, b, alpha], [r * 0.75, g * 0.75, b * 0.75, 1.0]


def load_vector_to_napari(
    gpkg_path: str = None,
    loader: SatelliteLoader = None,
    color_field: str = None,
    neutral_value: str = "0",
    layer: str = None,
) -> dict:
    """
    Transforma una capa vectorial a coordenadas de pixel de la preview para Napari.
    Soporta coloreado por atributo (ej. UBIGEO_CCPP_CONFIRMADO).
    """
    gdf = gpd.read_file(gpkg_path, layer=layer)
    if gdf.empty:
        return {
            "type": "shapes",
            "data": [],
            "shape_type": "polygon",
        }

    if loader is None:
        raise ValueError("loader es requerido para transformar la capa al visor.")
    if loader.transform is None or loader.scaled_factor is None:
        raise ValueError("loader no tiene transform/scale_factor configurados.")

    if loader.crs is not None and gdf.crs is not None and str(gdf.crs) != str(loader.crs):
        gdf = gdf.to_crs(loader.crs)

    aff_original = loader.transform
    factor = 1.0 / loader.scaled_factor
    aff_scaled = aff_original * Affine.scale(factor, factor)
    inv_transform = ~aff_scaled

    if color_field and color_field in gdf.columns:
        labels = gdf[color_field].fillna(neutral_value).astype(str).tolist()
    else:
        labels = ["default"] * len(gdf)

    shapes_in_pixels = []
    face_colors = []
    edge_colors = []

    for label, geom in zip(labels, gdf.geometry):
        fc, ec = _color_for_label(label, neutral_value=neutral_value)
        for poly in _iter_polygons(geom):
            coords = np.array(poly.exterior.coords)
            pixel_coords = [inv_transform * (x, y) for x, y in coords]
            napari_coords = np.array([[p[1], p[0]] for p in pixel_coords], dtype=float)
            shapes_in_pixels.append(napari_coords)
            face_colors.append(fc)
            edge_colors.append(ec)

    payload = {
        "type": "shapes",
        "data": shapes_in_pixels,
        "shape_type": "polygon",
    }
    if len(face_colors) == len(shapes_in_pixels) and face_colors:
        payload["face_color"] = face_colors
        payload["edge_color"] = edge_colors
    return payload
