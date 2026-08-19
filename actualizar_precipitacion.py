"""
Actualizador de precipitacion acumulada - Portal Hidrico Chaco.

Usa la API gratuita de Open-Meteo (sin necesidad de token/cuenta) para
obtener la lluvia acumulada de las ultimas 24 horas en cada localidad,
segun sus coordenadas, y la sube al backend via su endpoint POST.

Fuente: Open-Meteo (https://open-meteo.com), modelos ECMWF/GFS/ICON
combinados ("best_match"). Es un dato de pronostico/reanalisis
meteorologico, no una medicion de pluviometro en el lugar exacto -
se aclara esto en el backend para no dar una falsa sensacion de
precision quirurgica.
"""

import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

TZ_CHACO = ZoneInfo("America/Argentina/Buenos_Aires")

BACKEND_URL = "https://cuencas-bot.onrender.com"
TIMEOUT = 15.0

# Mismas coordenadas que ya usa el dashboard (panel_de_aplicacion.py)
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


def obtener_precipitacion_24h(lat: float, lon: float, intentos: int = 3) -> float:
    """
    Devuelve la lluvia acumulada (mm) de las ultimas 24 horas para
    un punto, usando la API de pronostico horario de Open-Meteo con
    past_days=1 (trae el dia anterior completo + lo que va del actual).

    Reintenta hasta 3 veces si hay un timeout o error de red pasajero,
    con una breve espera entre intentos, antes de darse por vencido.
    """
    import time

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "America/Argentina/Buenos_Aires",
    }

    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            resp = requests.get(
                "https://api.open-meteo.com/v1/forecast", params=params, timeout=20.0
            )
            resp.raise_for_status()
            datos = resp.json()
            break
        except Exception as e:
            ultimo_error = e
            if intento < intentos:
                time.sleep(3 * intento)  # espera un poco mas en cada reintento
            continue
    else:
        raise ultimo_error

    horas = datos["hourly"]["time"]
    precipitacion = datos["hourly"]["precipitation"]

    # Los horarios que devuelve Open-Meteo son hora LOCAL de Chaco
    # (naive, sin offset) porque pedimos timezone=America/Argentina/...
    # Por eso "ahora" tambien tiene que calcularse en esa misma zona,
    # y no con la hora del servidor (que en GitHub Actions es UTC).
    ahora_chaco = datetime.now(TZ_CHACO).replace(
        minute=0, second=0, microsecond=0, tzinfo=None
    )
    hace_24h = ahora_chaco.timestamp() - 24 * 3600

    total = 0.0
    for hora_str, mm in zip(horas, precipitacion):
        hora_dt = datetime.fromisoformat(hora_str)
        if hace_24h <= hora_dt.timestamp() <= ahora_chaco.timestamp():
            if mm is not None:
                total += mm
    return round(total, 1)


def actualizar_backend(localidad: str, precipitacion_mm: float) -> bool:
    try:
        # Se manda tambien el nivel_metros actual para no pisarlo con
        # un valor viejo: primero lo leemos, despues actualizamos solo
        # la precipitacion.
        r_actual = requests.get(f"{BACKEND_URL}/localidades/{localidad}", timeout=TIMEOUT)
        r_actual.raise_for_status()
        nivel_actual = r_actual.json()["localidad"]["nivel_metros"]

        r = requests.post(
            f"{BACKEND_URL}/hidrologia/actualizar",
            json={
                "localidad": localidad,
                "nivel_metros": nivel_actual,
                "precipitacion_acumulada_mm": precipitacion_mm,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  [ERROR] No se pudo actualizar {localidad}: {e}")
        return False


def main():
    print(f"=== Actualizador de precipitacion - {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Backend: {BACKEND_URL}\n")

    actualizadas, fallidas = [], []

    for localidad, (lat, lon) in COORDENADAS.items():
        try:
            mm = obtener_precipitacion_24h(lat, lon)
        except Exception as e:
            print(f"{localidad}: [ERROR] no se pudo leer Open-Meteo: {e}")
            fallidas.append(localidad)
            continue

        ok = actualizar_backend(localidad, mm)
        print(f"{localidad}: {mm} mm (ultimas 24h) ... {'OK' if ok else 'FALLO'}")
        (actualizadas if ok else fallidas).append(localidad)

    print(f"\nResumen: {len(actualizadas)} actualizadas OK, {len(fallidas)} con error.")
    if fallidas:
        print("Fallidas:", fallidas)
    if len(fallidas) > len(COORDENADAS) // 2:
        sys.exit(1)

if __name__ == "__main__":
    main()
