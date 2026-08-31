"""
Backend del Portal Hidrico Chaco.

Fuente unica de datos para el dashboard de Streamlit y el bot de
Telegram, asi no quedan datos duplicados y desincronizados entre
proyectos.

DATOS ESTATICOS vs ESTADO REAL:
- ESTATICO (vive en este archivo, en el dict `localidades`): nombre,
  cuenca_clave, umbral_alerta, umbral_evacuacion, fuente. Casi no
  cambia, no necesita base de datos.
- ESTADO REAL (vive en Firestore, ver firestore_db.py): nivel_metros,
  velocidad_m_h, anomalia_velocidad, conectado, ultima_verificacion.
  Esto es lo que actualiza actualizar_niveles.py, y ahora SOBREVIVE
  a un redeploy o a que Render se duerma por inactividad. Antes vivia
  en un diccionario en RAM y se perdia en cada reinicio del proceso.

UMBRALES: verificados contra la tabla oficial de Prefectura Naval
Argentina (fich.unl.edu.ar/cim/rios/parana/alturas) el 09/08/2026.

ALERTA POR VELOCIDAD DE SUBIDA:
Ademas del umbral fijo de altura, el sistema calcula cuantos metros
por hora sube el rio entre dos lecturas consecutivas. Una suba muy
rapida es peligrosa aunque el nivel absoluto todavia no llegue al
umbral de alerta (crecidas repentinas por apertura de compuertas
aguas arriba, tormentas muy localizadas, etc.).
"""
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

import firestore_db

app = FastAPI(title="Portal Hidrico Chaco - API")

UMBRAL_VELOCIDAD_M_H = 0.5

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
# (sin cambios respecto a la version anterior)
# ---------------------------------------------------------------------
CUENCAS: dict = {
    "parana": {
        "nombre": "Rio Parana", "estacion": "Barranqueras",
        "nivel_metros": 3.22, "umbral_alerta": 6.00, "umbral_evacuacion": 6.50,
        "fuente": "Prefectura Naval Argentina (via CIM-UNL)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "paraguay": {
        "nombre": "Rio Paraguay", "estacion": "Puerto Bermejo / confluencia",
        "nivel_metros": 4.10, "umbral_alerta": 6.50, "umbral_evacuacion": 7.00,
        "fuente": "Prefectura Naval Argentina (via CIM-UNL)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "bermejo": {
        "nombre": "Rio Bermejo", "estacion": "Presidencia de la Plaza (aprox.)",
        "nivel_metros": 2.80, "umbral_alerta": 4.50, "umbral_evacuacion": 5.00,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
    "pilcomayo": {
        "nombre": "Rio Pilcomayo", "estacion": "Zona norte de Chaco / limite con Formosa",
        "nivel_metros": 1.95, "umbral_alerta": 3.50, "umbral_evacuacion": 4.00,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
    },
}

# ---------------------------------------------------------------------
# LOCALIDADES — SOLO metadatos estaticos + valores de arranque.
# Los valores de arranque (nivel_metros, conectado, ultima_verificacion
# de aca abajo) se usan UNICAMENTE la primerisima vez que se consulta
# una localidad, antes de que exista algun estado guardado en Firestore.
# En cuanto actualizar_niveles.py mande la primera lectura real, estos
# numeros dejan de tener efecto: Firestore manda.
# ---------------------------------------------------------------------
localidades: dict = {
    "resistencia": {
        "nombre": "Resistencia", "cuenca_clave": "parana",
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (mismo tramo, ~8km)",
        "nivel_metros": 3.15, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 12.0,
    },
    "barranqueras": {
        "nombre": "Barranqueras", "cuenca_clave": "parana",
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (medicion directa)",
        "nivel_metros": 3.22, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 12.0,
    },
    "corrientes": {
        "nombre": "Corrientes (capital)", "cuenca_clave": "parana",
        "umbral_alerta": 6.50, "umbral_evacuacion": 7.00,
        "fuente": "Prefectura Naval Argentina, estacion Corrientes (medicion directa)",
        "nivel_metros": 3.30, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 11.0,
    },
    "formosa": {
        "nombre": "Formosa (capital)", "cuenca_clave": "paraguay",
        "umbral_alerta": 7.80, "umbral_evacuacion": 8.30,
        "fuente": "Prefectura Naval Argentina, estacion Formosa (medicion directa)",
        "nivel_metros": 4.05, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 8.0,
    },
    "puerto_bermejo": {
        "nombre": "Puerto Bermejo", "cuenca_clave": "paraguay",
        "umbral_alerta": 6.50, "umbral_evacuacion": 7.00,
        "fuente": "Prefectura Naval Argentina, estacion Bermejo (aproximado, zona de confluencia)",
        "nivel_metros": 2.75, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 15.0,
    },
    "el_sauzalito": {
        "nombre": "El Sauzalito", "cuenca_clave": "pilcomayo",
        "umbral_alerta": 3.50, "umbral_evacuacion": 4.00,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "nivel_metros": 1.90, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 5.0,
    },
    "isla_del_cerrito": {
        "nombre": "Isla del Cerrito", "cuenca_clave": "paraguay",
        "umbral_alerta": 6.20, "umbral_evacuacion": 6.80,
        "fuente": "Prefectura Naval Argentina, estacion Isla del Cerrito (medicion directa)",
        "nivel_metros": 3.35, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 12.0,
    },
    "puerto_vilelas": {
        "nombre": "Puerto Vilelas", "cuenca_clave": "parana",
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (mismo tramo, ~5km)",
        "nivel_metros": 3.20, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 12.0,
    },
    "la_leonesa": {
        "nombre": "La Leonesa", "cuenca_clave": "paraguay",
        "umbral_alerta": 6.50, "umbral_evacuacion": 7.00,
        "fuente": "Prefectura Naval Argentina, estacion Las Palmas (aproximado, ~5km)",
        "nivel_metros": 3.90, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 10.0,
    },
    "pampa_del_indio": {
        "nombre": "Pampa del Indio", "cuenca_clave": "bermejo",
        "umbral_alerta": 4.50, "umbral_evacuacion": 5.00,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "nivel_metros": 2.90, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 15.0,
    },
    "villa_rio_bermejito": {
        "nombre": "Villa Rio Bermejito", "cuenca_clave": "bermejo",
        "umbral_alerta": 4.50, "umbral_evacuacion": 5.00,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "nivel_metros": 2.70, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 15.0,
    },
    "fuerte_esperanza": {
        "nombre": "Fuerte Esperanza", "cuenca_clave": "pilcomayo",
        "umbral_alerta": 3.50, "umbral_evacuacion": 4.00,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "nivel_metros": 1.85, "conectado": False, "ultima_verificacion": "2026-08-04",
        "precipitacion_acumulada_mm": 6.0,
    },
}

# ---------------------------------------------------------------------
# BARRIOS VULNERABLES (sin cambios respecto a la version anterior)
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
    "ndvi_promedio": 0.48, "condicion_vegetacion": "ESTABLE",
    "conectado": False, "ultima_verificacion": "2026-08-04",
}

clima = {
    "fase_oni": "Neutro", "ultimo_valor_oni": 0.45,
    "conectado": False, "ultima_verificacion": "2026-08-04",
}

# ---------------------------------------------------------------------
# CLASIFICACION DE ESTADO
# ---------------------------------------------------------------------
def calcular_estado(nivel: float, umbral_alerta: float, umbral_evacuacion: float,
                     anomalia_velocidad: bool = False):
    if nivel >= umbral_evacuacion:
        return "EVACUACION", "🔴"
    if anomalia_velocidad:
        return "ALERTA_VELOCIDAD", "🟠"
    if nivel >= umbral_alerta:
        return "ALERTA", "🟡"
    return "NORMAL", "🟢"


def _cuenca_con_estado(clave: str) -> dict:
    c = CUENCAS[clave]
    estado, emoji = calcular_estado(c["nivel_metros"], c["umbral_alerta"], c["umbral_evacuacion"])
    return {**c, "clave": clave, "estado": estado, "emoji": emoji}


def _localidad_con_estado(clave: str) -> dict:
    """Combina los metadatos estaticos con el ultimo estado REAL guardado
    en Firestore. Si Firestore todavia no tiene nada para esta localidad
    (recien migrado, o nunca llego una lectura), usa el valor de arranque
    del dict `localidades` como respaldo."""
    base = localidades[clave]
    estado_guardado = firestore_db.leer_estado(clave) or {}
    loc = {**base, **estado_guardado}
    estado, emoji = calcular_estado(
        loc["nivel_metros"], loc["umbral_alerta"], loc["umbral_evacuacion"],
        anomalia_velocidad=loc.get("anomalia_velocidad", False),
    )
    return {**loc, "clave": clave, "estado": estado, "emoji": emoji}


# ---------------------------------------------------------------------
# MODELOS
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
@app.get("/")
def raiz():
    return {"servicio": "Portal Hidrico Chaco - API", "estado": "activo"}


@app.get("/localidades")
def listar_localidades():
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
    return {
        "cuencas": {clave: _cuenca_con_estado(clave) for clave in CUENCAS},
        "explicaciones": EXPLICACIONES,
    }


@app.get("/cuencas/{clave}")
def obtener_cuenca(clave: str):
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
    """
    Guarda el nuevo nivel EN FIRESTORE (no en RAM), calculando antes la
    velocidad de subida contra el ultimo estado real guardado. Esto
    sobrevive a un redeploy o a que Render se duerma por inactividad.
    """
    clave = datos.localidad.lower()
    if clave not in localidades:
        return {"error": f"Localidad '{datos.localidad}' no reconocida"}

    ahora = datetime.now(timezone.utc)
    estado_anterior = firestore_db.leer_estado(clave) or {}

    nivel_anterior = estado_anterior.get("nivel_metros", localidades[clave]["nivel_metros"])
    hora_anterior_iso = estado_anterior.get("hora_lectura_anterior")

    velocidad_m_h = None
    anomalia_velocidad = False
    if hora_anterior_iso:
        hora_anterior = datetime.fromisoformat(hora_anterior_iso)
        horas_transcurridas = (ahora - hora_anterior).total_seconds() / 3600
        if horas_transcurridas >= (1 / 60):
            velocidad_m_h = round((datos.nivel_metros - nivel_anterior) / horas_transcurridas, 3)
            anomalia_velocidad = velocidad_m_h >= UMBRAL_VELOCIDAD_M_H

    nuevo_estado = {
        "nivel_metros": datos.nivel_metros,
        "velocidad_m_h": velocidad_m_h,
        "anomalia_velocidad": anomalia_velocidad,
        "hora_lectura_anterior": ahora.isoformat(),
        "conectado": True,
        "ultima_verificacion": ahora.strftime("%Y-%m-%d %H:%M UTC"),
    }
    if datos.precipitacion_acumulada_mm is not None:
        nuevo_estado["precipitacion_acumulada_mm"] = datos.precipitacion_acumulada_mm

    firestore_db.guardar_estado(clave, nuevo_estado)

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


from whatsapp_webhook import router as whatsapp_router
app.include_router(whatsapp_router)
