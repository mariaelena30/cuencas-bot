"""
Sincroniza alertas meteorologicas del SMN para el Chaco, con foco especial
en localidades SIN rio cerca (inundacion pluvial) como Santa Sylvina, que
no aparecen cubiertas por ninguna fuente hidrologica (INA/Prefectura).

Sube al backend del Portal Hidrico Chaco (cuencas-bot) las alertas que
mencionen la provincia en general, y marca por separado las que nombran
puntualmente a una localidad pluvial vigilada.
"""
import os
from datetime import datetime, timezone

import requests

SMN_ALERTS_URL = "https://ws.smn.gob.ar/alerts"
BACKEND_URL = os.environ.get("PORTAL_BACKEND_URL", "https://cuencas-bot.onrender.com")
TIMEOUT_SEGUNDOS = 15

# Localidades sin rio cerca que dependen 100% de avisos de lluvia del SMN,
# porque ninguna fuente hidrologica (INA/Prefectura) las cubre.
# Agregar mas nombres aca a medida que se identifiquen (en minusculas).
LOCALIDADES_PLUVIALES = {
    "santa sylvina": "santa_sylvina",
    # "hermoso campo": "hermoso_campo",   # ejemplo para sumar a futuro
    # "charata": "charata",
}


def obtener_alertas_smn() -> list[dict]:
    resp = requests.get(SMN_ALERTS_URL, timeout=TIMEOUT_SEGUNDOS)
    resp.raise_for_status()
    datos = resp.json()
    return datos if isinstance(datos, list) else datos.get("alerts", [])


def texto_completo(alerta: dict) -> str:
    return " ".join(str(v) for v in alerta.values() if isinstance(v, str)).lower()


def es_de_chaco(texto: str) -> bool:
    return "chaco" in texto


def localidades_pluviales_mencionadas(texto: str) -> list[str]:
    """Devuelve las claves internas de las localidades pluviales vigiladas
    que aparecen mencionadas por nombre en el texto de la alerta."""
    return [clave for nombre, clave in LOCALIDADES_PLUVIALES.items() if nombre in texto]


def normalizar(alerta: dict, localidades_afectadas: list[str]) -> dict:
    return {
        "id": alerta.get("id") or alerta.get("identifier") or alerta.get("titulo"),
        "titulo": alerta.get("title") or alerta.get("titulo") or "Alerta meteorologica",
        "descripcion": alerta.get("description") or alerta.get("descripcion", ""),
        "nivel": alerta.get("level") or alerta.get("color") or "sin especificar",
        "zona": alerta.get("zone") or alerta.get("area", ""),
        "fuente": "Servicio Meteorologico Nacional (SMN)",
        "localidades_pluviales_afectadas": localidades_afectadas,
    }


def main() -> None:
    try:
        alertas_nacionales = obtener_alertas_smn()
    except (requests.RequestException, ValueError) as error:
        print(f"[actualizar_alertas_smn] Error consultando al SMN: {error}")
        return

    alertas_relevantes = []
    for alerta in alertas_nacionales:
        texto = texto_completo(alerta)
        localidades_afectadas = localidades_pluviales_mencionadas(texto)
        if es_de_chaco(texto) or localidades_afectadas:
            alertas_relevantes.append(normalizar(alerta, localidades_afectadas))

    payload = {
        "alertas": alertas_relevantes,
        "cantidad": len(alertas_relevantes),
        "ultima_verificacion": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    try:
        resp = requests.post(f"{BACKEND_URL}/alertas/actualizar", json=payload, timeout=TIMEOUT_SEGUNDOS)
        resp.raise_for_status()
    except requests.RequestException as error:
        print(f"[actualizar_alertas_smn] Error subiendo al backend: {error}")
        return

    con_localidad_pluvial = [a for a in alertas_relevantes if a["localidades_pluviales_afectadas"]]
    print(f"[actualizar_alertas_smn] OK: {len(alertas_relevantes)} alerta(s) de Chaco, "
          f"{len(con_localidad_pluvial)} mencionan localidades pluviales vigiladas.")


if __name__ == "__main__":
    main()
