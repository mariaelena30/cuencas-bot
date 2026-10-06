"""
Actualizador de precipitacion acumulada - Portal Hidrico Chaco.

Usa la API gratuita de Open-Meteo (sin necesidad de token/cuenta) para
obtener la lluvia acumulada de las ultimas 24 horas en cada localidad,
segun sus coordenadas, y la sube al backend.

Fuente: Open-Meteo (https://open-meteo.com), modelos ECMWF/GFS/ICON
combinados ("best_match"). Es un dato de pronostico/reanalisis
meteorologico, no una medicion de pluviometro en el lugar exacto.

CAMBIO (02/10/2026): ya NO se reenvia el nivel del rio. Usa un endpoint
propio (/precipitacion/actualizar) que solo toca la lluvia. La clave se
lee de la variable de entorno API_KEY_SENSORES.

CAMBIO (06/10/2026):
- Una SOLA consulta a Open-Meteo con todas las localidades (antes eran
  16 consultas seguidas y una sola que se colgara hacia fallar todo).
- Reintentos con espera, tanto para Open-Meteo como para el backend.
- Despierta el backend (Render gratis se duerme) antes de enviar datos.
- El trabajo solo se marca como fallido si fallan muchas localidades; un
  fallo aislado se avisa en el log pero no tira todo el proceso.
- La ventana de 24 h contaba 25 horas; ahora cuenta exactamente 24.
- Si faltan datos de lluvia, no se envia 0.0: se omite la localidad.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

TZ_CHACO = ZoneInfo("America/Argentina/Buenos_Aires")

BACKEND_URL = "https://cuencas-bot.onrender.com"
TIMEOUT_BACKEND = 60.0  # Render gratis puede tardar hasta 1 minuto en despertar

URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_OPEN_METEO = 60.0
INTENTOS_OPEN_METEO = 4

# Para considerar valido el dato de una localidad, tienen que venir al
# menos tantas horas con valor (de las 24 de la ventana).
MINIMO_HORAS_VALIDAS = 20

# Coordenadas del centro de cada localidad (dato geografico, no hidrologico).
# IMPORTANTE: cada clave de aca tiene que existir tambien en "localidades"
# de main.py; si no, el backend responde 404 "no reconocida".
COORDENADAS = {
    "resistencia": (-27.4511, -58.9866),
    "barranqueras": (-27.4815, -58.9324),
    "puerto_bermejo": (-26.8667, -58.6333),
    "el_sauzalito": (-24.4236, -61.6842),
    "isla_del_cerrito": (-27.3667, -58.6333),
    "puerto_vilelas": (-27.4967, -58.9394),
    "la_leonesa": (-27.0500, -58.6833),
    "pampa_del_indio": (-25.9167, -59.9333),
    "villa_rio_bermejito": (-25.6167, -60.1667),
    "fuerte_esperanza": (-24.5333, -61.7500),
    "san_martin_chaco": (-26.5375, -59.3417),
    "santa_sylvina": (-27.7830, -61.1500),
    "charata": (-27.2180, -61.1874),
    "quitilipi": (-26.8700, -60.2200),
    "castelli": (-25.9500, -60.6170),
    "presidencia_de_la_plaza": (-26.9986, -59.8466),
    "saenz_pena": (-26.7853, -60.4388),
}


def despertar_backend() -> bool:
    """Render (plan gratis) se duerme por inactividad y tarda en arrancar.
    Le pegamos a la raiz hasta que responda, antes de mandar datos."""
    for intento in range(1, 7):
        try:
            r = requests.get(f"{BACKEND_URL}/", timeout=TIMEOUT_BACKEND)
            if r.status_code == 200:
                print(f"Backend despierto (intento {intento}).")
                return True
        except requests.RequestException as e:
            print(f"  Backend aun no responde (intento {intento}/6): {e}")
        time.sleep(10)
    print("[AVISO] El backend no respondio al despertarlo; se intenta enviar igual.")
    return False


def pedir_lluvia_horaria(claves: list) -> list:
    """Una sola consulta a Open-Meteo con todas las localidades.
    Devuelve una lista con un resultado por localidad, en el mismo orden."""
    params = {
        "latitude": ",".join(str(COORDENADAS[c][0]) for c in claves),
        "longitude": ",".join(str(COORDENADAS[c][1]) for c in claves),
        "hourly": "precipitation",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "America/Argentina/Buenos_Aires",
    }
    ultimo_error = None
    for intento in range(1, INTENTOS_OPEN_METEO + 1):
        try:
            r = requests.get(URL_OPEN_METEO, params=params, timeout=TIMEOUT_OPEN_METEO)
            r.raise_for_status()
            datos = r.json()
            if isinstance(datos, dict):  # con un solo punto devuelve un objeto
                datos = [datos]
            if len(datos) != len(claves):
                raise ValueError(
                    f"Open-Meteo devolvio {len(datos)} resultados para {len(claves)} localidades"
                )
            return datos
        except Exception as e:
            ultimo_error = e
            print(f"  Open-Meteo fallo (intento {intento}/{INTENTOS_OPEN_METEO}): {e}")
            if intento < INTENTOS_OPEN_METEO:
                time.sleep(5 * intento)
    raise RuntimeError(f"Open-Meteo no respondio tras {INTENTOS_OPEN_METEO} intentos: {ultimo_error}")


def sumar_24h(hourly: dict):
    """Lluvia (mm) de las 24 horas que terminan en la hora actual de Chaco.
    Open-Meteo devuelve horas LOCALES de Chaco (sin zona), por eso "ahora"
    tambien se calcula en esa zona y no con la hora del servidor (UTC).
    Devuelve None si no hay datos suficientes."""
    horas = hourly.get("time") or []
    valores = hourly.get("precipitation") or []

    ahora = datetime.now(TZ_CHACO).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    desde = ahora - timedelta(hours=24)

    total = 0.0
    validas = 0
    for hora_str, mm in zip(horas, valores):
        hora = datetime.fromisoformat(hora_str)
        if desde < hora <= ahora and mm is not None:
            total += mm
            validas += 1

    if validas < MINIMO_HORAS_VALIDAS:
        return None
    return round(total, 1)


def actualizar_backend(localidad: str, precipitacion_mm: float, intentos: int = 3) -> bool:
    clave_api = os.environ.get("API_KEY_SENSORES", "")
    for intento in range(1, intentos + 1):
        try:
            r = requests.post(
                f"{BACKEND_URL}/precipitacion/actualizar",
                json={
                    "localidad": localidad,
                    "precipitacion_acumulada_mm": precipitacion_mm,
                    "fuente": "Open-Meteo (modelo meteorologico, no pluviometro)",
                },
                headers={"X-API-Key": clave_api},
                timeout=TIMEOUT_BACKEND,
            )
            if r.status_code in (401, 403):
                print("  [ERROR] Clave rechazada por el backend: revisar que API_KEY_SENSORES "
                      "sea igual en GitHub y en Render.")
                return False
            if r.status_code in (404, 422):
                print(f"  [ERROR] {localidad}: el backend no la reconoce o rechazo el dato "
                      f"({r.status_code}). Revisar que exista en main.py.")
                return False
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"  [ERROR] {localidad}, intento {intento}/{intentos}: {e}")
            if intento < intentos:
                time.sleep(10)
    return False


def main():
    print(f"=== Actualizador de precipitacion - {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Backend: {BACKEND_URL}\n")

    if not os.environ.get("API_KEY_SENSORES"):
        print("[ERROR FATAL] Falta la variable de entorno API_KEY_SENSORES. "
              "Sin ella el backend rechaza las escrituras.")
        sys.exit(1)

    claves = list(COORDENADAS.keys())

    despertar_backend()

    try:
        resultados = pedir_lluvia_horaria(claves)
    except Exception as e:
        print(f"[ERROR FATAL] {e}")
        sys.exit(1)

    actualizadas, fallidas, sin_dato = [], [], []

    for clave, resultado in zip(claves, resultados):
        mm = sumar_24h(resultado.get("hourly") or {})
        if mm is None:
            print(f"{clave}: sin datos suficientes de lluvia, se omite")
            sin_dato.append(clave)
            continue
        ok = actualizar_backend(clave, mm)
        print(f"{clave}: {mm} mm (ultimas 24h) ... {'OK' if ok else 'FALLO'}")
        (actualizadas if ok else fallidas).append(clave)

    problemas = fallidas + sin_dato
    print(f"\nResumen: {len(actualizadas)} actualizadas OK, "
          f"{len(fallidas)} con error al enviar, {len(sin_dato)} sin datos.")
    if problemas:
        print("Con problemas:", problemas)

    # El trabajo se marca como fallido solo si no se actualizo ninguna
    # localidad, o si fallo mas de un tercio. Un fallo aislado queda
    # avisado arriba pero no tira todo el proceso.
    if not actualizadas or len(problemas) > len(claves) / 3:
        sys.exit(1)


if __name__ == "__main__":
    main()
