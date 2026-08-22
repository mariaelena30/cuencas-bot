"""
Backend del Portal Hidrico Chaco.

Fuente unica de datos para el dashboard de Streamlit y el bot de
Telegram, asi no quedan datos duplicados y desincronizados entre
proyectos.

IMPORTANTE SOBRE LOS DATOS:
Los valores de abajo son datos SEMILLA (de referencia/demostracion)
para las localidades sin fuente publica en vivo. Las localidades con
estacion hidrometrica de Prefectura Naval (via CIM-UNL) se actualizan
automaticamente con el script actualizar_niveles.py. Cada localidad
indica 'conectado: True/False' segun corresponda.

UMBRALES: verificados contra la tabla oficial de Prefectura Naval
Argentina (fich.unl.edu.ar/cim/rios/parana/alturas) el 09/08/2026.
"""

import json
from datetime import datetime, timedelta, timezone

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
        "fuente": "Prefectura Naval Argentina (via CIM-UNL)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "paraguay": {
        "nombre": "Rio Paraguay",
        "estacion": "Puerto Bermejo / confluencia",
        "nivel_metros": 4.10,
        "umbral_alerta": 6.50,
        "umbral_evacuacion": 7.00,
        "fuente": "Prefectura Naval Argentina (via CIM-UNL)",
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
#
# Umbrales corregidos (verificados 09/08/2026 contra fich.unl.edu.ar):
#   barranqueras       6.00 / 6.50  (ya coincidia)
#   corrientes         6.00 / 6.50  ->  6.50 / 7.00
#   formosa            5.50 / 6.00  ->  7.80 / 8.30
#   isla_del_cerrito    5.50 / 6.00  ->  6.20 / 6.80
#   puerto_bermejo     4.50 / 5.00  ->  6.50 / 7.00  (estacion "Bermejo")
#   la_leonesa         5.50 / 6.00  ->  6.50 / 7.00  (estacion "Las Palmas")
#   resistencia, puerto_vilelas: usan umbral de Barranqueras (mismo tramo)
#   el_sauzalito, pampa_del_indio, villa_rio_bermejito, fuerte_esperanza:
#     sin fuente publica de umbrales verificada, se mantienen como estaban
# ---------------------------------------------------------------------
localidades: dict = {
    "resistencia": {
        "nombre": "Resistencia", "cuenca_clave": "parana", "nivel_metros": 3.15,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (mismo tramo, ~8km)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "barranqueras": {
        "nombre": "Barranqueras", "cuenca_clave": "parana", "nivel_metros": 3.22,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (medicion directa)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "corrientes": {
        "nombre": "Corrientes (capital)", "cuenca_clave": "parana", "nivel_metros": 3.30,
        "umbral_alerta": 6.50, "umbral_evacuacion": 7.00, "precipitacion_acumulada_mm": 11.0,
        "fuente": "Prefectura Naval Argentina, estacion Corrientes (medicion directa)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "formosa": {
        "nombre": "Formosa (capital)", "cuenca_clave": "paraguay", "nivel_metros": 4.05,
        "umbral_alerta": 7.80, "umbral_evacuacion": 8.30, "precipitacion_acumulada_mm": 8.0,
        "fuente": "Prefectura Naval Argentina, estacion Formosa (medicion directa)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "puerto_bermejo": {
        "nombre": "Puerto Bermejo", "cuenca_clave": "paraguay", "nivel_metros": 2.75,
        "umbral_alerta": 6.50, "umbral_evacuacion": 7.00, "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina, estacion Bermejo (aproximado, zona de confluencia)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "el_sauzalito": {
        "nombre": "El Sauzalito", "cuenca_clave": "pilcomayo", "nivel_metros": 1.90,
        "umbral_alerta": 3.50, "umbral_evacuacion": 4.00, "precipitacion_acumulada_mm": 5.0,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "isla_del_cerrito": {
        "nombre": "Isla del Cerrito", "cuenca_clave": "paraguay", "nivel_metros": 3.35,
        "umbral_alerta": 6.20, "umbral_evacuacion": 6.80, "precipitacion_acumulada_mm": 12.0,
        "fuente": "Prefectura Naval Argentina, estacion Isla del Cerrito (medicion directa)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "puerto_vilelas": {
        "nombre": "Puerto Vilelas", "cuenca_clave": "parana", "nivel_metros": 3.20,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (mismo tramo, ~5km)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "la_leonesa": {
        "nombre": "La Leonesa", "cuenca_clave": "paraguay", "nivel_metros": 3.90,
        "umbral_alerta": 6.50, "umbral_evacuacion": 7.00, "precipitacion_acumulada_mm": 10.0,
        "fuente": "Prefectura Naval Argentina, estacion Las Palmas (aproximado, ~5km)",
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

# ---------------------------------------------------------------------
# BARRIOS VULNERABLES — puntos especificos DENTRO de una localidad que
# son historicamente mas golpeados por las crecidas que el resto de la
# ciudad. No tienen nivel de rio propio: heredan el estado (Normal/
# Alerta/Evacuacion) de su localidad_padre. Son para dar mas precision
# visual en el mapa, marcados con datos de investigacion historica,
# no con medicion en vivo propia.
#
# IMPORTANTE SOBRE PRECISION: villa_rio_negro, san_pedro_pescador,
# antequeras y la_floresta tienen coordenadas confirmadas via fuentes
# publicas (OpenStreetMap/Mapcarta/derutasydestinos). santa_lucia y
# mujeres_argentinas usan coordenadas APROXIMADAS (no se encontro un
# registro con coordenadas exactas), aclarado en su campo "precision".
# ---------------------------------------------------------------------
BARRIOS_VULNERABLES: dict = {
    "villa_rio_negro": {
        "nombre": "Villa Río Negro", "localidad_padre": "resistencia",
        "lat": -27.4253, "lon": -58.9764, "precision": "confirmada",
        "motivo": "Inundado en la crecida de 1982 tras el colapso del dique del Río Negro",
    },
    "mujeres_argentinas": {
        "nombre": "Mujeres Argentinas", "localidad_padre": "resistencia",
        "lat": -27.4253, "lon": -58.9764, "precision": "aproximada (cerca de Villa Río Negro)",
        "motivo": "Ex Golf Club; inundado en la crecida de 1982",
    },
    "santa_lucia": {
        "nombre": "Santa Lucía", "localidad_padre": "resistencia",
        "lat": -27.4200, "lon": -58.9800, "precision": "aproximada",
        "motivo": "Identificado como uno de los barrios históricamente más afectados de Resistencia",
    },
    "san_pedro_pescador": {
        "nombre": "San Pedro Pescador (Barrio de los Pescadores)", "localidad_padre": "barranqueras",
        "lat": -27.46085, "lon": -58.86805, "precision": "confirmada",
        "motivo": "Único asentamiento del Chaco sobre el cauce principal del Paraná; 43 familias autoevacuadas en 2014",
    },
    "antequeras": {
        "nombre": "Puerto Antequeras", "localidad_padre": "barranqueras",
        "lat": -27.4425, "lon": -58.8503, "precision": "confirmada",
        "motivo": "Zona pesquera ribereña, afectada en múltiples crecidas históricas",
    },
    "la_floresta": {
        "nombre": "La Floresta", "localidad_padre": "formosa",
        "lat": -26.1547, "lon": -58.1794, "precision": "confirmada",
        "motivo": "Junto al Riacho Formosa, que recibe agua de las crecidas del Pilcomayo y Bermejo",
    },
    "tres_bocas": {
        "nombre": "Paraje Las Tres Bocas", "localidad_padre": "puerto_vilelas",
        "lat": -27.5300, "lon": -58.8600, "precision": "aproximada",
        "motivo": "Zona ribereña que queda aislada por tierra en crecidas grandes; en 2023, con Barranqueras en 6.54 m (evacuación), ~150 familias solo accedían en lancha desde Empedrado (Corrientes). Los parajes vecinos Soto y Cinco Bocas sufren el mismo aislamiento.",
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


class ActualizacionClima(BaseModel):
    fase_oni: str
    ultimo_valor_oni: float


# ---------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------
@app.get("/historico/{estacion}")
def obtener_historico(estacion: str, dias: int = 60):
    """
    Serie historica de niveles para una estacion de niveles_rios.json
    (ej. "Barranqueras", "Corrientes", "Formosa"). Alimenta el grafico
    de tendencia del dashboard. Comparacion case-insensitive.

    Nota: los nombres de estacion en niveles_rios.json vienen del
    pipeline CIM-UNL y no son 1 a 1 con las 12 localidades monitoreadas
    - varias localidades comparten estacion (ej. resistencia y
    puerto_vilelas usan la estacion Barranqueras) y algunas localidades
    todavia no tienen estacion con historico disponible.
    """
    try:
        with open("niveles_rios.json", "r", encoding="utf-8") as fh:
            historico = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"estacion": estacion, "lecturas": [], "error": "Historico no disponible todavia."}

    limite = datetime.now(timezone.utc) - timedelta(days=dias)

    def _fecha(fila):
        try:
            f = datetime.fromisoformat(fila["timestamp_consulta"].replace("Z", "+00:00"))
            return f if f.tzinfo else f.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            return None

    lecturas = []
    for fila in historico:
        if fila.get("puerto", "").strip().lower() != estacion.strip().lower():
            continue
        fecha = _fecha(fila)
        if fecha is None or fecha < limite:
            continue
        lecturas.append({
            "fecha": fila["timestamp_consulta"],
            "altura_m": fila.get("altura_actual_m"),
        })

    lecturas.sort(key=lambda l: l["fecha"])
    return {"estacion": estacion, "lecturas": lecturas, "n_lecturas": len(lecturas)}


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


@app.get("/barrios")
def listar_barrios():
    """Todos los barrios vulnerables, con el estado de su localidad padre."""
    resultado = {}
    for clave, b in BARRIOS_VULNERABLES.items():
        padre = _localidad_con_estado(b["localidad_padre"])
        resultado[clave] = {
            **b, "clave": clave,
            "estado": padre["estado"], "emoji": padre["emoji"],
            "nombre_localidad_padre": padre["nombre"],
        }
    return {"barrios": resultado}


@app.get("/barrios/{localidad_clave}")
def barrios_de_localidad(localidad_clave: str):
    """Barrios vulnerables que pertenecen a una localidad puntual (para el bot)."""
    localidad_clave = localidad_clave.lower()
    if localidad_clave not in localidades:
        return {"error": f"Localidad '{localidad_clave}' no encontrada"}
    padre = _localidad_con_estado(localidad_clave)
    resultado = {
        clave: {**b, "clave": clave, "estado": padre["estado"], "emoji": padre["emoji"]}
        for clave, b in BARRIOS_VULNERABLES.items()
        if b["localidad_padre"] == localidad_clave
    }
    return {"barrios": resultado}


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


@app.post("/clima/actualizar")
def actualizar_clima(datos: ActualizacionClima):
    clima["fase_oni"] = datos.fase_oni
    clima["ultimo_valor_oni"] = datos.ultimo_valor_oni
    clima["conectado"] = True
    clima["ultima_verificacion"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {"ok": True, "clima": clima}


# ---------------------------------------------------------------------
# SOS Y REPORTES CIUDADANOS (Prioridad 1 del roadmap)
#
# NOTA IMPORTANTE: igual que el resto de los datos de este backend,
# esto vive EN MEMORIA (listas de Python) - se pierde si Render
# reinicia el servicio. Es el mismo pendiente de siempre (migrar a
# Supabase), no algo nuevo que se agrega con esta funcionalidad.
# ---------------------------------------------------------------------
tickets_sos: list = []
reportes_ciudadanos: list = []


class SolicitudSOS(BaseModel):
    nombre: str
    telefono: str
    localidad: str
    direccion: str | None = None
    lat: float
    lon: float
    personas_afectadas: int = 1
    altura_agua_cm: int | None = None
    nivel_urgencia: str = "ALTO"  # ALTO / MEDIO / BAJO
    requiere: list[str] = []
    notas: str | None = None


class ActualizacionSOS(BaseModel):
    estado: str  # PENDIENTE / DESPACHADO / RESUELTO
    unidad_asignada: str | None = None
    notas_despacho: str | None = None


class ReporteCiudadano(BaseModel):
    nombre: str
    localidad: str
    calle: str
    lat: float
    lon: float
    nivel_agua_aprox: str = "CORDON"  # CORDON / TOBILLO / RODILLA / CINTURA / ENTRO_A_CASA
    descripcion: str | None = None


@app.post("/sos")
def crear_solicitud_sos(datos: SolicitudSOS):
    if datos.localidad.lower() not in localidades:
        return {"error": f"Localidad '{datos.localidad}' no reconocida"}
    ticket = {
        "id": f"sos_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        **datos.model_dump(),
        "estado": "PENDIENTE",
        "unidad_asignada": None,
        "notas_despacho": None,
    }
    tickets_sos.insert(0, ticket)
    return {"ok": True, "ticket": ticket}


@app.get("/sos")
def listar_solicitudes_sos():
    return {"tickets": tickets_sos}


@app.patch("/sos/{ticket_id}")
def actualizar_solicitud_sos(ticket_id: str, datos: ActualizacionSOS):
    ticket = next((t for t in tickets_sos if t["id"] == ticket_id), None)
    if ticket is None:
        return {"error": f"Ticket '{ticket_id}' no encontrado"}
    ticket["estado"] = datos.estado
    if datos.unidad_asignada is not None:
        ticket["unidad_asignada"] = datos.unidad_asignada
    if datos.notas_despacho is not None:
        ticket["notas_despacho"] = datos.notas_despacho
    return {"ok": True, "ticket": ticket}


@app.post("/reportes")
def crear_reporte_ciudadano(datos: ReporteCiudadano):
    if datos.localidad.lower() not in localidades:
        return {"error": f"Localidad '{datos.localidad}' no reconocida"}
    reporte = {
        "id": f"rep_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        **datos.model_dump(),
    }
    reportes_ciudadanos.insert(0, reporte)
    return {"ok": True, "reporte": reporte}


@app.get("/reportes")
def listar_reportes_ciudadanos():
    return {"reportes": reportes_ciudadanos}


from whatsapp_webhook import router as whatsapp_router
app.include_router(whatsapp_router)
