"""
Actualizador automatico de niveles de rio - Portal Hidrico Chaco.

Lee la tabla publica de alturas hidrometricas de la cuenca del Parana
(Prefectura Naval Argentina, publicada por el CIM - UNL) y actualiza
el backend del Portal Hidrico Chaco via su endpoint POST.

IMPORTANTE SOBRE PRECISION (leer antes de tocar el mapeo):
- 2 localidades tienen estacion propia y exacta en esta fuente:
  Barranqueras, Isla del Cerrito.
- 4 localidades usan la estacion mas cercana del MISMO tramo de rio,
  porque no tienen hidrometro propio publicado aca (Resistencia y
  Puerto Vilelas -> estacion Barranqueras; Puerto Bermejo -> estacion
  "Bermejo"; La Leonesa -> estacion "Las Palmas"). Son aproximaciones
  razonables por cercania geografica, NO el punto exacto.
- 4 localidades NO tienen dato real disponible en esta fuente porque
  estan en las cuencas del Bermejo, que esta red no cubre:
  El Sauzalito, Pampa del Indio, Villa Rio Bermejito, Fuerte Esperanza.
  Estas quedan con "conectado": False hasta conseguir otra fuente.

NOTA (02/09/2026): se sacaron las estaciones "Corrientes" y "Formosa"
de MAPEO_ESTACIONES - esas localidades ya NO forman parte del alcance
del proyecto (Portal Hidrico Chaco cubre solo la provincia del Chaco).

NOTA (02/10/2026): el backend ahora exige la clave de escritura en el
header X-API-Key. Se lee de la variable de entorno API_KEY_SENSORES
(la MISMA que esta cargada en Render). Nunca escribir la clave en este
archivo.

NOTA (05/10/2026): se agrego (1) despertar el backend antes de enviar
datos (Render gratis se duerme), (2) reintentos al leer la fuente y al
enviar cada lectura, y (3) se corrigieron los indices de columna de
Alerta/Evacuacion (la tabla tiene: Puerto, Rio, Altura, Variacion,
Cambio, Alt. Ant, Alerta, Evacuacion, Historico). La fuente informa
"cada 24 horas", asi que correr mas seguido que cada hora no aporta.

Fuente: Prefectura Naval Argentina, via CIM-UNL
        https://fich.unl.edu.ar/cim/rios/parana/alturas
"""

import os
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_FUENTE = "http://wfich1.unl.edu.ar/cim/rios/parana/alturas"
BACKEND_URL = "https://cuencas-bot.onrender.com"  # cambiar si el backend se muda
TIMEOUT = 60.0  # Render gratis puede tardar hasta 1 minuto en despertar

# ---------------------------------------------------------------------
# MAPEO estacion (nombre EXACTO en la tabla de la fuente) -> localidad
# "exacto": True  = la estacion es literalmente esa localidad
# "exacto": False = estacion mas cercana del mismo tramo, aproximacion
# ---------------------------------------------------------------------
MAPEO_ESTACIONES = {
    "Barranqueras": [
        {"localidad": "barranqueras", "exacto": True},
        {"localidad": "resistencia", "exacto": False},
        {"localidad": "puerto_vilelas", "exacto": False},
    ],
    "Isla del Cerrito": [
        {"localidad": "isla_del_cerrito", "exacto": True},
    ],
    "Bermejo": [
        {"localidad": "puerto_bermejo", "exacto": False},
    ],
    "Las Palmas": [
        {"localidad": "la_leonesa", "exacto": False},
    ],
}

# Localidades que sabemos de antemano que esta fuente NO cubre.
SIN_FUENTE_DISPONIBLE = [
    "el_sauzalito", "pampa_del_indio", "villa_rio_bermejito", "fuerte_esperanza",
]

# Posicion de cada columna en la tabla de la fuente
COL_ALTURA = 2
COL_ALTURA_ANTERIOR = 5
COL_ALERTA = 6
COL_EVACUACION = 7


def _a_float(texto: str):
    """Convierte '6,31' -> 6.31. Devuelve None si no es un numero valido."""
    texto = texto.strip().replace(",", ".")
    if texto in ("", "-", "—", "\u2014"):
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def despertar_backend() -> bool:
    """Render (plan gratis) se duerme por inactividad y tarda en arrancar.
    Le pegamos a la raiz hasta que responda, antes de mandar datos."""
    for intento in range(1, 7):
        try:
            r = requests.get(f"{BACKEND_URL}/", timeout=TIMEOUT)
            if r.status_code == 200:
                print(f"Backend despierto (intento {intento}).")
                return True
        except requests.RequestException as e:
            print(f"  Backend aun no responde (intento {intento}/6): {e}")
        time.sleep(10)
    print("[AVISO] El backend no respondio al despertarlo; se intenta enviar igual.")
    return False


def _descargar_filas() -> list:
    """Descarga la pagina de la fuente y devuelve la tabla como lista de filas
    (cada fila, una lista de textos de celda)."""
    resp = None
    ultimo_error = None
    for intento in range(1, 4):
        try:
            resp = requests.get(URL_FUENTE, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            ultimo_error = e
            print(f"  Fuente no respondio (intento {intento}/3): {e}")
            resp = None
            time.sleep(10)
    if resp is None:
        raise RuntimeError(f"No se pudo descargar la fuente: {ultimo_error}")

    soup = BeautifulSoup(resp.text, "lxml")

    tabla = soup.find("table")
    if tabla is None:
        raise RuntimeError("No se encontro ninguna tabla en la pagina fuente. "
                           "El sitio pudo haber cambiado de estructura, revisar manualmente.")

    return [
        [c.get_text(strip=True) for c in fila.find_all(["td", "th"])]
        for fila in tabla.find_all("tr")
    ]


def obtener_tabla_completa(filas: list) -> list:
    """Todas las estaciones de la tabla (Parana, Paraguay, aguas arriba), para
    el panel de referencia del rio. La tendencia NO se lee del icono de la
    pagina: se deduce del signo de la variacion."""
    estaciones = []
    for celdas in filas:
        if len(celdas) < 8:
            continue
        puerto, rio = celdas[0], celdas[1]
        if not puerto or puerto.lower() == "puerto":
            continue  # encabezado
        altura = _a_float(celdas[COL_ALTURA])
        anterior = _a_float(celdas[COL_ALTURA_ANTERIOR])
        variacion = round(altura - anterior, 2) if altura is not None and anterior is not None else None
        estaciones.append({
            "puerto": puerto,
            "rio": rio,
            "altura_m": altura,
            "variacion_m": variacion,
            "altura_anterior_m": anterior,
            "alerta_m": _a_float(celdas[COL_ALERTA]),
            "evacuacion_m": _a_float(celdas[COL_EVACUACION]),
        })
    return estaciones


def obtener_datos_estaciones(filas: list) -> dict:
    """
    Parsea las estaciones que usa el portal. Devuelve un dict:
    { "Barranqueras": {"altura": 4.16, "alerta": 6.00, "evacuacion": 6.50}, ... }
    """
    resultado = {}
    for celdas in filas:
        if len(celdas) < 6:
            continue
        nombre_estacion = celdas[0]
        if nombre_estacion not in MAPEO_ESTACIONES:
            continue  # no nos interesa esta fila
        altura = _a_float(celdas[COL_ALTURA])
        alerta = _a_float(celdas[COL_ALERTA]) if len(celdas) > COL_ALERTA else None
        evacuacion = _a_float(celdas[COL_EVACUACION]) if len(celdas) > COL_EVACUACION else None
        if altura is None:
            continue  # "sin datos" ese dia, no actualizamos con basura
        anterior = _a_float(celdas[COL_ALTURA_ANTERIOR]) if len(celdas) > COL_ALTURA_ANTERIOR else None
        variacion = round(altura - anterior, 2) if anterior is not None else None
        resultado[nombre_estacion] = {
            "altura": altura,
            "variacion_24h": variacion,
            "alerta": alerta,
            "evacuacion": evacuacion,
        }
    return resultado


def actualizar_backend(localidad: str, nivel_metros: float, variacion_24h=None, intentos: int = 3) -> bool:
    clave_api = os.environ.get("API_KEY_SENSORES", "")
    for intento in range(1, intentos + 1):
        try:
            r = requests.post(
                f"{BACKEND_URL}/hidrologia/actualizar",
                json={
                    "localidad": localidad,
                    "nivel_metros": nivel_metros,
                    "variacion_24h_m": variacion_24h,
                },
                headers={"X-API-Key": clave_api},
                timeout=TIMEOUT,
            )
            if r.status_code in (401, 403):
                # Clave incorrecta: reintentar no sirve.
                print(f"  [ERROR] {localidad}: el backend rechazo la clave ({r.status_code}). "
                      "Revisar que API_KEY_SENSORES sea igual en GitHub y en Render.")
                return False
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"  [ERROR] {localidad}, intento {intento}/{intentos}: {e}")
            if intento < intentos:
                time.sleep(15)
    return False


def enviar_referencia_rio(estaciones: list, intentos: int = 3) -> bool:
    """Manda la tabla completa de estaciones para el panel 'aguas arriba'."""
    clave_api = os.environ.get("API_KEY_SENSORES", "")
    for intento in range(1, intentos + 1):
        try:
            r = requests.post(
                f"{BACKEND_URL}/rio/referencia",
                json={"estaciones": estaciones,
                      "fuente": "Prefectura Naval Argentina, via CIM-FICH-UNL"},
                headers={"X-API-Key": clave_api},
                timeout=TIMEOUT,
            )
            if r.status_code in (401, 403):
                print(f"  [ERROR] referencia del rio: clave rechazada ({r.status_code}).")
                return False
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"  [ERROR] referencia del rio, intento {intento}/{intentos}: {e}")
            if intento < intentos:
                time.sleep(15)
    return False


def main():
    print(f"=== Actualizador de niveles - {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Fuente: {URL_FUENTE}")
    print(f"Backend: {BACKEND_URL}\n")

    if not os.environ.get("API_KEY_SENSORES"):
        print("[ERROR FATAL] Falta la variable de entorno API_KEY_SENSORES. "
              "Sin ella el backend rechaza las escrituras.")
        sys.exit(1)

    despertar_backend()

    try:
        filas = _descargar_filas()
        datos = obtener_datos_estaciones(filas)
        tabla_completa = obtener_tabla_completa(filas)
    except Exception as e:
        print(f"[ERROR FATAL] No se pudo leer la fuente: {e}")
        sys.exit(1)

    if not datos:
        print("[ERROR FATAL] Se leyo la pagina pero no se encontro ninguna estacion "
              "esperada. Revisar si la fuente cambio de formato.")
        sys.exit(1)

    actualizadas, fallidas = [], []

    for nombre_estacion, info in datos.items():
        destinos = MAPEO_ESTACIONES[nombre_estacion]
        for destino in destinos:
            clave = destino["localidad"]
            exacto = destino["exacto"]
            etiqueta = "medicion directa" if exacto else "APROXIMADO, estacion cercana"
            print(f"{nombre_estacion} ({etiqueta}) -> {clave}: {info['altura']} m")
            ok = actualizar_backend(clave, info["altura"], info.get("variacion_24h"))
            (actualizadas if ok else fallidas).append(clave)

    if tabla_completa:
        print(f"\nEnviando referencia del rio: {len(tabla_completa)} estaciones.")
        if not enviar_referencia_rio(tabla_completa):
            fallidas.append("referencia_rio")
    else:
        print("[AVISO] No se pudo armar la tabla completa de estaciones.")

    print("\n--- Localidades sin fuente publica disponible (sin tocar) ---")
    for clave in SIN_FUENTE_DISPONIBLE:
        print(f"  {clave}: sigue con dato de referencia")

    print(f"\nResumen: {len(actualizadas)} actualizadas OK, {len(fallidas)} con error.")
    if fallidas:
        print("Fallidas:", fallidas)
        sys.exit(1)


if __name__ == "__main__":
    main()
