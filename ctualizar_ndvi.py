"""
Actualizador de NDVI satelital - Portal Hidrico Chaco.

Usa el servicio REST publico del ORNL DAAC (NASA), que da acceso a
subsets de MODIS sin necesitar cuenta ni token de NASA Earthdata, y
calcula el NDVI promedio de las 12 localidades monitoreadas.

Producto: MOD13Q1 (MODIS/Terra Vegetation Indices, 16 dias, 250m).
El NDVI viene escalado x10000 en la fuente (ej: 4581 -> NDVI real 0.4581).

Como MOD13Q1 es un compuesto de 16 dias, no tiene sentido correr esto
mas seguido que eso - alcanza con una vez por semana.

Fuente: ORNL DAAC MODIS/VIIRS Web Service
        https://modis.ornl.gov/data/modis_webservice.html
"""

import sys
from datetime import datetime, timezone

import requests

BASE_URL = "https://modis.ornl.gov/rst/api/v1"
PRODUCTO = "MOD13Q1"
BACKEND_URL = "https://cuencas-bot.onrender.com"
TIMEOUT = 30.0
HEADERS = {"Accept": "application/json"}

# Mismas coordenadas que ya usa el dashboard
COORDENADAS = {
    "resistencia": (-27.4511, -58.9866),
    "barranqueras": (-27.4815, -58.9324),
    "corrientes": (-27.4698, -58.8306),
    "formosa": (-26.1775, -58.1781),
    "puerto_bermejo": (-26.8667, -58.6333),
    "el_sauzalito": (-24.4236, -61.6842),
    "isla_del_cerrito": (-27.3667, -58.6333),
    "puerto_vilelas": (-27.4967, -58.9394),
    "la_leonesa": (-27.0500, -58.6833),
    "pampa_del_indio": (-25.9167, -59.9333),
    "villa_rio_bermejito": (-25.6167, -60.1667),
    "fuerte_esperanza": (-24.5333, -61.7500),
}


def obtener_fecha_mas_reciente(lat: float, lon: float) -> str:
    """Consulta las fechas de composicion disponibles y devuelve la ultima."""
    url = f"{BASE_URL}/{PRODUCTO}/dates"
    resp = requests.get(url, params={"latitude": lat, "longitude": lon}, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    datos = resp.json()
    fechas = datos.get("dates", [])
    if not fechas:
        raise RuntimeError("No hay fechas disponibles para este punto.")
    # Vienen ordenadas cronologicamente, la ultima es la mas reciente.
    return fechas[-1]["modis_date"]


def obtener_ndvi_punto(lat: float, lon: float, fecha_modis: str) -> float:
    """
    Devuelve el NDVI real (ya dividido por 10000) del pixel central
    para un punto y fecha de composicion MODIS dados.
    """
    url = f"{BASE_URL}/{PRODUCTO}/subset"
    params = {
        "latitude": lat,
        "longitude": lon,
        "startDate": fecha_modis,
        "endDate": fecha_modis,
        "kmAboveBelow": 0,
        "kmLeftRight": 0,
    }
    resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    datos = resp.json()

    for banda in datos.get("subset", []):
        if banda["band"].endswith("_NDVI"):
            valores = banda["data"]
            if not valores:
                raise RuntimeError("La banda NDVI vino vacia.")
            # kmAboveBelow=0, kmLeftRight=0 -> un solo pixel central
            return valores[0] / 10000.0

    raise RuntimeError("No se encontro la banda NDVI en la respuesta.")


def clasificar_vegetacion(ndvi: float) -> str:
    if ndvi < 0.2:
        return "BAJA (posible estres o suelo desnudo)"
    if ndvi < 0.5:
        return "MODERADA"
    return "ESTABLE"


def actualizar_backend(ndvi_promedio: float, condicion: str) -> bool:
    try:
        r = requests.post(
            f"{BACKEND_URL}/satelital/actualizar",
            json={"ndvi_promedio": round(ndvi_promedio, 4), "condicion_vegetacion": condicion},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo actualizar el backend: {e}")
        return False


def main():
    print(f"=== Actualizador de NDVI - {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Backend: {BACKEND_URL}\n")

    # Uso Barranqueras como referencia para saber la fecha de composicion
    # mas reciente (todas las localidades de Chaco comparten fecha).
    try:
        lat_ref, lon_ref = COORDENADAS["barranqueras"]
        fecha = obtener_fecha_mas_reciente(lat_ref, lon_ref)
        print(f"Fecha de composicion MODIS mas reciente: {fecha}\n")
    except Exception as e:
        print(f"[ERROR FATAL] No se pudo consultar las fechas disponibles: {e}")
        sys.exit(1)

    valores_ndvi = []
    fallidas = []
    for localidad, (lat, lon) in COORDENADAS.items():
        try:
            ndvi = obtener_ndvi_punto(lat, lon, fecha)
            print(f"{localidad}: NDVI = {ndvi:.4f}")
            valores_ndvi.append(ndvi)
        except Exception as e:
            print(f"{localidad}: [ERROR] {e}")
            fallidas.append(localidad)

    if not valores_ndvi:
        print("\n[ERROR FATAL] No se pudo obtener NDVI de ninguna localidad.")
        sys.exit(1)

    promedio = sum(valores_ndvi) / len(valores_ndvi)
    condicion = clasificar_vegetacion(promedio)

    print(f"\nNDVI promedio ({len(valores_ndvi)}/{len(COORDENADAS)} localidades): {promedio:.4f}")
    print(f"Condicion: {condicion}")
    if fallidas:
        print(f"Localidades sin dato esta vez: {fallidas}")

    ok = actualizar_backend(promedio, condicion)
    print(f"\nActualizacion del backend: {'OK' if ok else 'FALLO'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
