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


# Ciudades/localidades monitoreadas dentro de las cuencas. Cada una
# pertenece a una cuenca (clave 'cuenca') y tiene su propio nivel de río
# porque el agua no sube igual en cada punto — por eso separamos ciudad
# de cuenca, aunque compartan el mismo río.
CIUDADES = {
    "resistencia": {
        "nombre": "Resistencia",
        "cuenca": "parana",
        "nivel_metros": 3.15,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "barranqueras": {
        "nombre": "Barranqueras",
        "cuenca": "parana",
        "nivel_metros": 3.22,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "corrientes": {
        "nombre": "Corrientes (capital)",
        "cuenca": "parana",
        "nivel_metros": 3.30,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "formosa": {
        "nombre": "Formosa (capital)",
        "cuenca": "paraguay",
        "nivel_metros": 4.05,
        "umbral_alerta": 5.50,
        "umbral_evacuacion": 6.00,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "puerto_bermejo": {
        "nombre": "Puerto Bermejo",
        "cuenca": "bermejo",
        "nivel_metros": 2.75,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "fuente_datos": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "el_sauzalito": {
        "nombre": "El Sauzalito",
        "cuenca": "pilcomayo",
        "nivel_metros": 1.90,
        "umbral_alerta": 3.50,
        "umbral_evacuacion": 4.00,
        "fuente_datos": "Reportes Prefectura / Comisión Binacional (sin API pública estable)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "isla_del_cerrito": {
        "nombre": "Isla del Cerrito",
        "cuenca": "parana",
        "nivel_metros": 3.35,
        "umbral_alerta": 5.50,
        "umbral_evacuacion": 6.00,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "puerto_vilelas": {
        "nombre": "Puerto Vilelas",
        "cuenca": "parana",
        "nivel_metros": 3.20,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "la_leonesa": {
        "nombre": "La Leonesa",
        "cuenca": "paraguay",
        "nivel_metros": 3.90,
        "umbral_alerta": 5.50,
        "umbral_evacuacion": 6.00,
        "fuente_datos": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "pampa_del_indio": {
        "nombre": "Pampa del Indio",
        "cuenca": "bermejo",
        "nivel_metros": 2.90,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "fuente_datos": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "villa_rio_bermejito": {
        "nombre": "Villa Río Bermejito",
        "cuenca": "bermejo",
        "nivel_metros": 2.70,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "fuente_datos": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04 (dato semilla)",
    },
    "fuerte_esperanza": {
        "nombre": "Fuerte Esperanza",
        "cuenca": "pilcomayo",
        "nivel_metros": 1.85,
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


def obtener_estado_ciudad(clave_ciudad: str) -> dict:
    """Devuelve el estado clasificado de una ciudad/localidad."""
    ciudad = CIUDADES.get(clave_ciudad)
    if ciudad is None:
        return None

    nivel = ciudad["nivel_metros"]
    if nivel >= ciudad["umbral_evacuacion"]:
        estado, emoji = "EVACUACIÓN", "🔴"
    elif nivel >= ciudad["umbral_alerta"]:
        estado, emoji = "ALERTA", "🟡"
    else:
        estado, emoji = "NORMAL", "🟢"

    return {**ciudad, "estado": estado, "emoji": emoji}


def ciudades_de_cuenca(clave_cuenca: str) -> list:
    """Devuelve las ciudades que pertenecen a una cuenca dada."""
    claves = [c for c, v in CIUDADES.items() if v["cuenca"] == clave_cuenca]
    return [obtener_estado_ciudad(c) for c in claves]


def resumen_todas() -> list:
    """Devuelve el estado de las 4 cuencas para el comando /cuencas."""
    return [obtener_estado(clave) for clave in CUENCAS]

