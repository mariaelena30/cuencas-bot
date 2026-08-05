"""
Backend del Portal Hidrico Chaco.

Fuente unica de datos para el dashboard de Streamlit y el bot de
Telegram, asi no quedan datos duplicados y desincronizados entre
proyectos.

IMPORTANTE SOBRE LOS DATOS:
Los valores de abajo son datos SEMILLA (de referencia/demostracion), no
una conexion automatica en vivo. Cada localidad/cuenca indica
'conectado: False' hasta que se integre su fuente real. Se actualizan
a mano por ahora via los endpoints POST, o reemplazando los valores de
este archivo.
"""

from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Portal Hidrico Chaco - API")

# ---------------------------------------------------------------------
# EXPLICACIONES EN LENGUAJE SIMPLE
# ---------------------------------------------------------------------
EXPLICACIONES = {
    "nivel_metros": (
        "Es cuanto subio el agua del rio en ese punto, medido en metros. "
        "Cuando supera el 'umbral de alerta', hay que empezar a prestar "
        "atencion; si supera el 'umbral de evacuacion', es momento de "
        "seguir las indicaciones de Defensa Civil."
    ),
    "ndvi": (
        "El NDVI mide que tan 'verde' y sana esta la vegetacion vista "
        "desde satelite. Sirve como pista indirecta: cambios bruscos "
        "pueden indicar sequia, inundacion o degradacion del suelo en "
        "la zona."
    ),
    "oni": (
        "El indice ONI mide si el oceano Pacifico esta mas caliente "
        "(El Nino, mas lluvia en la region) o mas frio (La Nina, menos "
        "lluvia) que lo normal. Ayuda a anticipar si se viene una "
        "temporada mas humeda o mas seca."
    ),
    "precipitacion_acumulada_mm": (
        "Es la cantidad de lluvia caida, sumada en un periodo (ultimas "
        "24 o 72 horas), medida en milimetros. Lluvia muy concentrada "
        "en pocas horas es lo que mas rapido puede hacer subir un rio."
    ),
}

# ---------------------------------------------------------------------
# CUENCAS — datos representativos de cada una de las 4 cuencas
# ---------------------------------------------------------------------
CUENCAS: dict = {
    "parana": {
        "nombre": "Rio Parana",
        "estacion": "Barranqueras",
        "nivel_metros": 3.22,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "paraguay": {
        "nombre": "Rio Paraguay",
        "estacion": "Puerto Bermejo / confluencia",
        "nivel_metros": 4.10,
        "umbral_alerta": 5.50,
        "umbral_evacuacion": 6.00,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "bermejo": {
        "nombre": "Rio Bermejo",
        "estacion": "Presidencia de la Plaza (aprox.)",
        "nivel_metros": 2.80,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "pilcomayo": {
        "nombre": "Rio Pilcomayo",
        "estacion": "Zona norte de Chaco / limite con Formosa",
        "nivel_metros": 1.95,
        "umbral_alerta": 3.50,
        "umbral_evacuacion": 4.00,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
}

# ---------------------------------------------------------------------
# LOCALIDADES — cada una con su cuenca_clave para poder agruparlas
# ---------------------------------------------------------------------
localidades: dict = {
    "resistencia": {
        "nombre": "Resistencia", "cuenca_clave": "parana", "nivel_metros": 3.15,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica / Prefectura Naval",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "barranqueras": {
        "nombre": "Barranqueras", "cuenca_clave": "parana", "nivel_metros": 3.22,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica / Prefectura Naval",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "corrientes": {
        "nombre": "Corrientes (capital)", "cuenca_clave": "parana", "nivel_metros": 3.30,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 11.0,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica / Prefectura Naval",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "formosa": {
        "nombre": "Formosa (capital)", "cuenca_clave": "paraguay", "nivel_metros": 4.05,
        "umbral_alerta": 5.50, "umbral_evacuacion": 6.00, "precipitacion_acumulada_mm": 8.0,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "puerto_bermejo": {
        "nombre": "Puerto Bermejo", "cuenca_clave": "bermejo", "nivel_metros": 2.75,
        "umbral_alerta": 4.50, "umbral_evacuacion": 5.00, "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "el_sauzalito": {
        "nombre": "El Sauzalito", "cuenca_clave": "pilcomayo", "nivel_metros": 1.90,
        "umbral_alerta": 3.50, "umbral_evacuacion": 4.00, "precipitacion_acumulada_mm": 5.0,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "isla_del_cerrito": {
        "nombre": "Isla del Cerrito", "cuenca_clave": "parana", "nivel_metros": 3.35,
        "umbral_alerta": 5.50, "umbral_evacuacion": 6.00, "precipitacion_acumulada_mm": 12.0,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica / Prefectura Naval",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "puerto_vilelas": {
        "nombre": "Puerto Vilelas", "cuenca_clave": "parana", "nivel_metros": 3.20,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica / Prefectura Naval",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "la_leonesa": {
        "nombre": "La Leonesa", "cuenca_clave": "paraguay", "nivel_metros": 3.90,
        "umbral_alerta": 5.50, "umbral_evacuacion": 6.00, "precipitacion_acumulada_mm": 10.0,
        "fuente": "INA - Sistema Nacional de Informacion Hidrica / Prefectura Naval",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "pampa_del_indio": {
        "nombre": "Pampa del Indio", "cuenca_clave": "bermejo", "nivel_metros": 2.90,
        "umbral_alerta": 4.50, "umbral_evacuacion": 5.00, "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "villa_rio_bermejito": {
        "nombre": "Villa Rio Bermejito", "cuenca_clave": "bermejo", "nivel_metros": 2.70,
        "umbral_alerta": 4.50, "umbral_evacuacion": 5.00, "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "fuerte_esperanza": {
        "nombre": "Fuerte Esperanza", "cuenca_clave": "pilcomayo", "nivel_metros": 1.85,
        "umbral_alerta": 3.50, "umbral_evacuacion": 4.00, "precipitacion_acumulada_mm": 6.0,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
}

satelital_ndvi = {
    "ndvi_promedio": 0.48,
    "condicion_vegetacion": "ESTABLE",
    "conectado": False,
    "ultima_verificacion": "2026-08-04",
}

clima = {
    "fase_oni": "Neutro",
    "ultimo_valor_oni": 0.45,
    "conectado": False,
    "ultima_verificacion": "2026-08-04",
}


# ---------------------------------------------------------------------
# CLASIFICACION DE ESTADO (verde/amarillo/rojo) — compartida
# ---------------------------------------------------------------------
def calcular_estado(nivel: float, umbral_alerta: float, umbral_evacuacion: float):
    if nivel >= umbral_evacuacion:
        return "EVACUACION", "🔴"
    if nivel >= umbral_alerta:
        return "ALERTA", "🟡"
    return "NORMAL", "🟢"


def _cuenca_con_estado(clave: str) -> dict:
    c = CUENCAS[clave]
    estado, emoji = calcular_estado(c["nivel_metros"], c["umbral_alerta"], c["umbral_evacuacion"])
    return {**c, "clave": clave, "estado": estado, "emoji": emoji}


def _localidad_con_estado(clave: str) -> dict:
    loc = localidades[clave]
    estado, emoji = calcular_estado(loc["nivel_metros"], loc["umbral_alerta"], loc["umbral_evacuacion"])
    return {**loc, "clave": clave, "estado": estado, "emoji": emoji}


# ---------------------------------------------------------------------
# MODELOS para los endpoints de actualizacion manual
# ---------------------------------------------------------------------
class ActualizacionHidrologia(BaseModel):
    localidad: str
    nivel_metros: float
    precipitacion_acumulada_mm: float | None = None


class ActualizacionSatelital(BaseModel):
    ndvi_promedio: float
    condicion_vegetacion: str


# ---------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------
@app.get("/")
def raiz():
    return {"servicio": "Portal Hidrico Chaco - API", "estado": "activo"}


@app.get("/localidades")
def listar_localidades():
    """Devuelve todas las localidades con su estado calculado."""
    return {
        "localidades": {clave: _localidad_con_estado(clave) for clave in localidades},
        "explicaciones": EXPLICACIONES,
    }


@app.get("/localidades/{clave}")
def obtener_localidad(clave: str):
    clave = clave.lower()
    if clave not in localidades:
        return {"error": f"Localidad '{clave}' no encontrada"}
    return {"localidad": _localidad_con_estado(clave), "explicaciones": EXPLICACIONES}


@app.get("/cuencas")
def listar_cuencas():
    """Devuelve las 4 cuencas con su estado calculado (para /cuencas del bot)."""
    return {
        "cuencas": {clave: _cuenca_con_estado(clave) for clave in CUENCAS},
        "explicaciones": EXPLICACIONES,
    }


@app.get("/cuencas/{clave}")
def obtener_cuenca(clave: str):
    """Devuelve una cuenca puntual junto con las localidades que le pertenecen."""
    clave = clave.lower()
    if clave not in CUENCAS:
        return {"error": f"Cuenca '{clave}' no encontrada"}
    localidades_de_la_cuenca = [
        _localidad_con_estado(c) for c, v in localidades.items() if v["cuenca_clave"] == clave
    ]
    return {
        "cuenca": _cuenca_con_estado(clave),
        "localidades": localidades_de_la_cuenca,
        "explicaciones": EXPLICACIONES,
    }


@app.get("/bot/consultar")
def consultar_para_bot():
    """Endpoint de compatibilidad con el dashboard de Streamlit actual."""
    barr = _localidad_con_estado("barranqueras")
    return {
        "clima": clima,
        "hidrologia": {
            "estacion": barr["nombre"],
            "nivel_metros": barr["nivel_metros"],
            "estado": barr["estado"],
            "umbral_alerta": barr["umbral_alerta"],
            "umbral_evacuacion": barr["umbral_evacuacion"],
            "fuente": barr["fuente"],
            "ultima_verificacion": barr["ultima_verificacion"],
        },
        "satelital_ndvi": satelital_ndvi,
    }


@app.post("/hidrologia/actualizar")
def actualizar_hidrologia(datos: ActualizacionHidrologia):
    clave = datos.localidad.lower()
    if clave not in localidades:
        return {"error": f"Localidad '{datos.localidad}' no reconocida"}
    localidades[clave]["nivel_metros"] = datos.nivel_metros
    if datos.precipitacion_acumulada_mm is not None:
        localidades[clave]["precipitacion_acumulada_mm"] = datos.precipitacion_acumulada_mm
    localidades[clave]["conectado"] = True
    localidades[clave]["ultima_verificacion"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {"ok": True, "localidad": _localidad_con_estado(clave)}


@app.post("/satelital/actualizar")
def actualizar_satelital(datos: ActualizacionSatelital):
    satelital_ndvi["ndvi_promedio"] = datos.ndvi_promedio
    satelital_ndvi["condicion_vegetacion"] = datos.condicion_vegetacion
    satelital_ndvi["conectado"] = True
    satelital_ndvi["ultima_verificacion"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {"ok": True, "satelital_ndvi": satelital_ndvi}
