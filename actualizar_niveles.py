"""
Actualizador automatico de niveles de rio - Portal Hidrico Chaco.

FUENTE PRINCIPAL: API publica del INA (Sistema de Informacion y Alerta
Hidrologica, https://alerta.ina.gob.ar/a5). Las estaciones Barranqueras,
Bermejo e Isla del Cerrito vienen de la red "escalas Prefectura Nacional",
es decir, las mismas lecturas de Prefectura Naval Argentina que antes se
tomaban via la pagina de la FICH-UNL.
FUENTE DE RESPALDO: tabla de la FICH-UNL (https://fich.unl.edu.ar/cim/rios/parana/alturas)
Se usa solo para las estaciones que el INA no devuelva, y para el panel
"aguas arriba" (tabla completa de estaciones).

IMPORTANTE SOBRE PRECISION (leer antes de tocar el mapeo):
- 2 localidades tienen estacion propia y exacta: Barranqueras, Isla del Cerrito.
- 4 localidades usan la estacion mas cercana del MISMO tramo de rio
  (Resistencia y Puerto Vilelas -> Barranqueras; Puerto Bermejo -> "Bermejo";
  La Leonesa -> "Las Palmas"). Son aproximaciones, NO el punto exacto.
- "Las Palmas" NO figura en el catalogo del INA (verificado 04/11/2026):
  La Leonesa solo se actualiza si responde la FICH. No se inventa un codigo.
- 4 localidades NO tienen dato real en estas fuentes (cuencas del Bermejo):
  El Sauzalito, Pampa del Indio, Villa Rio Bermejito, Fuerte Esperanza.

NOTA (02/10/2026): el backend exige la clave en el header X-API-Key, que se lee
de la variable de entorno API_KEY_SENSORES. Nunca escribirla en este archivo.

NOTA (04/11/2026): la FICH empezo a fallar. Se agrego el INA como fuente
principal. Reglas de seguridad nuevas:
  * Se usa la altura media diaria (serie Hmd, var 39) del INA.
  * Si el dato mas reciente tiene mas de MAX_ANTIGUEDAD_DIAS dias, NO se envia
    (mejor dejar el valor cargado a mano que publicar un nivel viejo como actual).
  * Si ninguna fuente responde, el script avisa y termina sin tocar el backend.

Alturas de referencia INA (m, escala de Prefectura): Barranqueras alerta 6,00 /
evacuacion 6,50; Bermejo alerta 6,50 / evacuacion 7,00.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

BACKEND_URL = "https://cuencas-bot.onrender.com"  # cambiar si el backend se muda
TIMEOUT = 60.0  # Render gratis puede tardar hasta 1 minuto en despertar
HEADERS = {"User-Agent": "Mozilla/5.0 (PortalHidricoChaco actualizador)"}

INA_URL = "https://alerta.ina.gob.ar/a5/getObservaciones"
MAX_ANTIGUEDAD_DIAS = 3

URLS_FICH = [
    "https://fich.unl.edu.ar/cim/rios/parana/alturas",
    "http://wfich1.unl.edu.ar/cim/rios/parana/alturas",
]

# Estacion -> serie del INA (Altura hidrometrica media diaria, medicion directa)
SERIES_INA = {
    "Barranqueras": 26262,      # estacion INA 20
    "Bermejo": 26300,           # estacion INA 58
    "Isla del Cerrito": 26301,  # estacion INA 59
}

# ---------------------------------------------------------------------
# MAPEO estacion -> localidad del portal
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

SIN_FUENTE_DISPONIBLE = [
    "el_sauzalito", "pampa_del_indio", "villa_rio_bermejito", "fuerte_esperanza",
]

# Posicion de cada columna en la tabla de la FICH
COL_ALTURA = 2
COL_ALTURA_ANTERIOR = 5
COL_ALERTA = 6
COL_EVACUACION = 7


def _a_float(texto: str):
    """Convierte '6,31' -> 6.31. Devuelve None si no es un numero valido."""
    texto = texto.strip().replace(",", ".")
    if texto in ("", "-", "—", "—"):
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def despertar_backend() -> bool:
    """Render (plan gratis) se duerme por inactividad y tarda en arrancar."""
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


# ----------------------------------------------------------------------
# FUENTE PRINCIPAL: INA
# ----------------------------------------------------------------------
def parsear_observaciones_ina(obs: list, ahora=None):
    """Recibe la lista JSON de getObservaciones y devuelve
    {"altura", "variacion_24h", "fecha"} o None si no hay dato utilizable.

    - Usa el valor mas reciente con 'valor' numerico.
    - variacion_24h = ultimo - anterior (solo si el anterior es del dia previo).
    - Devuelve None si el ultimo dato supera MAX_ANTIGUEDAD_DIAS."""
    ahora = ahora or datetime.now(timezone.utc)
    validas = []
    for o in obs or []:
        valor = o.get("valor")
        inicio = o.get("timestart")
        if valor is None or not inicio:
            continue
        try:
            fecha = datetime.fromisoformat(inicio.replace("Z", "+00:00"))
            valor = float(valor)
        except (ValueError, TypeError):
            continue
        validas.append((fecha, valor))
    if not validas:
        return None
    validas.sort(key=lambda x: x[0])
    fecha, altura = validas[-1]
    if ahora - fecha > timedelta(days=MAX_ANTIGUEDAD_DIAS + 1):
        return {"altura": None, "obsoleto": True, "fecha": fecha}
    variacion = None
    if len(validas) >= 2:
        fecha_ant, valor_ant = validas[-2]
        if timedelta(hours=20) <= (fecha - fecha_ant) <= timedelta(hours=28):
            variacion = round(altura - valor_ant, 2)
    return {"altura": altura, "variacion_24h": variacion, "fecha": fecha, "obsoleto": False}


def consultar_ina(series_id: int, intentos: int = 3):
    """Pide los ultimos 6 dias de la serie. Devuelve la lista JSON o lanza."""
    hasta = datetime.now(timezone.utc) + timedelta(days=1)
    desde = hasta - timedelta(days=7)
    params = {
        "tipo": "puntual",
        "series_id": series_id,
        "timestart": desde.strftime("%Y-%m-%d"),
        "timeend": hasta.strftime("%Y-%m-%d"),
        "format": "json",
    }
    ultimo = None
    for intento in range(1, intentos + 1):
        try:
            r = requests.get(INA_URL, params=params, timeout=TIMEOUT, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                raise ValueError(f"respuesta inesperada: {type(data).__name__}")
            return data
        except Exception as e:
            ultimo = e
            print(f"  INA serie {series_id} no respondio (intento {intento}/{intentos}): {e}")
            if intento < intentos:
                time.sleep(10)
    raise RuntimeError(f"INA serie {series_id}: {ultimo}")


def obtener_datos_ina() -> dict:
    """{ 'Barranqueras': {...}, ... } con las estaciones que el INA devolvio bien."""
    resultado = {}
    for estacion, serie in SERIES_INA.items():
        try:
            info = parsear_observaciones_ina(consultar_ina(serie))
        except Exception as e:
            print(f"  [AVISO] INA fallo para {estacion}: {e}")
            continue
        if info is None:
            print(f"  [AVISO] INA sin datos para {estacion}.")
            continue
        if info.get("obsoleto"):
            print(f"  [AVISO] INA: el dato de {estacion} es del {info['fecha'].date()} "
                  f"(mas de {MAX_ANTIGUEDAD_DIAS} dias); no se envia.")
            continue
        info["fuente"] = "INA"
        resultado[estacion] = info
        print(f"  INA {estacion}: {info['altura']} m (dia {info['fecha'].date()}, "
              f"variacion {info['variacion_24h']})")
    return resultado


# ----------------------------------------------------------------------
# RESPALDO: FICH-UNL
# ----------------------------------------------------------------------
def _descargar_filas_fich():
    """Devuelve la tabla de la FICH como lista de filas, o None si no responde."""
    for url in URLS_FICH:
        for intento in range(1, 3):
            try:
                resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"  FICH {url} no respondio (intento {intento}/2): {e}")
                if getattr(e, "response", None) is not None and e.response.status_code in (403, 404):
                    break
                time.sleep(5)
                continue
            tabla = BeautifulSoup(resp.text, "lxml").find("table")
            if tabla is None:
                print(f"  FICH {url} respondio sin tabla.")
                break
            return [
                [c.get_text(strip=True) for c in fila.find_all(["td", "th"])]
                for fila in tabla.find_all("tr")
            ]
    return None


def obtener_tabla_completa(filas: list) -> list:
    """Todas las estaciones de la tabla FICH, para el panel 'aguas arriba'."""
    estaciones = []
    for celdas in filas:
        if len(celdas) < 8:
            continue
        puerto, rio = celdas[0], celdas[1]
        if not puerto or puerto.lower() == "puerto":
            continue
        altura = _a_float(celdas[COL_ALTURA])
        anterior = _a_float(celdas[COL_ALTURA_ANTERIOR])
        variacion = round(altura - anterior, 2) if altura is not None and anterior is not None else None
        estaciones.append({
            "puerto": puerto, "rio": rio, "altura_m": altura,
            "variacion_m": variacion, "altura_anterior_m": anterior,
            "alerta_m": _a_float(celdas[COL_ALERTA]),
            "evacuacion_m": _a_float(celdas[COL_EVACUACION]),
        })
    return estaciones


def obtener_datos_estaciones_fich(filas: list) -> dict:
    resultado = {}
    for celdas in filas:
        if len(celdas) < 6:
            continue
        nombre = celdas[0]
        if nombre not in MAPEO_ESTACIONES:
            continue
        altura = _a_float(celdas[COL_ALTURA])
        if altura is None:
            continue
        anterior = _a_float(celdas[COL_ALTURA_ANTERIOR]) if len(celdas) > COL_ALTURA_ANTERIOR else None
        resultado[nombre] = {
            "altura": altura,
            "variacion_24h": round(altura - anterior, 2) if anterior is not None else None,
            "fuente": "FICH",
        }
    return resultado


# ----------------------------------------------------------------------
# BACKEND
# ----------------------------------------------------------------------
def actualizar_backend(localidad: str, nivel_metros: float, variacion_24h=None, intentos: int = 3) -> bool:
    clave_api = os.environ.get("API_KEY_SENSORES", "")
    for intento in range(1, intentos + 1):
        try:
            r = requests.post(
                f"{BACKEND_URL}/hidrologia/actualizar",
                json={"localidad": localidad, "nivel_metros": nivel_metros,
                      "variacion_24h_m": variacion_24h},
                headers={"X-API-Key": clave_api},
                timeout=TIMEOUT,
            )
            if r.status_code in (401, 403):
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
    print(f"Backend: {BACKEND_URL}\n")

    if not os.environ.get("API_KEY_SENSORES"):
        print("[ERROR FATAL] Falta la variable de entorno API_KEY_SENSORES. "
              "Sin ella el backend rechaza las escrituras.")
        sys.exit(1)

    despertar_backend()

    print("Fuente principal: INA")
    datos = obtener_datos_ina()

    # Respaldo FICH: completa las estaciones que el INA no dio (p. ej. Las Palmas)
    # y trae la tabla completa para el panel "aguas arriba".
    print("\nRespaldo: FICH-UNL")
    filas = _descargar_filas_fich()
    tabla_completa = []
    if filas:
        tabla_completa = obtener_tabla_completa(filas)
        for estacion, info in obtener_datos_estaciones_fich(filas).items():
            if estacion not in datos:
                datos[estacion] = info
                print(f"  FICH {estacion}: {info['altura']} m (completa lo que no dio el INA)")
    else:
        print("  FICH no disponible (se sigue solo con el INA).")

    if not datos:
        print("::warning title=Sin fuentes de niveles::Ni el INA ni la FICH devolvieron datos utilizables.")
        print("[AVISO] No se actualizo nada. Los niveles del portal quedan con el ultimo "
              "valor cargado (manual o automatico). Cargar a mano si hace falta.")
        sys.exit(0)

    actualizadas, fallidas = [], []
    for nombre_estacion, info in datos.items():
        for destino in MAPEO_ESTACIONES[nombre_estacion]:
            clave, exacto = destino["localidad"], destino["exacto"]
            etiqueta = "medicion directa" if exacto else "APROXIMADO, estacion cercana"
            print(f"{nombre_estacion} [{info['fuente']}] ({etiqueta}) -> {clave}: {info['altura']} m")
            ok = actualizar_backend(clave, info["altura"], info.get("variacion_24h"))
            (actualizadas if ok else fallidas).append(clave)

    if tabla_completa:
        print(f"\nEnviando referencia del rio: {len(tabla_completa)} estaciones.")
        if not enviar_referencia_rio(tabla_completa):
            fallidas.append("referencia_rio")
    else:
        print("\n[AVISO] Sin tabla de referencia del rio (la FICH no respondio); "
              "el panel 'aguas arriba' queda con lo ultimo cargado.")

    sin_dato = [d["localidad"] for e, ds in MAPEO_ESTACIONES.items() if e not in datos for d in ds]
    if sin_dato:
        print("\n--- Localidades sin dato en esta corrida (se dejan como estan) ---")
        for clave in sin_dato:
            print(f"  {clave}")
    print("\n--- Localidades sin fuente publica disponible (sin tocar) ---")
    for clave in SIN_FUENTE_DISPONIBLE:
        print(f"  {clave}: sigue con dato de referencia")

    print(f"\nResumen: {len(actualizadas)} actualizadas OK, {len(fallidas)} con error.")
    if fallidas:
        print("Fallidas:", fallidas)
        sys.exit(1)


if __name__ == "__main__":
    main()
