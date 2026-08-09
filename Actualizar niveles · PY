"""
Actualizador automatico de niveles de rio - Portal Hidrico Chaco.

Lee la tabla publica de alturas hidrometricas de la cuenca del Parana
(Prefectura Naval Argentina, publicada por el CIM - UNL) y actualiza
el backend del Portal Hidrico Chaco via su endpoint POST.

IMPORTANTE SOBRE PRECISION (leer antes de tocar el mapeo):
- 4 localidades tienen estacion propia y exacta en esta fuente:
  Barranqueras, Corrientes, Formosa, Isla del Cerrito.
- 4 localidades usan la estacion mas cercana del MISMO tramo de rio,
  porque no tienen hidrometro propio publicado aca (Resistencia y
  Puerto Vilelas -> estacion Barranqueras; Puerto Bermejo -> estacion
  "Bermejo"; La Leonesa -> estacion "Las Palmas"). Son aproximaciones
  razonables por cercania geografica, NO el punto exacto.
- 4 localidades NO tienen dato real disponible en esta fuente porque
  estan en las cuencas del Bermejo/Pilcomayo, que esta red no cubre:
  El Sauzalito, Pampa del Indio, Villa Rio Bermejito, Fuerte Esperanza.
  Estas quedan con "conectado": False hasta conseguir otra fuente.

Fuente: Prefectura Naval Argentina, via CIM-UNL
        https://fich.unl.edu.ar/cim/rios/parana/alturas
"""

import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_FUENTE = "https://fich.unl.edu.ar/cim/rios/parana/alturas"
BACKEND_URL = "https://cuencas-bot.onrender.com"  # cambiar si el backend se muda
TIMEOUT = 15.0

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
    "Corrientes": [
        {"localidad": "corrientes", "exacto": True},
    ],
    "Formosa": [
        {"localidad": "formosa", "exacto": True},
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
# Se listan para poder avisar explicitamente que quedan sin actualizar.
SIN_FUENTE_DISPONIBLE = [
    "el_sauzalito", "pampa_del_indio", "villa_rio_bermejito", "fuerte_esperanza",
]


def _a_float(texto: str):
    """Convierte '6,31' -> 6.31. Devuelve None si no es un numero valido."""
    texto = texto.strip().replace(",", ".")
    if texto in ("", "-", "—", "\u2014"):
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def obtener_datos_estaciones() -> dict:
    """
    Descarga y parsea la tabla de alturas. Devuelve un dict:
    { "Barranqueras": {"altura": 3.10, "alerta": 6.00, "evacuacion": 6.50}, ... }
    """
    resp = requests.get(URL_FUENTE, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    tabla = soup.find("table")
    if tabla is None:
        raise RuntimeError("No se encontro ninguna tabla en la pagina fuente. "
                            "El sitio pudo haber cambiado de estructura, revisar manualmente.")

    filas = tabla.find_all("tr")
    resultado = {}
    for fila in filas:
        celdas = [c.get_text(strip=True) for c in fila.find_all(["td", "th"])]
        if len(celdas) < 6:
            continue
        nombre_estacion = celdas[0]
        if nombre_estacion not in MAPEO_ESTACIONES:
            continue  # no nos interesa esta fila
        altura = _a_float(celdas[2])
        alerta = _a_float(celdas[5]) if len(celdas) > 5 else None
        evacuacion = _a_float(celdas[6]) if len(celdas) > 6 else None
        if altura is None:
            continue  # "sin datos" ese dia, no actualizamos con basura
        resultado[nombre_estacion] = {
            "altura": altura,
            "alerta": alerta,
            "evacuacion": evacuacion,
        }
    return resultado


def actualizar_backend(localidad: str, nivel_metros: float) -> bool:
    try:
        r = requests.post(
            f"{BACKEND_URL}/hidrologia/actualizar",
            json={"localidad": localidad, "nivel_metros": nivel_metros},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  [ERROR] No se pudo actualizar {localidad}: {e}")
        return False


def main():
    print(f"=== Actualizador de niveles - {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Fuente: {URL_FUENTE}")
    print(f"Backend: {BACKEND_URL}\n")

    try:
        datos = obtener_datos_estaciones()
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
            ok = actualizar_backend(clave, info["altura"])
            (actualizadas if ok else fallidas).append(clave)

    print("\n--- Localidades sin fuente publica disponible (sin tocar) ---")
    for clave in SIN_FUENTE_DISPONIBLE:
        print(f"  {clave}: sigue con dato de referencia")

    print(f"\nResumen: {len(actualizadas)} actualizadas OK, {len(fallidas)} con error.")
    if fallidas:
        print("Fallidas:", fallidas)
        sys.exit(1)


if __name__ == "__main__":
    main()
