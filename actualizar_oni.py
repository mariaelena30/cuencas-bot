"""
Actualizador del indice ONI (El Nino / La Nina) - Portal Hidrico Chaco.

Lee la tabla oficial del NOAA Climate Prediction Center (CPC) con el
Oceanic Nino Index historico, toma el valor mas reciente y lo sube al
backend via su endpoint POST /clima/actualizar.

Clasificacion (criterio estandar del NOAA):
  ANOM >= 0.5   -> El Nino
  ANOM <= -0.5  -> La Nina
  en el medio   -> Neutro
(El criterio oficial completo pide 5 temporadas seguidas cruzando el
umbral; ac{a} usamos el valor mas reciente como aproximacion simple,
aclarado como tal en el dato que se muestra al usuario.)

Fuente: NOAA Climate Prediction Center
        https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
"""

import sys
from datetime import datetime, timezone

import requests

URL_FUENTE = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
BACKEND_URL = "https://cuencas-bot.onrender.com"
TIMEOUT = 15.0


def clasificar_fase(anomalia: float) -> str:
    if anomalia >= 0.5:
        return "El Niño"
    if anomalia <= -0.5:
        return "La Niña"
    return "Neutro"


def obtener_ultimo_oni() -> tuple[str, float]:
    """
    Descarga la tabla y devuelve (temporada_mas_reciente, anomalia).
    La tabla viene ordenada cronologicamente, asi que el dato mas
    reciente es siempre la ultima linea con datos.
    """
    resp = requests.get(URL_FUENTE, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    lineas = [l.strip() for l in resp.text.strip().splitlines() if l.strip()]
    if len(lineas) < 2:
        raise RuntimeError("La tabla del NOAA vino vacia o con formato inesperado.")

    # Primera linea es el encabezado (SEAS YR TOTAL ANOM), la ignoramos.
    ultima_linea = lineas[-1]
    partes = ultima_linea.split()
    if len(partes) != 4:
        raise RuntimeError(f"Formato de linea inesperado: '{ultima_linea}'")

    temporada, anio, _total, anom_str = partes
    anomalia = float(anom_str)
    etiqueta = f"{temporada} {anio}"
    return etiqueta, anomalia


def actualizar_backend(fase: str, valor: float) -> bool:
    try:
        r = requests.post(
            f"{BACKEND_URL}/clima/actualizar",
            json={"fase_oni": fase, "ultimo_valor_oni": valor},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo actualizar el backend: {e}")
        return False


def main():
    print(f"=== Actualizador de ONI - {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Fuente: {URL_FUENTE}")
    print(f"Backend: {BACKEND_URL}\n")

    try:
        temporada, anomalia = obtener_ultimo_oni()
    except Exception as e:
        print(f"[ERROR FATAL] No se pudo leer la fuente: {e}")
        sys.exit(1)

    fase = clasificar_fase(anomalia)
    print(f"Temporada mas reciente: {temporada}")
    print(f"Anomalia ONI: {anomalia:+.2f}")
    print(f"Fase clasificada: {fase}")

    ok = actualizar_backend(fase, anomalia)
    print(f"\nActualizacion del backend: {'OK' if ok else 'FALLO'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

