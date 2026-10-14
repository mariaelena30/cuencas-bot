"""
Carga del historial diario de niveles - Portal Hidrico Chaco.

La UNL (CIM-FICH) publica, para cada estacion, una pagina "Historico" con una
lectura por dia durante el ultimo año (fecha, hora, altura, variacion, altura
anterior). Este script baja los ultimos DIAS dias de las estaciones que usa el
portal y los manda al backend, asi el grafico y la tendencia se arman con
datos reales desde el primer dia (en vez de esperar a juntar lecturas).

- Es seguro correrlo varias veces: el backend guarda UNA lectura por dia y
  la de la fuente reemplaza a la que ya estaba para ese dia.
- Las fechas de la fuente estan en hora de Argentina (UTC-3).
- Usa la misma clave API_KEY_SENSORES que actualizar_niveles.py.

Fuente: Prefectura Naval Argentina, via CIM-FICH-UNL
        https://fich.unl.edu.ar/cim/rios/historico/<id de estacion>
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from actualizar_niveles import (
    BACKEND_URL,
    MAPEO_ESTACIONES,
    TIMEOUT,
    _a_float,
    despertar_backend,
)

# Numero de estacion en las paginas de historico de la fuente
ID_ESTACION = {
    "Barranqueras": 25,
    "Isla del Cerrito": 49,
    "Bermejo": 48,
    "Las Palmas": 51,
}

# Se prueban en este orden; si el primero falla se usa el segundo
URLS_BASE = [
    "http://wfich1.unl.edu.ar/cim/rios/historico/{id}",
    "https://fich.unl.edu.ar/cim/rios/historico/{id}",
]

DIAS = 60  # el backend guarda como maximo 90
ZONA_ARGENTINA = timezone(timedelta(hours=-3))  # sin horario de verano


def parsear_historico(html: str, dias: int = DIAS, ahora: datetime | None = None) -> list:
    """Devuelve [{"fecha": ISO con -03:00, "altura_m": float}, ...] de los
    ultimos `dias` dias, ordenado de mas viejo a mas nuevo. Se ignoran las
    filas sin altura o con fecha ilegible."""
    ahora = ahora or datetime.now(ZONA_ARGENTINA)
    desde = ahora - timedelta(days=dias)

    soup = BeautifulSoup(html, "lxml")
    tabla = None
    for t in soup.find_all("table"):
        encabezado = t.get_text(" ", strip=True).lower()
        if "fecha" in encabezado and "altura" in encabezado:
            tabla = t
            break
    if tabla is None:
        raise RuntimeError("No se encontro la tabla de historico (la pagina pudo cambiar).")

    lecturas = []
    for fila in tabla.find_all("tr"):
        celdas = [c.get_text(strip=True) for c in fila.find_all(["td", "th"])]
        if len(celdas) < 3:
            continue
        try:
            momento = datetime.strptime(f"{celdas[0]} {celdas[1]}", "%d/%m/%Y %H:%M")
        except ValueError:
            continue  # encabezado u otra fila
        momento = momento.replace(tzinfo=ZONA_ARGENTINA)
        altura = _a_float(celdas[2])
        if altura is None or momento < desde or momento > ahora + timedelta(days=1):
            continue
        lecturas.append({"fecha": momento.isoformat(), "altura_m": altura})

    lecturas.sort(key=lambda l: l["fecha"])
    return lecturas


def descargar(id_estacion: int) -> str:
    ultimo_error = None
    for plantilla in URLS_BASE:
        url = plantilla.format(id=id_estacion)
        for intento in range(1, 3):
            try:
                r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                return r.text
            except requests.RequestException as e:
                ultimo_error = e
                print(f"  {url} no respondio (intento {intento}/2): {e}")
                time.sleep(5)
    raise RuntimeError(f"No se pudo bajar el historico de la estacion {id_estacion}: {ultimo_error}")


def enviar(localidad: str, lecturas: list, intentos: int = 3) -> bool:
    clave_api = os.environ.get("API_KEY_SENSORES", "")
    for intento in range(1, intentos + 1):
        try:
            r = requests.post(
                f"{BACKEND_URL}/hidrologia/historico",
                json={"localidad": localidad, "lecturas": lecturas},
                headers={"X-API-Key": clave_api},
                timeout=TIMEOUT,
            )
            if r.status_code in (401, 403):
                print(f"  [ERROR] {localidad}: clave rechazada ({r.status_code}).")
                return False
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"  [ERROR] {localidad}, intento {intento}/{intentos}: {e}")
            if intento < intentos:
                time.sleep(15)
    return False


def main():
    print(f"=== Carga de historico - {datetime.now(timezone.utc).isoformat()} ===")
    if not os.environ.get("API_KEY_SENSORES"):
        print("[ERROR FATAL] Falta la variable de entorno API_KEY_SENSORES.")
        sys.exit(1)

    despertar_backend()

    ok, fallidas = [], []
    for estacion, id_estacion in ID_ESTACION.items():
        try:
            lecturas = parsear_historico(descargar(id_estacion))
        except Exception as e:
            print(f"[ERROR] {estacion}: {e}")
            fallidas.extend(d["localidad"] for d in MAPEO_ESTACIONES[estacion])
            continue
        if not lecturas:
            print(f"[AVISO] {estacion}: la fuente no trajo lecturas validas; no se envia nada.")
            fallidas.extend(d["localidad"] for d in MAPEO_ESTACIONES[estacion])
            continue
        print(f"{estacion}: {len(lecturas)} lecturas "
              f"({lecturas[0]['fecha'][:10]} a {lecturas[-1]['fecha'][:10]})")
        for destino in MAPEO_ESTACIONES[estacion]:
            clave = destino["localidad"]
            (ok if enviar(clave, lecturas) else fallidas).append(clave)

    print(f"\nResumen: {len(ok)} localidades cargadas, {len(fallidas)} con error.")
    if fallidas:
        print("Fallidas:", fallidas)
        sys.exit(1)


if __name__ == "__main__":
    main()
