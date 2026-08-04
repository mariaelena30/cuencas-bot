"""
Datos y lógica de las 4 cuencas monitoreadas.
 
IMPORTANTE: los valores de 'nivel_metros' de abajo son datos SEMILLA
(de demostración), no una conexión en vivo a ninguna fuente. Cada cuenca
tiene 'fuente_datos' indicando de dónde deberían salir los datos reales
y 'conectado' en False hasta que se integre esa fuente.
 
Para actualizar un valor manualmente mientras no hay integración
automática, modificar el diccionario CUENCAS o cargar desde el backend
FastAPI (main.py) vía sus endpoints POST.
"""

from datetime import datetime

CUENCAS = {
    "parana": {
        "nombre": "Río Paraná",
        "estacion": "Barranqueras",
        "nivel_metros": 3.22,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "paraguay": {
        "nombre": "Río Paraguay",
        "estacion": "Puerto Bermejo / confluencia",
        "nivel_metros": 4.10,
        "umbral_alerta": 5.50,
        "umbral_evacuacion": 6.00,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "bermejo": {
        "nombre": "Río Bermejo",
        "estacion": "Presidencia de la Plaza (aprox.)",
        "nivel_metros": 2.80,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "fuente_datos": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "pilcomayo": {
        "nombre": "Río Pilcomayo",
        "estacion": "Zona norte de Chaco / límite con Formosa",
        "nivel_metros": 1.95,
        "umbral_alerta": 3.50,
        "umbral_evacuacion": 4.00,
        "fuente_datos": "Reportes Prefectura / Comisión Binacional (sin API pública estable)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
}

def obtener_estado(clave_cuenca: str) -> dict:
    """Devuelve el estado clasificado de una cuenca (verde/amarillo/rojo)."""
    cuenca = CUENCAS.get(clave_cuenca)
    if cuenca is None:
        return None

    nivel = cuenca["nivel_metros"]
    if nivel >= cuenca["umbral_evacuacion"]:
        estado, emoji = "EVACUACIÓN", "🔴"
    elif nivel >= cuenca["umbral_alerta"]:
        estado, emoji = "ALERTA", "🟡"
    else:
        estado, emoji = "NORMAL", "🟢"

    return {**cuenca, "estado": estado, "emoji": emoji}


def resumen_todas() -> list:
    """Devuelve el estado de las 4 cuencas para el comando /cuencas."""
    return [obtener_estado(clave) for clave in CUENCAS]
