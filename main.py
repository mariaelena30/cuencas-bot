"""
Backend del Portal Hídrico Chaco.

Sirve datos de riesgo hídrico para Resistencia, Barranqueras y Formosa
(capital), pensado para alimentar tanto el dashboard de Streamlit como,
a futuro, el bot de Telegram — un solo lugar con la información, para
no tener datos duplicados y desincronizados en dos proyectos distintos.

IMPORTANTE SOBRE LOS DATOS:
Los valores de abajo son datos SEMILLA (de referencia/demostración), no
una conexión automática en vivo. Cada localidad indica 'conectado: False'
hasta que se integre su fuente real. Se actualizan a mano por ahora vía
los endpoints POST, o reemplazando los valores de este archivo.
"""

from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Portal Hídrico Chaco - API")

# ---------------------------------------------------------------------
# EXPLICACIONES EN LENGUAJE SIMPLE
# El objetivo del proyecto es que lo entienda cualquier persona, no solo
# alguien con formación técnica. Estos textos se devuelven junto a los
# datos para que el dashboard/bot los pueda mostrar como ayuda.
# ---------------------------------------------------------------------
EXPLICACIONES = {
    "nivel_metros": (
        "Es cuánto subió el agua del río en ese punto, medido en metros. "
        "Cuando supera el 'umbral de alerta', hay que empezar a prestar "
        "atención; si supera el 'umbral de evacuación', es momento de "
        "seguir las indicaciones de Defensa Civil."
    ),
    "ndvi": (
        "El NDVI mide qué tan 'verde' y sana está la vegetación vista "
        "desde satélite. Sirve como pista indirecta: cambios bruscos "
        "pueden indicar sequía, inundación o degradación del suelo en "
        "la zona."
    ),
    "oni": (
        "El índice ONI mide si el océano Pacífico está más caliente "
        "(El Niño, más lluvia en la región) o más frío (La Niña, menos "
        "lluvia) que lo normal. Ayuda a anticipar si se viene una "
        "temporada más húmeda o más seca."
    ),
    "precipitacion_acumulada_mm": (
        "Es la cantidad de lluvia caída, sumada en un período (últimas "
        "24 o 72 horas), medida en milímetros. Lluvia muy concentrada "
        "en pocas horas es lo que más rápido puede hacer subir un río."
    ),
}

# ---------------------------------------------------------------------
# BASE DE CONOCIMIENTO — datos semilla, cargar vía POST o conectar
# fuente automática cuando esté disponible.
# ---------------------------------------------------------------------
localidades: dict = {
    "resistencia": {
        "nombre": "Resistencia",
        "cuenca": "Río Paraná",
        "nivel_metros": 3.15,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "precipitacion_acumulada_mm": 12.0,
        "fuente": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "barranqueras": {
        "nombre": "Barranqueras",
        "cuenca": "Río Paraná",
        "nivel_metros": 3.22,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "precipitacion_acumulada_mm": 12.0,
        "fuente": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "corrientes": {
        "nombre": "Corrientes (capital)",
        "cuenca": "Río Paraná",
        "nivel_metros": 3.30,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "precipitacion_acumulada_mm": 11.0,
        "fuente": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "formosa": {
        "nombre": "Formosa (capital)",
        "cuenca": "Río Paraguay",
        "nivel_metros": 4.05,
        "umbral_alerta": 5.50,
        "umbral_evacuacion": 6.00,
        "precipitacion_acumulada_mm": 8.0,
        "fuente": "INA - Sistema Nacional de Información Hídrica",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "puerto_bermejo": {
        "nombre": "Puerto Bermejo",
        "cuenca": "Río Bermejo",
        "nivel_metros": 2.75,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "el_sauzalito": {
        "nombre": "El Sauzalito",
        "cuenca": "Río Pilcomayo",
        "nivel_metros": 1.90,
        "umbral_alerta": 3.50,
        "umbral_evacuacion": 4.00,
        "precipitacion_acumulada_mm": 5.0,
        "fuente": "Reportes Prefectura / Comisión Binacional (sin API pública estable)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "isla_del_cerrito": {
        "nombre": "Isla del Cerrito",
        "cuenca": "Río Paraná",
        "nivel_metros": 3.35,
        "umbral_alerta": 5.50,
        "umbral_evacuacion": 6.00,
        "precipitacion_acumulada_mm": 12.0,
        "fuente": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "puerto_vilelas": {
        "nombre": "Puerto Vilelas",
        "cuenca": "Río Paraná",
        "nivel_metros": 3.20,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "precipitacion_acumulada_mm": 12.0,
        "fuente": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "la_leonesa": {
        "nombre": "La Leonesa",
        "cuenca": "Río Paraguay",
        "nivel_metros": 3.90,
        "umbral_alerta": 5.50,
        "umbral_evacuacion": 6.00,
        "precipitacion_acumulada_mm": 10.0,
        "fuente": "INA - Sistema Nacional de Información Hídrica / Prefectura Naval",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "pampa_del_indio": {
        "nombre": "Pampa del Indio",
        "cuenca": "Río Bermejo",
        "nivel_metros": 2.90,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "villa_rio_bermejito": {
        "nombre": "Villa Río Bermejito",
        "cuenca": "Río Bermejo",
        "nivel_metros": 2.70,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "fuerte_esperanza": {
        "nombre": "Fuerte Esperanza",
        "cuenca": "Río Pilcomayo",
        "nivel_metros": 1.85,
        "umbral_alerta": 3.50,
        "umbral_evacuacion": 4.00,
        "precipitacion_acumulada_mm": 6.0,
        "fuente": "Reportes Prefectura / Comisión Binacional (sin API pública estable)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
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
# MODELOS para los endpoints de actualización manual
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
    return {"servicio": "Portal Hídrico Chaco - API", "estado": "activo"}


@app.get("/localidades")
def listar_localidades():
    """Devuelve las 3 localidades con sus datos y explicación de cada campo."""
    return {"localidades": localidades, "explicaciones": EXPLICACIONES}


@app.get("/localidades/{clave}")
def obtener_localidad(clave: str):
    """Devuelve una localidad puntual (resistencia, barranqueras o formosa)."""
    datos = localidades.get(clave.lower())
    if datos is None:
        return {"error": f"Localidad '{clave}' no encontrada"}
    return {"localidad": datos, "explicaciones": EXPLICACIONES}


@app.get("/bot/consultar")
def consultar_para_bot():
    """
    Endpoint de compatibilidad con el dashboard de Streamlit actual,
    que espera 'clima', 'hidrologia' (Barranqueras) y 'satelital_ndvi'.
    """
    return {
        "clima": clima,
        "hidrologia": {
            "estacion": localidades["barranqueras"]["nombre"],
            "nivel_metros": localidades["barranqueras"]["nivel_metros"],
            "estado": (
                "EVACUACIÓN"
                if localidades["barranqueras"]["nivel_metros"] >= localidades["barranqueras"]["umbral_evacuacion"]
                else "ALERTA"
                if localidades["barranqueras"]["nivel_metros"] >= localidades["barranqueras"]["umbral_alerta"]
                else "NORMAL"
            ),
            "umbral_alerta": localidades["barranqueras"]["umbral_alerta"],
            "umbral_evacuacion": localidades["barranqueras"]["umbral_evacuacion"],
            "fuente": localidades["barranqueras"]["fuente"],
            "ultima_verificacion": localidades["barranqueras"]["ultima_verificacion"],
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
    return {"ok": True, "localidad": localidades[clave]}


@app.post("/satelital/actualizar")
def actualizar_satelital(datos: ActualizacionSatelital):
    satelital_ndvi["ndvi_promedio"] = datos.ndvi_promedio
    satelital_ndvi["condicion_vegetacion"] = datos.condicion_vegetacion
    satelital_ndvi["conectado"] = True
    satelital_ndvi["ultima_verificacion"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {"ok": True, "satelital_ndvi": satelital_ndvi}
