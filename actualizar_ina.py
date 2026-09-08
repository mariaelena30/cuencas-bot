"""
actualizar_ina.py
-------------------
Portal Hidrico Chaco - Trae datos del INA (Instituto Nacional del Agua),
el organismo NACIONAL que pronostica el rio Parana (no solo mide como
Prefectura - PRONOSTICA a 7-15 dias).

Fuente: https://alerta.ina.gob.ar/a5/diario/reporte_diario (publica, sin
necesidad de API key). Se actualiza todos los dias. Contiene una tabla
con nivel actual + tendencia por estacion, y un texto narrativo de
pronostico por sistema de rios (Parana, Paraguay, Iguazu, Uruguay).

QUE HACE ESTE SCRIPT:
1. Descarga la pagina del reporte diario.
2. Extrae la fila de Barranqueras y Corrientes de la tabla de niveles
   (son las que nos importan para el Chaco).
3. Extrae el parrafo narrativo de pronostico del sistema
   "PARAGUAY - IGUAZU - PARANA" (el que menciona Corrientes/La Paz,
   que es upstream de Barranqueras).
4. Sube todo al backend (cuencas-bot) via POST /ina/actualizar.

IMPORTANTE - HONESTIDAD DE DATOS:
Este script NO calcula ninguna prediccion propia - copia tal cual lo
que el INA ya publico. Si el HTML de la pagina cambia de estructura,
el script debe fallar de forma visible (no debe inventar un numero),
por eso cada extraccion tiene su propio try/except que loguea el error
en vez de generar un dato falso.

COMO PROGRAMARLO: GitHub Actions, 1 vez por dia (el INA solo actualiza
el reporte una vez al dia, no tiene sentido correr esto mas seguido).
"""

import os
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

INA_URL = "https://alerta.ina.gob.ar/a5/diario/reporte_diario"
BACKEND_URL = os.environ.get("PORTAL_BACKEND_URL", "https://cuencas-bot.onrender.com")
TIMEOUT_SEGUNDOS = 20

# Estaciones del INA que nos interesan para el Chaco (nombre tal cual
# aparece en la tabla del reporte diario del INA).
ESTACIONES_INA_RELEVANTES = ["Barranqueras", "Corrientes"]


def obtener_reporte_diario() -> BeautifulSoup:
    resp = requests.get(INA_URL, timeout=TIMEOUT_SEGUNDOS, headers={"User-Agent": "PortalHidricoChaco/1.0"})
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def extraer_fecha_actualizacion(soup: BeautifulSoup) -> str | None:
    """Busca el texto 'Fecha de actualización: DD/MM/AAAA' en la pagina."""
    texto = soup.get_text()
    match = re.search(r"Fecha de actualizaci[oó]n:\s*(\d{2}/\d{2}/\d{4})", texto)
    return match.group(1) if match else None


def extraer_niveles_tabla(soup: BeautifulSoup) -> dict:
    """
    Recorre la primera tabla del reporte (niveles por estacion) y
    devuelve solo las filas de ESTACIONES_INA_RELEVANTES.
    """
    resultado = {}
    tabla = soup.find("table")
    if tabla is None:
        return resultado

    filas = tabla.find_all("tr")
    for fila in filas:
        celdas = [c.get_text(strip=True) for c in fila.find_all(["td", "th"])]
        if not celdas or celdas[0] not in ESTACIONES_INA_RELEVANTES:
            continue
        try:
            nombre_estacion = celdas[0]
            rio = celdas[1]
            nivel_texto = celdas[2]  # ej: "3,26" (puede traer basura del tooltip, se limpia abajo)
            umbral_alerta = celdas[3]
            umbral_evacuacion = celdas[4]
            perspectiva = celdas[5] if len(celdas) > 5 else None

            nivel_m = float(re.sub(r"[^\d,.-]", "", nivel_texto.split()[0]).replace(",", "."))

            resultado[nombre_estacion.lower()] = {
                "rio": rio,
                "nivel_metros": nivel_m,
                "umbral_alerta": float(umbral_alerta.replace(",", ".")),
                "umbral_evacuacion": float(umbral_evacuacion.replace(",", ".")),
                "perspectiva": perspectiva,
            }
        except (ValueError, IndexError) as error:
            print(f"[actualizar_ina] No se pudo parsear la fila de {celdas[0] if celdas else '?'}: {error}")
            continue

    return resultado


def extraer_pronostico_narrativo(soup: BeautifulSoup) -> str | None:
    """
    Busca el parrafo que empieza con 'El río Paraná en Corrientes' -
    es el que menciona directamente la zona que nos interesa (Corrientes/
    La Paz, upstream de Barranqueras).
    """
    texto_completo = soup.get_text()
    match = re.search(
        r"(El río Paraná en Corrientes.*?)(?=\n\n|\nFRENTE DEL DELTA|\Z)",
        texto_completo,
        re.DOTALL,
    )
    if match:
        return " ".join(match.group(1).split())  # normaliza espacios/saltos de linea
    return None


def main() -> None:
    try:
        soup = obtener_reporte_diario()
    except requests.RequestException as error:
        print(f"[actualizar_ina] Error consultando al INA: {error}")
        return

    fecha_actualizacion = extraer_fecha_actualizacion(soup)
    niveles = extraer_niveles_tabla(soup)
    pronostico = extraer_pronostico_narrativo(soup)

    if not niveles:
        print("[actualizar_ina] No se pudo extraer ninguna estacion - la pagina puede haber cambiado de formato. No se sube nada (mejor no subir que subir un dato falso).")
        return

    payload = {
        "fuente": "Instituto Nacional del Agua (INA) - Alerta Hidrológico Cuenca del Plata",
        "url_original": INA_URL,
        "fecha_actualizacion_ina": fecha_actualizacion,
        "estaciones": niveles,
        "pronostico_narrativo": pronostico,
        "consultado_en": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    try:
        resp = requests.post(f"{BACKEND_URL}/ina/actualizar", json=payload, timeout=TIMEOUT_SEGUNDOS)
        resp.raise_for_status()
    except requests.RequestException as error:
        print(f"[actualizar_ina] Error subiendo al backend: {error}")
        return

    # Ademas de guardar el contexto INA por separado, usamos la lectura
    # de Barranqueras para actualizar el NIVEL REAL de esa localidad en
    # el sistema principal (el mismo que usan las 5 fases de alerta).
    # Esto es importante: si el scraper de Prefectura (actualizar_niveles.py)
    # esta fallando o desactualizado, esta es una segunda fuente
    # oficial que evita que el sitio se quede mostrando un numero viejo.
    if "barranqueras" in niveles:
        try:
            resp2 = requests.post(
                f"{BACKEND_URL}/hidrologia/actualizar",
                json={"localidad": "barranqueras", "nivel_metros": niveles["barranqueras"]["nivel_metros"]},
                timeout=TIMEOUT_SEGUNDOS,
            )
            resp2.raise_for_status()
            print(f"[actualizar_ina] Nivel real de Barranqueras actualizado: {niveles['barranqueras']['nivel_metros']}m")
        except requests.RequestException as error:
            print(f"[actualizar_ina] Se subio el contexto INA pero fallo la actualizacion de nivel de barranqueras: {error}")

    print(f"[actualizar_ina] OK: {len(niveles)} estacion(es) del INA actualizadas ({fecha_actualizacion}).")


if __name__ == "__main__":
    main()
