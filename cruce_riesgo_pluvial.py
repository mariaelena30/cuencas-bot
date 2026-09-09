"""
cruce_riesgo_pluvial.py
------------------------
Portal Hidrico Chaco

Cruza un DEM (cotas bajas / lagunas) con la cartografia de radios
censales de INDEC para generar automaticamente la lista de zonas con
riesgo de anegamiento pluvial, en vez de cargarla a mano.

REQUIERE (instalar antes de correr):
    pip install geopandas rasterio shapely

INSUMOS (bajalos vos, no vienen incluidos):
    1. DEM de la zona (AMGR o la localidad que quieras analizar)
       -> IGN: ign.gob.ar/NuestrasActividades/InformacionGeoespacial/CapasSIG
       -> o ALOS PALSAR (12.5m): search.asf.alaska.edu
       Guardalo como: data/dem_amgr.tif

    2. Radios censales de Chaco (INDEC, censo 2022)
       -> geoportal.indec.gob.ar (Cartografia > Radios censales > Chaco)
       Guardalo como: data/radios_censales_chaco.shp  (o .geojson)

SALIDA:
    Un GeoJSON (zonas_riesgo_pluvial.geojson) con un poligono por cada
    radio censal marcado como riesgo_pluvial=True, listo para:
      a) revisar en QGIS antes de confiar en el resultado
      b) o convertir directo a la lista que usa riesgo_pluvial_barrios.py
"""

import geopandas as gpd
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape
import json

# ============================================================
# CONFIGURACION - ajustar segun la zona a analizar
# ============================================================

DEM_PATH = "data/dem_amgr.tif"
RADIOS_CENSALES_PATH = "data/radios_censales_chaco.shp"
SALIDA_GEOJSON = "zonas_riesgo_pluvial.geojson"

# Cota MOP de referencia. OJO: el DEM baja en metros sobre el nivel
# del mar (elipsoidal/IGN), NO en cota MOP. Hay que convertir antes
# de comparar - la diferencia entre datum IGN y MOP en Resistencia
# es conocida pero hay que confirmarla con APA antes de usar esto
# en produccion. Por ahora se deja como constante para no mezclar
# el TODO con el resto del script.
COTA_LAGUNAS_MOP = 48.08          # linea de ribera general (Roces, UNNE)
OFFSET_MOP_A_ELIPSOIDAL = None    # TODO: confirmar con APA Chaco

UMBRAL_RIESGO_M = 52.0  # placeholder si OFFSET_MOP_A_ELIPSOIDAL sigue None


def extraer_zonas_bajas(dem_path: str, umbral_m: float) -> gpd.GeoDataFrame:
    """
    Convierte el DEM en poligonos: todo pixel por debajo del umbral
    se agrupa en manchas (zonas bajas / potencialmente inundables).
    """
    with rasterio.open(dem_path) as src:
        banda = src.read(1)
        mascara_bajo_umbral = banda < umbral_m
        transformo = src.transform
        crs = src.crs

        resultados = (
            {"geometry": shape(geom), "cota_baja": True}
            for geom, valor in shapes(
                banda, mask=mascara_bajo_umbral, transform=transformo
            )
        )
        return gpd.GeoDataFrame(list(resultados), crs=crs)


def cruzar_con_radios_censales(
    zonas_bajas: gpd.GeoDataFrame, radios_path: str
) -> gpd.GeoDataFrame:
    """
    Interseccion vectorial: que radios censales tocan una zona baja.
    Equivalente a "Vectorial > Analisis > Interseccion" en QGIS.
    """
    radios = gpd.read_file(radios_path)
    radios = radios.to_crs(zonas_bajas.crs)  # mismo sistema de referencia

    interseccion = gpd.overlay(radios, zonas_bajas, how="intersection")

    # nos quedamos con el nombre/codigo de radio + area afectada,
    # sin duplicar geometria de mas
    columnas_radio = [c for c in radios.columns if c != "geometry"]
    resultado = interseccion[columnas_radio + ["geometry"]].copy()
    resultado["riesgo_pluvial"] = True
    resultado["confianza"] = "media"  # cruce automatico, no lo bajes a "alta" sin revisar en QGIS
    resultado["motivo"] = "Interseccion DEM (zona baja) x radio censal INDEC"

    return resultado


def guardar(resultado: gpd.GeoDataFrame, salida: str):
    resultado.to_file(salida, driver="GeoJSON")
    print(f"Listo: {len(resultado)} radios censales con riesgo pluvial -> {salida}")
    print("IMPORTANTE: revisar en QGIS antes de subir a produccion.")
    print("El offset MOP<->elipsoidal sigue sin confirmar (ver comentario arriba).")


if __name__ == "__main__":
    zonas_bajas = extraer_zonas_bajas(DEM_PATH, UMBRAL_RIESGO_M)
    resultado = cruzar_con_radios_censales(zonas_bajas, RADIOS_CENSALES_PATH)
    guardar(resultado, SALIDA_GEOJSON)
