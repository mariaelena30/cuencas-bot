"""
Carga manual VERIFICADA de una lectura de rio - Portal Hidrico Chaco.

Sirve para cuando la tabla diaria de la UNL esta atrasada y Prefectura Naval
de la zona informo una lectura mas nueva (por ejemplo, la de las 22:00). La
carga una persona autorizada, desde GitHub Actions ("Run workflow"): no hay
formulario publico ni forma de cargar datos desde el portal.

Cada lectura queda guardada con:
  - la hora REAL de la lectura (no la hora en que se cargo),
  - la fuente declarada,
  - quien la cargo.

Datos de entrada (variables de entorno, las completa el workflow):
  ESTACION      nombre de la estacion de la fuente: Barranqueras, etc.
  ALTURA_M      altura en metros, ej. 6.36 (se acepta coma)
  FECHA_HORA    hora de la lectura en hora de Argentina: AAAA-MM-DD HH:MM
  FUENTE        de donde salio (por defecto, Prefectura de la zona)
  CARGADO_POR   nombre de quien carga
  API_KEY_SENSORES  la misma clave de escritura que usa el resto (secreto)
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from actualizar_niveles import BACKEND_URL, MAPEO_ESTACIONES, TIMEOUT, despertar_backend

ZONA_ARGENTINA = timezone(timedelta(hours=-3))  # sin horario de verano


def _error(mensaje: str):
    print(f"[ERROR] {mensaje}")
    sys.exit(1)


def leer_entradas():
    estacion = (os.environ.get("ESTACION") or "").strip()
    if estacion not in MAPEO_ESTACIONES:
        _error(f"Estacion '{estacion}' no reconocida. Opciones: {', '.join(MAPEO_ESTACIONES)}")

    texto_altura = (os.environ.get("ALTURA_M") or "").strip().replace(",", ".")
    try:
        altura = float(texto_altura)
    except ValueError:
        _error(f"Altura invalida: '{texto_altura}'. Ejemplo: 6.36")
    if not (0.0 <= altura <= 20.0):
        _error(f"Altura fuera de rango razonable: {altura} m")

    texto_fecha = (os.environ.get("FECHA_HORA") or "").strip()
    momento = None
    for formato in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            momento = datetime.strptime(texto_fecha, formato).replace(tzinfo=ZONA_ARGENTINA)
            break
        except ValueError:
            continue
    if momento is None:
        _error(f"Fecha y hora invalidas: '{texto_fecha}'. Formato: 2026-10-16 22:00")

    ahora = datetime.now(timezone.utc)
    if momento > ahora + timedelta(minutes=10):
        _error("La hora de la lectura esta en el futuro. Revisa fecha y hora (hora de Argentina).")
    if momento < ahora - timedelta(hours=72):
        _error("La lectura tiene mas de 72 horas: no se carga como lectura actual.")

    fuente = (os.environ.get("FUENTE") or "").strip() or "Prefectura Naval Argentina, zona Barranqueras (carga manual)"
    cargado_por = (os.environ.get("CARGADO_POR") or "").strip()
    if not cargado_por:
        _error("Falta indicar quien carga la lectura.")

    return estacion, altura, momento, fuente, cargado_por


def enviar(localidad, altura, momento, fuente, cargado_por, intentos=3) -> bool:
    clave_api = os.environ.get("API_KEY_SENSORES", "")
    for intento in range(1, intentos + 1):
        try:
            r = requests.post(
                f"{BACKEND_URL}/hidrologia/actualizar",
                json={
                    "localidad": localidad,
                    "nivel_metros": altura,
                    "manual": True,
                    "momento_lectura": momento.isoformat(),
                    "fuente_lectura": fuente,
                    "cargado_por": cargado_por,
                },
                headers={"X-API-Key": clave_api},
                timeout=TIMEOUT,
            )
            if r.status_code in (401, 403):
                print(f"  [ERROR] {localidad}: clave rechazada ({r.status_code}).")
                return False
            if r.status_code == 422:
                # El backend rechazo la lectura (por ejemplo, ya hay una mas nueva): no se reintenta
                print(f"  [RECHAZADA] {localidad}: {r.json().get('detail', r.text)}")
                return False
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"  [ERROR] {localidad}, intento {intento}/{intentos}: {e}")
            if intento < intentos:
                time.sleep(15)
    return False


def main():
    if not os.environ.get("API_KEY_SENSORES"):
        _error("Falta la variable de entorno API_KEY_SENSORES.")

    estacion, altura, momento, fuente, cargado_por = leer_entradas()
    print("=== Carga manual de lectura ===")
    print(f"Estacion: {estacion} | Altura: {altura:.2f} m")
    print(f"Hora de la lectura (Argentina): {momento.strftime('%d/%m/%Y %H:%M')}")
    print(f"Fuente: {fuente} | Cargado por: {cargado_por}\n")

    despertar_backend()

    ok, fallidas = [], []
    for destino in MAPEO_ESTACIONES[estacion]:
        clave = destino["localidad"]
        etiqueta = "medicion directa" if destino["exacto"] else "APROXIMADO, estacion cercana"
        print(f"-> {clave} ({etiqueta})")
        (ok if enviar(clave, altura, momento, fuente, cargado_por) else fallidas).append(clave)

    print(f"\nResumen: {len(ok)} localidades actualizadas, {len(fallidas)} con problema.")
    if fallidas:
        print("Con problema:", fallidas)
        sys.exit(1)


if __name__ == "__main__":
    main()
