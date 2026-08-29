"""
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
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Portal Hidrico Chaco - API")

# ---------------------------------------------------------------------
# SUPABASE (persistencia real para SOS y reportes ciudadanos)
#
# Si SUPABASE_URL y SUPABASE_KEY estan configuradas (en Render: Settings
# -> Environment), se usa Supabase. Si no estan (ej. corriendo local sin
# configurar nada), cae de vuelta a las listas en memoria de siempre -
# asi nadie se queda sin poder levantar el proyecto en su maquina.
#
# IMPORTANTE: la SUPABASE_KEY tiene que ser la "service_role" (no la
# "anon"), porque este backend necesita poder escribir (insert/update).
# Nunca expongas esa key en el frontend - solo vive como variable de
# entorno del servidor (Render).
# ---------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Permite que el frontend (Vercel, o localhost mientras desarrollas)
# llame a esta API desde el navegador. Sin esto, el navegador bloquea
# las peticiones por la politica de CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En produccion, mejor restringir a tu dominio de Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

    "rio_negro": {
        "nombre": "Rio Negro / Riacho Barranqueras (interno)",
        "estacion": None,
        "nivel_metros": None,
        "umbral_alerta": None,
        "umbral_evacuacion": None,
        "fuente": "Sin estacion de medicion publica conocida en tiempo real. Historia documentada: colapsos de dique en 1977 y 1982 (Caputo et al. 1985, via CEPAL LC/ARTS 2018); evacuacion total planificada en 1998 (Rozé 1998, UNNE).",
        "conectado": False,
        "ultima_verificacion": None,
        "tipo": "pluvial_fluvial_interno",
        "internacional": False,
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
# ------------------------
localidades: dict = {
        "influencia_internacional": "Lluvias en el centro-este de Brasil (cuenca alta del Parana) y aporte del rio Paraguay.",
    },
    "la_leonesa": {
        "nombre": "La Leonesa", "cuenca_clave": "paraguay", "nivel_metros": 2.60,
        "umbral_alerta": 6.50, "umbral_evacuacion": 7.00, "precipitacion_acumulada_mm": 10.0,
        "fuente": "Prefectura Naval Argentina, estacion Las Palmas (aproximado, ~5km)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Cuenca del rio Paraguay: lluvias en Brasil, Paraguay y Bolivia.",
    },
    "pampa_del_indio": {
        "nombre": "Pampa del Indio", "cuenca_clave": "bermejo", "nivel_metros": 3.20,
        "umbral_alerta": 5.00, "umbral_evacuacion": 5.70, "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Cuenca del rio Bermejo: nace en Bolivia y el noroeste argentino (Salta/Jujuy).",
    },
    "villa_rio_bermejito": {
        "nombre": "Villa Rio Bermejito", "cuenca_clave": "bermejo", "nivel_metros": 2.45,
        "umbral_alerta": 3.80, "umbral_evacuacion": 4.30, "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Cuenca del rio Bermejo: nace en Bolivia y Salta. Afectada en el temporal historico de abril 2026, cuando Defensa Civil confirmo que el rio traia caudales desde Salta por lluvias previas en esa provincia.",
    },
    "fuerte_esperanza": {
        "nombre": "Fuerte Esperanza", "cuenca_clave": "pilcomayo", "nivel_metros": 3.05,
        "umbral_alerta": 5.20, "umbral_evacuacion": 6.00, "precipitacion_acumulada_mm": 6.0,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Cuenca del rio Pilcomayo, compartida con Bolivia y Paraguay.",
    },
    # -----------------------------------------------------------------
    # LOCALIDADES DEL INTERIOR — riesgo PLUVIAL, sumadas 29/08/2026.
    # A diferencia de las anteriores, estas NO estan sobre el Parana ni
    # el Paraguay - no tienen estacion de rio, asi que nivel_metros y
    # los umbrales quedan en None (nada que inventar). El riesgo real
    # es lluvia local que supera la capacidad de desague, confirmado
    # por fuente academica (Gomez et al., FACENA-UNNE, "Areas de riesgo
    # de inundacion pluvial en la provincia del Chaco") y por eventos
    # reales documentados en prensa durante 2026.
    # -----------------------------------------------------------------
    "san_martin_chaco": {
        "nombre": "General José de San Martín", "cuenca_clave": None, "nivel_metros": None,
        "umbral_alerta": None, "umbral_evacuacion": None, "precipitacion_acumulada_mm": 38.0,
        "fuente": "Identificada como zona de riesgo pluvial en Gomez et al. (FACENA-UNNE, 2014). Ultimo evento real: temporal del 15/04/2026 con 64mm y caida de arboles/postes (Diario La Voz del Chaco).",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "pluvial",
        "influencia_internacional": None,
    },
    "santa_sylvina": {
        "nombre": "Santa Sylvina", "cuenca_clave": None, "nivel_metros": None,
        "umbral_alerta": None, "umbral_evacuacion": None, "precipitacion_acumulada_mm": 22.0,
        "fuente": "Evento real documentado: temporal del 07/06/2026, más de 80mm en pocas horas, inundacion de barrios y zona centrica con agua dentro de viviendas, tornado registrado (CharataChaco.Net).",
        "conectado": False, "ultima_verificacion": "2026-06-07",
        "tipo_inundacion_dominante": "pluvial",
        "influencia_internacional": None,
    },
    "charata": {
        "nombre": "Charata", "cuenca_clave": None, "nivel_metros": None,
        "umbral_alerta": None, "umbral_evacuacion": None, "precipitacion_acumulada_mm": 105.0,
        "fuente": "Identificada como zona de riesgo pluvial en Gomez et al. (FACENA-UNNE, 2014). Ultimo evento real: temporal del 15/04/2026 con 105mm y caida de un arbol (Diario La Voz del Chaco).",
        "conectado": False, "ultima_verificacion": "2026-04-15",
        "tipo_inundacion_dominante": "pluvial",
        "influencia_internacional": None,
    },
 "castelli": {
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
@app.get("/nota-tecnica-enso")
def obtener_nota_tecnica_enso():
    """
    Ultima Nota Tecnica Conjunta UNNE/UFSM/APA Chaco sobre El Nino,
    detectada automaticamente via actualizar_nota_tecnica.py (Zenodo API).
    Reemplaza/complementa el indice ONI generico con una fuente oficial
    citable y especifica para la region.
    """
    try:
        with open("nota_tecnica_enso.json", "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"encontrada": False, "aviso": "Todavia no corrio actualizar_nota_tecnica.py"}


@app.get("/vertederos")
def obtener_estado_vertederos():
    """
    Estado de los vertederos de Itaipu/Yacyreta (alerta temprana para
    el Parana), generado por actualizar_vertederos.py via GitHub Actions.
    Si el archivo todavia no existe (primera corrida no hecha aun),
    devuelve un estado vacio en vez de romper.
    """
    try:
        with open("vertederos_estado.json", "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "vertederos": {},
            "alerta_temprana": {"hay_alerta": False, "avisos": []},
            "actualizado": None,
            "aviso": "Todavia no corrio actualizar_vertederos.py",
        }

@app.get("/historico/{estacion}")
    },
    "ina": {
        "nombre": "Instituto Nacional del Agua (INA)",
        "nivel": "nacional",
        "dependencia": "Secretaria de Infraestructura y Politica Hidrica, Ministerio de Obras Publicas",
        "rol": "Pronosticos hidrologicos de los rios Parana, Paraguay, Iguazu y Uruguay via su Sistema de Informacion y Alerta Hidrologico (SIyAH). Reporta Barranqueras.",
        "url": "https://www.ina.gob.ar/siyah/index.php",
        "url_alertas": "https://alerta.ina.gob.ar/a5/diario/reporte_diario",
    },
    "apa": {
        "nombre": "Administración Provincial del Agua (APA)",
        "nivel": "provincial (Chaco)",
        "dependencia": "Gobierno de la Provincia del Chaco",
        "rol": "Unica autoridad del agua de la provincia. Mantiene 2.600 km de canales rurales y terraplenes de defensa contra inundaciones, y opera el Sistema de Defensas contra Inundaciones del Gran Resistencia. Tambien opera infraestructura de mitigacion PLUVIAL, como la Estacion de Bombeo Laguna Avalos (beneficia a mas de 200.000 habitantes de Gran Resistencia).",
        "url": "http://apachaco.gob.ar/web/index.php",
    },
    "proteccion_civil_chaco": {
        "nombre": "Subsecretaría de Protección Civil (ex Dirección Provincial de Defensa Civil)",
        "nivel": "provincial (Chaco)",
        "dependencia": "Ministerio de Gobierno y Trabajo",
        "rol": "Coordinacion operativa de emergencias. En emergencias grandes arma un Comite de Contingencia junto a APA, Vialidad Provincial, SECHEEP, SAMEEP y demas areas, bajo monitoreo del gobernador. Provista de canobotes para zonas rurales aisladas (2026).",
        "url": None,
        "nota": "El nombre cambio en algun momento reciente - notas de 2026 usan 'Subsecretaria de Proteccion Civil'; una nota mas vieja la nombra 'Direccion Provincial de Defensa Civil'. Verificar el nombre vigente antes de citarlo formalmente.",
    },
    "afe": {
        "nombre": "Agencia Federal de Emergencias (AFE)",
        "nivel": "nacional",
        "dependencia": "No confirmado con precision en las fuentes consultadas",
        "rol": "Coordina el Plan Federal de Coordinacion ENOS 2026-2027 (aprobado por el Ministerio de Seguridad Nacional) entre Nacion, provincias y municipios, frente a inundaciones y crecidas asociadas a El Nino. Chaco se sumo a este plan (jul. 2026).",
        "url": None,
        "nota": "No confirmamos si reemplaza o coexiste con SINAGIR (que aparece en otras fuentes) - falta verificar la relacion entre ambos organismos.",
    },
}


@app.get("/organismos")
def listar_organismos():
    return {"organismos": ORGANISMOS}


# ---------------------------------------------------------------------
# CONTEXTO DE RELIEVE — investigado 29/08/2026.
# ---------------------------------------------------------------------
CONTEXTO_RELIEVE = {
    "resumen": (
        "Provincia llana, parte de la gran llanura chaco-pampeana. Pendiente "
        "suave de noroeste a sudeste: desde ~145 m s.n.m. en Taco Pozo (limite "
        "oeste) hasta casi el nivel del rio en Barranqueras (este). Suelos "
        "mayormente arcillosos, que junto con la escasa pendiente dificultan "
        "el escurrimiento y forman numerosos banados, esteros y lagunas "
        "semipermanentes. El sur de la provincia (Bajos Submeridionales) es la "
        "zona de mayor riesgo de inundacion por su pendiente casi nula. El "
        "noroeste (El Impenetrable) es llano con un leve abovedamiento sin "
        "escurrimiento superficial hacia los rios."
    ),
    "fuente": "todo-argentina.net, viajarg.com, Wikipedia (Geografia de la Provincia del Chaco) - consultados 29/08/2026",
}

@app.get("/relieve")
    return {"ok": True, "ticket": ticket}


@app.get("/sos")
def listar_solicitudes_sos():
    if supabase:
        resultado = (
            supabase.table("sos_tickets")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return {"tickets": resultado.data}
    return {"tickets": tickets_sos}


@app.patch("/sos/{ticket_id}")
def actualizar_solicitud_sos(ticket_id: str, datos: ActualizacionSOS):
    cambios = {"estado": datos.estado}
    if datos.unidad_asignada is not None:
        cambios["unidad_asignada"] = datos.unidad_asignada
    if datos.notas_despacho is not None:
        cambios["notas_despacho"] = datos.notas_despacho

    if supabase:
        resultado = (
            supabase.table("sos_tickets").update(cambios).eq("id", ticket_id).execute()
        )
        if not resultado.data:
            return {"error": f"Ticket '{ticket_id}' no encontrado"}
        return {"ok": True, "ticket": resultado.data[0]}

    ticket = next((t for t in tickets_sos if t["id"] == ticket_id), None)
    if ticket is None:
        return {"error": f"Ticket '{ticket_id}' no encontrado"}
    ticket.update(cambios)
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
    if supabase:
        supabase.table("reportes_ciudadanos").insert(reporte).execute()
    else:
        reportes_ciudadanos.insert(0, reporte)
    return {"ok": True, "reporte": reporte}


@app.get("/reportes")
def listar_reportes_ciudadanos():
    if supabase:
        resultado = (
            supabase.table("reportes_ciudadanos")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return {"reportes": resultado.data}
    return {"reportes": reportes_ciudadanos}


from whatsapp_webhook import router as whatsapp_router
app.include_router(whatsapp_router)

