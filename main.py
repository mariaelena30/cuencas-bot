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
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Firestore: persiste el estado EN VIVO de cada localidad (nivel_metros,
# velocidad_m_h, anomalia_velocidad, conectado, ultima_verificacion)
# afuera del proceso, asi sobrevive a que Render reinicie el backend en
# cada deploy o cuando el servicio se duerme por inactividad. Los datos
# ESTATICOS (nombre, umbral_alerta, umbral_evacuacion, cuenca, fuente)
# siguen viviendo en este archivo como siempre - casi no cambian y no
# hace falta leer la base de datos para eso.
#
# CONFIGURACION: variable de entorno FIREBASE_CREDENTIALS_JSON en
# Render, con el contenido completo del JSON de la cuenta de servicio
# de Firebase (Firebase Console -> Configuracion del proyecto ->
# Cuentas de servicio -> Generar nueva clave privada). Ya esta
# configurada y funcionando (confirmado 02/09/2026 con datos reales
# en la consola de Firestore).
import firestore_db

UMBRAL_VELOCIDAD_M_H = 0.05  # 5 cm/hora sostenido = ascenso peligrosamente rapido

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
    "tipo_inundacion_dominante": (
        "FLUVIAL: se desborda un rio grande (Parana, Paraguay, Bermejo, "
        "Pilcomayo) - dias de aviso, se sigue con el nivel del rio. "
        "PLUVIAL: lluvia local que el desague no puede evacuar, sin que "
        "ningun rio grande haya subido - es repentino y localizado, y NO "
        "tiene estacion de rio que lo mida (por eso nivel_metros/umbrales "
        "quedan en None en las localidades pluviales - el indicador real "
        "es precipitacion_acumulada_mm). En Chaco, ademas, esta el Rio "
        "Negro / riacho Barranqueras, un curso interno independiente del "
        "Parana que historicamente causo las peores inundaciones de "
        "Resistencia (1977, 1982, 1998) - ver /cuencas/rio_negro."
    ),
}

# ---------------------------------------------------------------------
# CUENCAS — datos representativos de cada una de las 4 cuencas
# ---------------------------------------------------------------------
CUENCAS: dict = {
    "parana": {
        "nombre": "Rio Parana",
        "estacion": "Barranqueras",
        "nivel_metros": 2.65,
        "umbral_alerta": 6.00,
        "umbral_evacuacion": 6.50,
        "fuente": "Prefectura Naval Argentina (via CIM-UNL)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "paraguay": {
        "nombre": "Rio Paraguay",
        "estacion": "Puerto Bermejo / confluencia",
        "nivel_metros": 2.40,
        "umbral_alerta": 6.50,
        "umbral_evacuacion": 7.00,
        "fuente": "Prefectura Naval Argentina (via CIM-UNL)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    "bermejo": {
        "nombre": "Rio Bermejo",
        "estacion": "Presidencia de la Plaza (aprox.)",
        "nivel_metros": 3.31,
        "umbral_alerta": 4.50,
        "umbral_evacuacion": 5.00,
        "fuente": "Prefectura Naval Argentina (cobertura parcial)",
        "conectado": False,
        "ultima_verificacion": "2026-08-04",
    },
    # NOTA (02/09/2026): se saco la cuenca "Pilcomayo" de esta lista.
    # El rio Pilcomayo NO pasa por la provincia del Chaco - recorre
    # exclusivamente Formosa (limite con Paraguay al norte, con Salta
    # al oeste). El limite real entre Chaco y Formosa es el rio
    # Bermejo/Teuco. Confirmado con fuentes geograficas (Parque
    # Nacional Rio Pilcomayo - Formosa; Wikipedia Rio Pilcomayo) y
    # senalado por un ingeniero hidraulico consultado por el equipo.
    # Las localidades que estaban mal asignadas a "pilcomayo"
    # (el_sauzalito, fuerte_esperanza) se reasignaron a "bermejo".
    #
    # ALCANCE DEL PROYECTO (02/09/2026): este backend cubre SOLO la
    # provincia del Chaco - se saco "formosa" (capital de OTRA
    # provincia) y "corrientes" de `localidades`. Si en el futuro se
    # arma cobertura de Corrientes/Formosa, va en un proyecto/repo
    # separado, no mezclado en cuencas-bot.
    # -------------------------------------------------------------
    # CUENCA INTERNA — sumada 29/08/2026. Distinta del Parana: no
    # depende del nivel del rio grande. Causo las inundaciones mas
    # graves de la historia de Resistencia: en 1982 el dique que
    # regulaba el valle del Rio Negro colapso, inundando el 70% de
    # la superficie urbana y evacuando casi el 50% de la poblacion
    # (Caputo et al. 1985, via CEPAL); en 1977 otro colapso del dique
    # en la desembocadura dejo entrar agua del riacho Barranqueras a
    # zonas densamente pobladas; en 1998 se llego a planificar la
    # evacuacion total del area metropolitana.
    #
    # HONESTIDAD DE DATOS: no encontramos una estacion de medicion
    # publica en tiempo real para el Rio Negro (no esta en la tabla
    # del INA ni en niveles_rios.json). nivel_metros y umbrales
    # quedan en None - pendiente de gestionar con la APA.
    # -------------------------------------------------------------
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
# ---------------------------------------------------------------------
localidades: dict = {
    "resistencia": {
        "nombre": "Resistencia", "cuenca_clave": "parana", "nivel_metros": 2.65,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (mismo tramo, ~8km)",
        "conectado": False, "ultima_verificacion": "2026-08-04",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Lluvias en el centro-este de Brasil (cuenca alta del Parana) y aporte del rio Paraguay. Tambien afectada por el rio interno Rio Negro / riacho Barranqueras - ver /organismos y /cuencas-internas.",
    },
    "barranqueras": {
        "nombre": "Barranqueras", "cuenca_clave": "parana", "nivel_metros": 2.65,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (medicion directa)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Lluvias en el centro-este de Brasil (cuenca alta del Parana) y aporte del rio Paraguay. Tambien afectada por el riacho Barranqueras (cuenca del Rio Negro).",
    },
    "puerto_bermejo": {
        "nombre": "Puerto Bermejo", "cuenca_clave": "paraguay", "nivel_metros": 2.75,
        "umbral_alerta": 6.50, "umbral_evacuacion": 7.00, "precipitacion_acumulada_mm": 15.0,
        "fuente": "Prefectura Naval Argentina, estacion Bermejo (aproximado, zona de confluencia)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Cuenca del rio Bermejo: nace en Bolivia y el noroeste argentino (Salta/Jujuy). Distinto origen que el Parana - ver caso Villa Rio Bermejito/Fortin Lavalle, abril 2026.",
    },
    "el_sauzalito": {
        "nombre": "El Sauzalito", "cuenca_clave": "bermejo", "nivel_metros": 3.00,
        "umbral_alerta": 5.20, "umbral_evacuacion": 6.00, "precipitacion_acumulada_mm": 6.00,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Cuenca del rio Bermejo, compartida con Bolivia y el noroeste argentino (Salta/Jujuy). Reasignado desde 'pilcomayo' el 02/09/2026: el Pilcomayo no pasa por Chaco.",
    },
    "isla_del_cerrito": {
        "nombre": "Isla del Cerrito", "cuenca_clave": "paraguay", "nivel_metros": 2.85,
        "umbral_alerta": 6.20, "umbral_evacuacion": 6.80, "precipitacion_acumulada_mm": 12.0,
        "fuente": "Prefectura Naval Argentina, estacion Isla del Cerrito (medicion directa)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Confluencia Parana-Paraguay: lluvias en Brasil, Paraguay y Bolivia.",
    },
    "puerto_vilelas": {
        "nombre": "Puerto Vilelas", "cuenca_clave": "parana", "nivel_metros": 2.65,
        "umbral_alerta": 6.00, "umbral_evacuacion": 6.50, "precipitacion_acumulada_mm": 12.0,
        "fuente": "Prefectura Naval Argentina, estacion Barranqueras (mismo tramo, ~5km)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
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
        "nombre": "Fuerte Esperanza", "cuenca_clave": "bermejo", "nivel_metros": 3.05,
        "umbral_alerta": 5.20, "umbral_evacuacion": 6.00, "precipitacion_acumulada_mm": 6.0,
        "fuente": "Reportes Prefectura / Comision Binacional (sin API publica estable)",
        "conectado": False, "ultima_verificacion": "2026-08-29",
        "tipo_inundacion_dominante": "fluvial",
        "influencia_internacional": "Cuenca del rio Bermejo, compartida con Bolivia y el noroeste argentino. Reasignado desde 'pilcomayo' el 02/09/2026: el Pilcomayo no pasa por Chaco.",
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
    "quitilipi": {
        "nombre": "Quitilipi", "cuenca_clave": None, "nivel_metros": None,
        "umbral_alerta": None, "umbral_evacuacion": None, "precipitacion_acumulada_mm": 32.0,
        "fuente": "Gobierno provincial anuncio plan integral para prevenir inundaciones en Quitilipi (chaco.gov.ar, mar. 2026). Ultimo evento real: temporal del 15/04/2026 con 78mm (Diario La Voz del Chaco).",
        "conectado": False, "ultima_verificacion": "2026-04-15",
        "tipo_inundacion_dominante": "pluvial",
        "influencia_internacional": None,
    },
    "castelli": {
        "nombre": "Juan José Castelli", "cuenca_clave": None, "nivel_metros": None,
        "umbral_alerta": None, "umbral_evacuacion": None, "precipitacion_acumulada_mm": 149.0,
        "fuente": "Identificada como zona de riesgo pluvial en Gomez et al. (FACENA-UNNE, 2014). Ministerio de Salud de Chaco desplego equipos en 6 centros de evacuados de Castelli tras el temporal de Santa Sylvina, 07/06/2026 (CharataChaco.Net).",
        "conectado": False, "ultima_verificacion": "2026-06-07",
        "tipo_inundacion_dominante": "pluvial",
        "influencia_internacional": None,
    },
    "presidencia_de_la_plaza": {
        "nombre": "Presidencia de la Plaza", "cuenca_clave": None, "nivel_metros": None,
        "umbral_alerta": None, "umbral_evacuacion": None, "precipitacion_acumulada_mm": 21.0,
        "fuente": "Identificada como zona de riesgo pluvial en Gomez et al. (FACENA-UNNE, 2014) bajo 'Pcia. de la Plaza'.",
        "conectado": False, "ultima_verificacion": "2014",
        "tipo_inundacion_dominante": "pluvial",
        "influencia_internacional": None,
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
    "bendiciones": {
        "nombre": "Barrio Bendiciones", "localidad_padre": "santa_sylvina",
        "lat": -27.7830, "lon": -61.1500, "precision": "aproximada (coordenadas del centro urbano de Santa Sylvina, no hay coordenadas exactas del barrio)",
        "motivo": "Temporal del 07/06/2026: voladura de techo de una vivienda (12 chapas de ~3.5m), confirmado por 4 fuentes (ChacoDiaPorDia, Diario Plaza 109, Alerta Urbana, CharataChaco.Net). Nota: las fuentes difieren sobre si hubo anegamiento de calles - la mayoria dice que no, una (CharataChaco.Net) menciona inundacion en barrios y zona centrica. Danno principal confirmado es por viento/tornado, no por agua.",
        "via_acceso_critica": "Caminos rurales del interior quedaron intransitables tras el temporal (no es un corte de acceso al barrio en si, es a nivel de toda la zona rural de Santa Sylvina)",
    },
    "victoria_quitilipi": {
        "nombre": "Barrio Victoria", "localidad_padre": "quitilipi",
        "lat": -26.8700, "lon": -60.2200, "precision": "aproximada (coordenadas del centro urbano de Quitilipi, no hay coordenadas exactas del barrio)",
        "motivo": "Testimonio de vecino (Higinio Encina, comunidad Qom) tuvo que evacuar su casa y refugiarse en la Escuela N°59 - LA NACION. OJO: la fuente de este nombre puntual es de un evento historico (no de 2026), pero Quitilipi tiene inundaciones recurrentes documentadas en el mismo tipo de terreno segun vecinos y prensa 2026 (chacoahora.com, sin nombre de barrio en esa nota) - se marca el nombre como referencia historica a confirmar si se repite en eventos recientes.",
        "via_acceso_critica": "Agua estancada sin escurrimiento (terreno llano, sin desagues) - mismo problema estructural que denuncian los vecinos en las notas de 2026.",
    },
    "macarena_quitilipi": {
        "nombre": "Barrio Macarena", "localidad_padre": "quitilipi",
        "lat": -26.8700, "lon": -60.2200, "precision": "aproximada (coordenadas del centro urbano de Quitilipi, no hay coordenadas exactas del barrio)",
        "motivo": "Testimonio de vecino (Ruben Alvarenga) - LA NACION. Misma nota de advertencia que Barrio Victoria: fuente de un evento historico, a confirmar vigencia en 2026.",
        "via_acceso_critica": "Agua estancada sin escurrimiento (terreno llano, sin desagues).",
    },
    "villa_rio_negro": {
        "nombre": "Villa Río Negro", "localidad_padre": "resistencia",
        "lat": -27.4253, "lon": -58.9764, "precision": "confirmada",
        "motivo": "Inundado en la crecida de 1982 tras el colapso del dique del Río Negro",
        "cota_inundacion_m": 4.80, 
        "via_acceso_critica": "Av. Sabin y Puente San Fernando (se corta por agua)",
    },
    "mujeres_argentinas": {
        "nombre": "Mujeres Argentinas", "localidad_padre": "resistencia",
        "lat": -27.4253, "lon": -58.9764, "precision": "aproximada (cerca de Villa Río Negro)",
        "motivo": "Ex Golf Club; inundado en la crecida de 1982",
        "cota_inundacion_m": 5.10, 
        "via_acceso_critica": "Av. Viuda de Ross / Av. San Martín",
    },
    "santa_lucia": {
        "nombre": "Santa Lucía", "localidad_padre": "resistencia",
        "lat": -27.4200, "lon": -58.9800, "precision": "aproximada",
        "motivo": "Identificado como uno de los barrios históricamente más afectados de Resistencia",
        "cota_inundacion_m": 4.95, 
        "via_acceso_critica": "Av. Lavalle prolongación norte",
    },
    "san_pedro_pescador": {
        "nombre": "San Pedro Pescador (Barrio de los Pescadores)", "localidad_padre": "barranqueras",
        "lat": -27.46085, "lon": -58.86805, "precision": "confirmada",
        "motivo": "Único asentamiento del Chaco sobre el cauce principal del Paraná; 43 familias autoevacuadas en 2014",
        "cota_inundacion_m": 5.60,
        "via_acceso_critica": "Rampa de bajada del Puente General Belgrano (se corta con 6.20m)",
    },
    "antequeras": {
        "nombre": "Puerto Antequeras", "localidad_padre": "barranqueras",
        "lat": -27.4425, "lon": -58.8503, "precision": "confirmada",
        "motivo": "Zona pesquera ribereña, afectada en múltiples crecidas históricas",
        "cota_inundacion_m": 5.40, 
        "via_acceso_critica": "Camino costero desde Barranqueras (intransitable con lluvia)",
    },
    # NOTA (02/09/2026): se saco el barrio "La Floresta" - esta en la
    # ciudad de Formosa (capital de OTRA provincia), fuera del alcance
    # de este portal (solo Chaco). Ver nota de alcance mas arriba en
    # `localidades`.
    "tres_bocas": {
        "nombre": "Paraje Las Tres Bocas", "localidad_padre": "puerto_vilelas",
        "lat": -27.5300, "lon": -58.8600, "precision": "aproximada",
        "motivo": "Zona ribereña que queda aislada por tierra en crecidas grandes; en 2023, con Barranqueras en 6.54 m (evacuación), ~150 familias solo accedían en lancha desde Empedrado (Corrientes). Los parajes vecinos Soto y Cinco Bocas sufren el mismo aislamiento.",
        "cota_inundacion_m": 5.80, 
        "via_acceso_critica": "Camino vecinal del Paranacito (inundable) / Acceso fluvial",
    },
    "parajes_sauzalito": {
        "nombre": "Comunidades Wichí y Parajes (El Sauzal, Tartagal, Tres Pozos)", "localidad_padre": "el_sauzalito",
        "lat": -24.3800, "lon": -61.6200, "precision": "territorial dispersa, sin coordenadas exactas por paraje",
        "motivo": "Cortes recurrentes de caminos por crecientes del río Bermejo y desbordes de cañadas. Pérdida de conectividad celular y aislamiento alimentario.",
        "cota_inundacion_m": 4.20, 
        "via_acceso_critica": "Ruta Provincial 3 y picadas de tierra (intransitables)",
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
# ALERTAS SMN (en memoria, no en Firestore) — agregado 02/09/2026
#
# Cubre lo que las estaciones de rio NO pueden avisar: tormentas
# fuertes / lluvia localizada, sobre todo para las 6 localidades
# pluviales que no tienen estacion de rio cerca (Charata, Santa
# Sylvina, Quitilipi, Castelli, Presidencia de la Plaza, San Martin).
#
# Por que EN MEMORIA y no en Firestore: un aviso del SMN vigente hoy
# no importa mañana - no hace falta persistirlo entre reinicios, se
# resincroniza solo la proxima vez que corre actualizar_alertas_smn.py
# (via GitHub Actions, cada 20-30 min, igual patron que
# actualizar_niveles.py / actualizar_vertederos.py).
# ---------------------------------------------------------------------
ALERTAS_SMN: dict = {
    "alertas": [],
    "cantidad": 0,
    "ultima_verificacion": None,
}


# ---------------------------------------------------------------------
# CLASIFICACION DE ESTADO (verde/amarillo/rojo) — compartida
# ---------------------------------------------------------------------
def calcular_estado(nivel, umbral_alerta, umbral_evacuacion, anomalia_velocidad: bool = False):
    """
    Sistema de 5 niveles de alerta (inspirado en el sistema de 5 niveles
    de la Agencia Meteorologica de Japon - JMA), en vez del esquema
    binario anterior (Normal/Alerta/Evacuacion), MAS un sexto nivel por
    VELOCIDAD de ascenso (agregado 02/09/2026).

    Niveles (de menor a mayor riesgo):
      NORMAL            - por debajo del 70% del umbral de alerta, sin
                           ascenso anomalo.
      MONITOREO         - entre 70% y 90% del umbral de alerta (vigilar).
      ALERTA_VELOCIDAD  - todavia por debajo del umbral de alerta oficial,
                           pero subiendo mas rapido de lo normal (ver
                           UMBRAL_VELOCIDAD_M_H). Detecta una crecida
                           SUBITA antes de que cruce el umbral absoluto,
                           no despues - es lo que suma este nivel sobre
                           el esquema anterior.
      ATENCION          - entre 90% y 100% del umbral de alerta (preparar).
      ALERTA            - alcanzo el umbral de alerta oficial (Prefectura/APA).
      EVACUACION        - alcanzo el umbral de evacuacion oficial.

    Los umbrales de ALERTA y EVACUACION son siempre los oficiales
    (verificados contra fich.unl.edu.ar). Los cortes de MONITOREO/
    ATENCION al 70%/90%, y el umbral de velocidad, son margen de
    seguridad propio del proyecto, no una norma oficial de Prefectura -
    se pueden ajustar si Defensa Civil Chaco define otro criterio.
    """
    if nivel is None or umbral_alerta is None or umbral_evacuacion is None:
        return "SIN_DATO", "⚪"
    if nivel >= umbral_evacuacion:
        return "EVACUACION", "🔴"
    if nivel >= umbral_alerta:
        return "ALERTA", "🟠"
    if nivel >= umbral_alerta * 0.90:
        return "ATENCION", "🟡"
    if anomalia_velocidad:
        return "ALERTA_VELOCIDAD", "🟣"
    if nivel >= umbral_alerta * 0.70:
        return "MONITOREO", "🔵"
    return "NORMAL", "🟢"


def _cuenca_con_estado(clave: str) -> dict:
    c = CUENCAS[clave]
    try:
        vivo = firestore_db.leer_estado(f"cuenca_{clave}") or {}
    except Exception:
        vivo = {}  # Firestore con hipo momentaneo: se sigue con el valor semilla, no se rompe la pagina
    c = {**c, **vivo}
    estado, emoji = calcular_estado(
        c["nivel_metros"], c["umbral_alerta"], c["umbral_evacuacion"],
        anomalia_velocidad=c.get("anomalia_velocidad", False),
    )
    return {**c, "clave": clave, "estado": estado, "emoji": emoji}


def _localidad_con_estado(clave: str) -> dict:
    base = localidades[clave]
    try:
        vivo = firestore_db.leer_estado(clave) or {}
    except Exception:
        vivo = {}  # Firestore con hipo momentaneo: se sigue con el valor semilla, no se rompe la pagina
    loc = {**base, **vivo}
    estado, emoji = calcular_estado(
        loc["nivel_metros"], loc["umbral_alerta"], loc["umbral_evacuacion"],
        anomalia_velocidad=loc.get("anomalia_velocidad", False),
    )
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


class ActualizacionAlertasSMN(BaseModel):
    alertas: list[dict]
    cantidad: int
    ultima_verificacion: str | None = None


class LecturaSensorIoT(BaseModel):
    """
    Lectura enviada por un sensor IoT propio (ESP32/ESP8266 + sensor
    ultrasonico de nivel, ver docs/sensores-iot.md). Pensado para
    localidades sin estacion de Prefectura, como El Sauzalito o Pampa
    del Indio.
    """
    nivel_metros: float | None = None
    precipitacion_mm: float | None = None
    bateria_pct: float | None = None


# Clave simple para autenticar sensores IoT propios. Se configura en
# Render -> Settings -> Environment como API_KEY_SENSORES. Sin esto
# configurado, el endpoint queda abierto (util solo para pruebas) - se
# recomienda configurarla antes de desplegar sensores reales para que
# no cualquiera pueda mandar lecturas falsas.
API_KEY_SENSORES = os.environ.get("API_KEY_SENSORES")


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


# ---------------------------------------------------------------------
# ORGANISMOS RELEVANTES — investigado y verificado 29/08/2026.
# ---------------------------------------------------------------------
ORGANISMOS: dict = {
    "smn": {
        "nombre": "Servicio Meteorologico Nacional (SMN)",
        "nivel": "nacional",
        "dependencia": "Ministerio de Defensa",
        "rol": "Pronostico del tiempo y sistema de alerta temprana meteorologica (3 niveles: amarillo/naranja/rojo).",
        "url": "https://www.smn.gob.ar",
        "url_alertas": "https://www.smn.gob.ar/alertas",
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
def relieve_provincial():
    return CONTEXTO_RELIEVE


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


@app.post("/sensores/{clave}/lectura")
def recibir_lectura_sensor(clave: str, datos: LecturaSensorIoT, x_api_key: str | None = Header(default=None)):
    """
    Recibe una lectura de un sensor IoT propio (ver docs/sensores-iot.md
    para el hardware: ESP32 + sensor ultrasonico + panel solar, costo
    aprox. USD 50-100 por unidad). Pensado para localidades que hoy
    estan en null porque Prefectura no tiene estacion ahi (El Sauzalito,
    Pampa del Indio, Fuerte Esperanza).

    Requiere el header X-API-Key con el valor de la variable de entorno
    API_KEY_SENSORES configurada en Render. Sin esa variable configurada
    el endpoint queda sin autenticar (solo para pruebas).
    """
    if API_KEY_SENSORES and x_api_key != API_KEY_SENSORES:
        return {"error": "API key invalida o faltante. Mandar el header X-API-Key."}

    clave = clave.lower()
    if clave not in localidades:
        return {"error": f"Localidad '{clave}' no reconocida"}

    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if datos.nivel_metros is not None:
        localidades[clave]["nivel_metros"] = datos.nivel_metros
        localidades[clave]["conectado"] = True
        if "Sensor IoT propio" not in localidades[clave]["fuente"]:
            localidades[clave]["fuente"] = f"Sensor IoT propio (UDC) - antes: {localidades[clave]['fuente']}"

    if datos.precipitacion_mm is not None:
        localidades[clave]["precipitacion_acumulada_mm"] = datos.precipitacion_mm

    localidades[clave]["ultima_verificacion"] = ahora

    return {
        "ok": True,
        "localidad": _localidad_con_estado(clave),
        "bateria_pct": datos.bateria_pct,
    }


def calcular_riesgo_pluvial(clave: str) -> dict:
    """
    Puntaje de riesgo para localidades PLUVIALES (sin estacion de rio -
    tipo_inundacion_dominante == 'pluvial'), como Charata o Santa
    Sylvina.

    OJO: esto NO es un modelo de IA ni fue entrenado con datos
    historicos (a diferencia de Google Flood Hub / Groundsource). Es
    una heuristica simple y transparente basada en dos senales
    honestas: la lluvia acumulada ya cargada para esa localidad, y la
    cantidad de reportes ciudadanos de anegamiento de las ultimas 24
    horas. Se etiqueta como heuristica a proposito para no dar una
    falsa sensacion de precision.
    """
    loc = localidades.get(clave)
    if loc is None:
        return {"riesgo": "SIN_DATO", "detalle": "localidad no encontrada"}

    lluvia = loc.get("precipitacion_acumulada_mm")
    if lluvia is None:
        return {"riesgo": "SIN_DATO", "detalle": "sin dato de lluvia acumulada", "metodo": "heuristica_no_ia"}

    if supabase:
        try:
            fuente_reportes = (
                supabase.table("reportes_ciudadanos").select("*").eq("localidad", clave).execute().data
            )
        except Exception:
            fuente_reportes = []
    else:
        fuente_reportes = reportes_ciudadanos

    ahora = datetime.now(timezone.utc)
    reportes_recientes = 0
    for r in fuente_reportes:
        if str(r.get("localidad", "")).lower() != clave:
            continue
        ts_raw = r.get("timestamp") or r.get("created_at") or ""
        try:
            ts_limpio = str(ts_raw).replace(" UTC", "").replace("Z", "").split(".")[0].replace("T", " ")
            ts_dt = datetime.strptime(ts_limpio, "%Y-%m-%d %H:%M:%S") if len(ts_limpio) > 16 else datetime.strptime(ts_limpio, "%Y-%m-%d %H:%M")
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            if (ahora - ts_dt).total_seconds() <= 24 * 3600:
                reportes_recientes += 1
        except Exception:
            continue

    puntaje = 0
    if lluvia >= 80:
        puntaje += 3
    elif lluvia >= 40:
        puntaje += 2
    elif lluvia >= 15:
        puntaje += 1
    puntaje += min(reportes_recientes, 3)

    if puntaje >= 5:
        riesgo = "ALTO"
    elif puntaje >= 3:
        riesgo = "MEDIO"
    elif puntaje >= 1:
        riesgo = "BAJO"
    else:
        riesgo = "MINIMO"

    return {
        "riesgo": riesgo,
        "puntaje": puntaje,
        "lluvia_acumulada_mm": lluvia,
        "reportes_ciudadanos_24h": reportes_recientes,
        "metodo": "heuristica_transparente_no_ia",
    }


@app.get("/riesgo-pluvial/{clave}")
def obtener_riesgo_pluvial(clave: str):
    return calcular_riesgo_pluvial(clave.lower())


@app.get("/riesgo-pluvial")
def listar_riesgo_pluvial():
    """Riesgo heuristico para todas las localidades pluviales (sin estacion de rio)."""
    pluviales = [c for c, l in localidades.items() if l.get("tipo_inundacion_dominante") == "pluvial"]
    return {clave: calcular_riesgo_pluvial(clave) for clave in pluviales}


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

    ahora = datetime.now(timezone.utc)

    # Velocidad de ascenso: comparamos contra la ULTIMA lectura guardada
    # en Firestore (no contra el valor semilla en memoria, que no se
    # actualiza solo). Si no hay lectura previa (primera vez que se
    # reporta esta localidad) o paso muy poco tiempo, no se puede
    # calcular una velocidad confiable todavia.
    try:
        estado_anterior = firestore_db.leer_estado(clave) or {}
    except Exception:
        estado_anterior = {}

    nivel_anterior = estado_anterior.get("nivel_metros", localidades[clave]["nivel_metros"])
    hora_anterior_iso = estado_anterior.get("hora_lectura_anterior")

    velocidad_m_h = None
    anomalia_velocidad = False
    if hora_anterior_iso and nivel_anterior is not None:
        try:
            hora_anterior = datetime.fromisoformat(hora_anterior_iso)
            horas_transcurridas = (ahora - hora_anterior).total_seconds() / 3600
            if horas_transcurridas >= (1 / 60):  # al menos 1 minuto entre lecturas
                velocidad_m_h = round((datos.nivel_metros - nivel_anterior) / horas_transcurridas, 3)
                anomalia_velocidad = velocidad_m_h >= UMBRAL_VELOCIDAD_M_H
        except (ValueError, TypeError):
            pass  # timestamp con formato inesperado: se sigue sin velocidad, no se rompe el request

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

    try:
        firestore_db.guardar_estado(clave, nuevo_estado)
    except Exception:
        # Si Firestore falla, al menos actualizamos en memoria para esta
        # instancia del proceso - no ideal (se pierde en el proximo
        # reinicio) pero mejor que perder la lectura por completo.
        localidades[clave].update(nuevo_estado)

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


@app.get("/alertas")
def listar_alertas_smn():
    """Alertas meteorologicas vigentes del SMN (Chaco en general + localidades
    pluviales especificas sin rio cerca, como Charata o Santa Sylvina)."""
    return ALERTAS_SMN


@app.post("/alertas/actualizar")
def actualizar_alertas_smn(datos: ActualizacionAlertasSMN):
    """Llamado por actualizar_alertas_smn.py cada vez que corre (GitHub Actions)."""
    ALERTAS_SMN["alertas"] = datos.alertas
    ALERTAS_SMN["cantidad"] = datos.cantidad
    ALERTAS_SMN["ultima_verificacion"] = (
        datos.ultima_verificacion or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )
    return {"ok": True, "alertas_smn": ALERTAS_SMN}


# ---------------------------------------------------------------------
# SOS Y REPORTES CIUDADANOS (Prioridad 1 del roadmap)
#
# Con SUPABASE_URL/SUPABASE_KEY configuradas, esto se guarda en
# Postgres (persiste entre reinicios de Render). Sin esas variables,
# sigue funcionando como antes: listas en memoria, se pierden al
# reiniciar el servicio.
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
    if supabase:
        supabase.table("sos_tickets").insert(ticket).execute()
    else:
        tickets_sos.insert(0, ticket)
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
