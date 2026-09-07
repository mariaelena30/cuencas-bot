"""
alertas_dispatcher.py
----------------------
Portal Hidrico Chaco - Despachador de alertas tempranas (SOLO WhatsApp).

Se saco Telegram de este script: en la comunidad nadie lo usa, asi que
no tenia sentido invertir tiempo ahi. Todo el envio pasa por WhatsApp,
usando el MISMO numero que ya tienen conectado (whatsapp_webhook.py).

DOS TIPOS DE MENSAJE DE WHATSAPP, Y POR QUE SE USA CADA UNO:

  1) A DEFENSA CIVIL / BOMBEROS -> mensaje de texto libre
     (send_whatsapp_message, ya existia). Funciona siempre y cuando esas
     personas le hayan escrito al bot en las ultimas 24hs - como son
     pocos numeros que ya interactuan seguido con el bot, esto no suele
     ser un problema en la practica. Si en algun momento no funciona
     (pasaron mas de 24hs sin que escriban), lo mas simple es que le
     manden un mensaje al bot una vez por semana para mantener la
     ventana abierta, o sumarlos tambien a la plantilla de abajo.

  2) A VECINOS SUSCRIPTOS -> PLANTILLA OFICIAL (send_whatsapp_template)
     Un vecino se suscribe UNA vez (escribiendole "alertas" al bot), y
     a partir de ahi puede pasar cualquier cantidad de dias sin escribir
     - el aviso le va a llegar igual, porque las plantillas de Meta
     estan pensadas exactamente para esto (categoria UTILITY: alertas
     de cuenta / notificaciones). Ver la explicacion completa y el
     texto de la plantilla a crear en whatsapp_webhook.py
     (send_whatsapp_template).

     IMPORTANTE: la plantilla "alerta_hidrica_chaco" tiene que estar
     CREADA Y APROBADA por Meta antes de que esto funcione (una sola
     vez, 5-10 minutos para crearla + minutos/horas para que la
     aprueben). Sin la plantilla aprobada, este script no puede avisar
     a nadie que no le haya escrito al bot en las ultimas 24hs.

QUE PASO CON TELEGRAM Y GOOGLE:
  - Telegram: descartado, nadie de la comunidad lo usa.
  - Google Flood Hub: es un canal de PRONOSTICO (te dice si viene una
    crecida), no de ENVIO de mensajes - no reemplaza a este script, lo
    complementa. Se integra por separado una vez que aprueben el acceso
    (lista de espera, ver el link que te paso en el chat).
  - Firebase (push del navegador): sigue como tercer canal a futuro,
    no se toco en este script.

PERSISTENCIA DEL ESTADO (evitar reenviar la misma alerta):
Igual que antes: Supabase si esta configurado, si no, un JSON local.

COMO PROGRAMARLO: GitHub Actions cada 10-15 minutos (mismo patron que
actualizar_niveles.py). Ver el workflow de ejemplo mas abajo en los
comentarios finales.

VARIABLES DE ENTORNO A CONFIGURAR EN RENDER:
    WHATSAPP_TOKEN                  (ya la tienen, se reusa)
    WHATSAPP_PHONE_NUMBER_ID        (ya la tienen, se reusa)
    WHATSAPP_TEMPLATE_ALERTA        (default: alerta_hidrica_chaco)
    WHATSAPP_TEMPLATE_IDIOMA        (default: es_AR)
    WHATSAPP_NUMEROS_DEFENSA_CIVIL  -> numeros separados por coma
    BACKEND_URL                     (ya la tienen)
    SUPABASE_URL / SUPABASE_KEY     (ya las tienen)
"""

import os
import json
import logging
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alertas_dispatcher")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:10000")
WHATSAPP_NUMEROS_DEFENSA_CIVIL = [
    n.strip() for n in os.environ.get("WHATSAPP_NUMEROS_DEFENSA_CIVIL", "").split(",") if n.strip()
]

ESTADO_LOCAL_PATH = Path("estado_fases.json")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------
# MENSAJES POR FASE
#
# La FASE se toma de "estado" que ya devuelve /localidades (calculado
# por calcular_estado() en main.py) - la MISMA que pinta las tarjetas
# de la web. Una sola fuente de verdad, ver la nota larga sobre esto
# en la version anterior de este archivo si la tenes a mano.
# ---------------------------------------------------------------------
def _mensajes_por_fase(fase: str, loc: dict) -> dict:
    nombre = loc["nombre"]
    nivel = loc["nivel_metros"]
    umbral_alerta = loc["umbral_alerta"]
    umbral_evacuacion = loc["umbral_evacuacion"]

    if fase == "NORMAL":
        return {
            "mostrar_a_vecinos": True,
            "emoji_titulo": "🟢 Normal",
            "nivel_texto": f"{nivel:.2f} m — dentro de rango normal",
            "mensaje_tecnico": f"Nivel actual {nivel:.2f} m, dentro de rango normal. Sin acción requerida.",
        }
    if fase == "MONITOREO":
        return {
            "mostrar_a_vecinos": False,  # a proposito: no se avisa al vecino todavia
            "emoji_titulo": None,
            "nivel_texto": None,
            "mensaje_tecnico": (
                f"[SOLO PERSONAL] {nombre}: nivel {nivel:.2f} m (por encima del 70% del "
                f"umbral de alerta de {umbral_alerta:.2f} m). Empezar a seguir de cerca."
            ),
        }
    if fase == "ATENCION":
        return {
            "mostrar_a_vecinos": True,
            "emoji_titulo": "🟡 Atención",
            "nivel_texto": f"{nivel:.2f} m, acercándose al umbral de alerta ({umbral_alerta:.2f} m)",
            "mensaje_tecnico": (
                f"[DEFENSA CIVIL / BOMBEROS] {nombre}: nivel {nivel:.2f} m, acercándose al "
                f"umbral de alerta ({umbral_alerta:.2f} m). Recomendado iniciar preparativos."
            ),
        }
    if fase == "ALERTA":
        return {
            "mostrar_a_vecinos": True,
            "emoji_titulo": "⚠️ Alerta",
            "nivel_texto": f"{nivel:.2f} m, superó el umbral de alerta ({umbral_alerta:.2f} m)",
            "mensaje_tecnico": (
                f"[ALERTA ACTIVA] {nombre}: nivel {nivel:.2f} m, superó umbral de alerta "
                f"({umbral_alerta:.2f} m). Faltan {umbral_evacuacion - nivel:.2f} m para evacuación."
            ),
        }
    if fase == "EVACUACION":
        return {
            "mostrar_a_vecinos": True,
            "emoji_titulo": "🔴 Evacuación",
            "nivel_texto": f"{nivel:.2f} m, superó el umbral de evacuación ({umbral_evacuacion:.2f} m)",
            "mensaje_tecnico": (
                f"[EVACUACIÓN ACTIVA] {nombre}: nivel {nivel:.2f} m, superó umbral de evacuación "
                f"({umbral_evacuacion:.2f} m). Activar protocolo con barrios vulnerables de la zona."
            ),
        }
    return {"mostrar_a_vecinos": False, "emoji_titulo": None, "nivel_texto": None, "mensaje_tecnico": f"{nombre}: sin dato."}


# ---------------------------------------------------------------------
# ESTADO: ultima fase avisada por localidad
# ---------------------------------------------------------------------
def cargar_estado_previo() -> dict:
    if supabase:
        try:
            filas = supabase.table("estado_fases_localidad").select("*").execute().data
            return {f["id_localidad"]: f["fase"] for f in filas}
        except Exception:
            logger.exception("No se pudo leer estado_fases_localidad de Supabase")
            return {}
    if ESTADO_LOCAL_PATH.exists():
        return json.loads(ESTADO_LOCAL_PATH.read_text(encoding="utf-8"))
    return {}


def guardar_fase(clave: str, fase: str):
    if supabase:
        try:
            supabase.table("estado_fases_localidad").upsert(
                {"id_localidad": clave, "fase": fase}
            ).execute()
            return
        except Exception:
            logger.exception(f"No se pudo guardar fase de {clave} en Supabase")
    estado = {}
    if ESTADO_LOCAL_PATH.exists():
        estado = json.loads(ESTADO_LOCAL_PATH.read_text(encoding="utf-8"))
    estado[clave] = fase
    ESTADO_LOCAL_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------
# LOOP PRINCIPAL
# ---------------------------------------------------------------------
async def revisar_y_despachar():
    # Imports diferidos: este script puede correr como job separado
    # (GitHub Actions) sin levantar todo FastAPI.
    from whatsapp_webhook import send_whatsapp_message, send_whatsapp_template, listar_suscriptores_activos

    estado_previo = cargar_estado_previo()

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BACKEND_URL}/localidades", timeout=15)
        localidades = resp.json()["localidades"]

        for clave, loc in localidades.items():
            fase_nueva = loc["estado"]
            if fase_nueva == "SIN_DATO":
                continue

            fase_anterior = estado_previo.get(clave)
            if fase_nueva == fase_anterior:
                continue  # sin cambios, no se manda nada (evita spam)

            logger.info(f"{clave}: {fase_anterior} -> {fase_nueva}")

            resultado = _mensajes_por_fase(fase_nueva, loc)

            # A Defensa Civil / Bomberos: SIEMPRE, mensaje libre.
            texto_tecnico = f"[{loc['nombre']}] {resultado['mensaje_tecnico']}"
            for numero in WHATSAPP_NUMEROS_DEFENSA_CIVIL:
                await send_whatsapp_message(numero, texto_tecnico)

            # A vecinos suscriptos: SOLO si corresponde mostrar (no en
            # MONITOREO), usando la plantilla oficial aprobada.
            if resultado["mostrar_a_vecinos"] and resultado["emoji_titulo"]:
                suscriptores = listar_suscriptores_activos()
                logger.info(f"Mandando plantilla a {len(suscriptores)} suscriptores para {clave}")
                for numero in suscriptores:
                    await send_whatsapp_template(
                        numero,
                        emoji_titulo=resultado["emoji_titulo"],
                        localidad=loc["nombre"],
                        nivel_texto=resultado["nivel_texto"],
                    )

                # Notificacion push (Firebase) - tercer canal, ademas
                # de WhatsApp. Llega aunque el celular este en
                # silencio, usando el mismo criterio "mostrar_a_vecinos"
                # que WhatsApp (no molesta en fase MONITOREO).
                try:
                    import firestore_db
                    urgente = fase_nueva in ("ALERTA", "EVACUACION")
                    resultado_push = firestore_db.enviar_push_localidad(
                        localidad=clave,
                        titulo=f"{resultado['emoji_titulo']} - {loc['nombre']}",
                        cuerpo=resultado["nivel_texto"],
                        urgente=urgente,
                    )
                    logger.info(f"Push a {clave}: {resultado_push}")
                except Exception:
                    logger.exception(f"No se pudo mandar push para {clave}")

            guardar_fase(clave, fase_nueva)


if __name__ == "__main__":
    import asyncio
    asyncio.run(revisar_y_despachar())
