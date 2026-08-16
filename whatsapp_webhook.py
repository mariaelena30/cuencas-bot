"""
whatsapp_webhook.py
--------------------
Integracion de WhatsApp Cloud API (Meta) para el Portal Hidrico Chaco.
Se conecta EN EL MISMO PROCESO a las funciones que ya usa main.py para
Telegram (no hace falta HTTP interno, es todo en memoria).

COMO INTEGRARLO (una sola linea al final de main.py, despues de todos
los @app.get / @app.post que ya existen):

    from whatsapp_webhook import router as whatsapp_router
    app.include_router(whatsapp_router)

VARIABLES DE ENTORNO A AGREGAR EN RENDER (Settings > Environment),
mismo lugar donde esta TFG_BOT_TOKEN:

    WHATSAPP_TOKEN            -> token de acceso (Meta for Developers)
    WHATSAPP_PHONE_NUMBER_ID  -> ID del numero de WhatsApp Business (lo da Meta)
    WHATSAPP_VERIFY_TOKEN     -> string inventado por vos, ej "cuencas_chaco_2026"
                                  (Meta te lo va a pedir al configurar el webhook)

La URL que vas a cargar en el panel de Meta for Developers es:
    https://<tu-app>.onrender.com/whatsapp/webhook
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Request, Response, Query

logger = logging.getLogger("whatsapp_webhook")
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "cuencas_chaco_2026")
GRAPH_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

# Reportes SOS: un JSONL simple (una linea = un reporte). Se puede leer
# despues desde el dashboard de Streamlit o desde un endpoint propio.
SOS_LOG_PATH = Path(os.getenv("SOS_LOG_PATH", "sos_reports.jsonl"))


# ---------------------------------------------------------------------------
# 1) VERIFICACION DEL WEBHOOK (Meta llama a esto UNA vez al configurarlo)
# ---------------------------------------------------------------------------
@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("Webhook de WhatsApp verificado correctamente")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("Verificacion de webhook fallo: token no coincide")
    return Response(content="Verification failed", status_code=403)


# ---------------------------------------------------------------------------
# 2) RECEPCION DE MENSAJES
# ---------------------------------------------------------------------------
@router.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()

    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return {"status": "ignored"}  # ej. confirmaciones de "leido"

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message["type"]

        if msg_type == "text":
            await handle_text_message(from_number, message["text"]["body"].strip())
        elif msg_type == "location":
            loc = message["location"]
            await handle_location_message(from_number, loc["latitude"], loc["longitude"])
        else:
            await send_whatsapp_message(
                from_number,
                "Por ahora puedo leer texto y ubicación compartida. Escribí *ayuda*.",
            )

    except (KeyError, IndexError) as e:
        logger.info(f"Payload sin mensaje procesable: {e}")

    return {"status": "received"}


# ---------------------------------------------------------------------------
# 3) FORMATEO — mismo criterio que formatear_ciudad/formatear_cuenca de bot.py
#    pero en markdown de WhatsApp (*negrita*, no HTML)
# ---------------------------------------------------------------------------
def _formatear_localidad(datos: dict, nombre_cuenca: str) -> str:
    aviso = "" if datos["conectado"] else "\n⚠️ _Dato de demostración, sin conexión automática aún._"
    return (
        f"{datos['emoji']} *{datos['nombre']}* (cuenca: {nombre_cuenca})\n"
        f"Nivel: {datos['nivel_metros']} m — Estado: {datos['estado']}\n"
        f"Umbral alerta: {datos['umbral_alerta']} m | evacuación: {datos['umbral_evacuacion']} m\n"
        f"Fuente: {datos['fuente']}\n"
        f"Última verificación: {datos['ultima_verificacion']}"
        f"{aviso}"
    )


def _formatear_cuenca(datos: dict) -> str:
    aviso = "" if datos["conectado"] else "\n⚠️ _Dato de demostración, sin conexión automática aún._"
    return (
        f"{datos['emoji']} *{datos['nombre']}* ({datos['estacion']})\n"
        f"Nivel: {datos['nivel_metros']} m — Estado: {datos['estado']}\n"
        f"Umbral alerta: {datos['umbral_alerta']} m | evacuación: {datos['umbral_evacuacion']} m\n"
        f"Fuente: {datos['fuente']}\n"
        f"Última verificación: {datos['ultima_verificacion']}"
        f"{aviso}"
    )


# ---------------------------------------------------------------------------
# 4) LOGICA DE COMANDOS DE TEXTO — conectada directo a main.py
# ---------------------------------------------------------------------------
async def handle_text_message(from_number: str, text: str):
    # Import diferido (no al tope del archivo) para evitar problemas de
    # import circular con main.py, que es quien importa este modulo.
    from main import (
        CUENCAS,
        localidades,
        _cuenca_con_estado,
        _localidad_con_estado,
        BARRIOS_VULNERABLES,
    )

    comando = text.lower().strip()

    if comando in ("hola", "ayuda", "menu", "start", "/start"):
        respuesta = (
            "Hola! Soy el bot del *Portal Hídrico Chaco*.\n\n"
            "Comandos:\n"
            "• *cuencas* — resumen de las 4 cuencas\n"
            "• *nivel [localidad]* — ej: nivel barranqueras\n"
            "• *barrios [localidad]* — zonas vulnerables de esa localidad\n"
            "• *sos* — reportar una emergencia (te pido tu ubicación)\n\n"
            "También podés compartir tu ubicación en cualquier momento si estás en riesgo."
        )
        await send_whatsapp_message(from_number, respuesta)
        return

    if comando == "cuencas":
        lineas = [
            f"{c['emoji']} *{c['nombre']}*: {c['nivel_metros']} m ({c['estado']})"
            for c in (_cuenca_con_estado(clave) for clave in CUENCAS)
        ]
        await send_whatsapp_message(
            from_number, "*Estado de las 4 cuencas:*\n\n" + "\n".join(lineas)
        )
        return

    if comando.startswith("nivel "):
        clave = comando.replace("nivel ", "").strip().replace(" ", "_")
        if clave not in localidades:
            await send_whatsapp_message(
                from_number,
                f"No encontré la localidad '{clave}'. Escribí *ayuda* para ver opciones.",
            )
            return
        loc = _localidad_con_estado(clave)
        nombre_cuenca = CUENCAS[loc["cuenca_clave"]]["nombre"]
        await send_whatsapp_message(from_number, _formatear_localidad(loc, nombre_cuenca))
        return

    if comando.startswith("barrios"):
        clave = comando.replace("barrios", "").strip().replace(" ", "_")
        if not clave:
            await send_whatsapp_message(
                from_number, "Decime de qué localidad. Ej: *barrios barranqueras*"
            )
            return
        if clave not in localidades:
            await send_whatsapp_message(from_number, f"No encontré la localidad '{clave}'.")
            return
        padre = _localidad_con_estado(clave)
        barrios = [b for b in BARRIOS_VULNERABLES.values() if b["localidad_padre"] == clave]
        if not barrios:
            await send_whatsapp_message(
                from_number, f"No tengo barrios vulnerables cargados para {padre['nombre']} todavía."
            )
            return
        texto = f"📍 *Zonas vulnerables en {padre['nombre']}:*\n\n"
        texto += "\n\n".join(f"{padre['emoji']} *{b['nombre']}*\n{b['motivo']}" for b in barrios)
        await send_whatsapp_message(from_number, texto)
        return

    if comando == "sos":
        await send_whatsapp_message(
            from_number,
            "Entendido. Por favor compartí tu ubicación ahora mismo: tocá el clip 📎 > "
            "Ubicación > Ubicación actual, para que Defensa Civil pueda encontrarte.",
        )
        return

    await send_whatsapp_message(
        from_number, "No entendí ese mensaje. Escribí *ayuda* para ver los comandos disponibles."
    )


# ---------------------------------------------------------------------------
# 5) UBICACION (SOS)
# ---------------------------------------------------------------------------
async def handle_location_message(from_number: str, lat: float, lon: float):
    reporte = {
        "telefono": from_number,
        "latitud": lat,
        "longitud": lon,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "atendido": False,
    }
    with SOS_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(reporte, ensure_ascii=False) + "\n")
    logger.info(f"Reporte SOS recibido: {reporte}")

    await send_whatsapp_message(
        from_number,
        "Recibimos tu ubicación, quedó registrada para Defensa Civil. "
        "Si podés, contanos tu nombre y cuántas personas están con vos.",
    )


# ---------------------------------------------------------------------------
# 6) ENVIO (Graph API)
# ---------------------------------------------------------------------------
async def send_whatsapp_message(to_number: str, text: str):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        logger.error("Faltan WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID en las variables de entorno.")
        return
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(GRAPH_API_URL, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.error(f"Error enviando mensaje WhatsApp: {resp.status_code} {resp.text}")
        return resp


# ---------------------------------------------------------------------------
# 7) LECTURA DE REPORTES SOS (para que el dashboard los pinte en el mapa)
# ---------------------------------------------------------------------------
@router.get("/sos-reports")
async def get_sos_reports():
    if not SOS_LOG_PATH.exists():
        return []
    reportes = []
    with SOS_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                reportes.append(json.loads(line))
    return reportes
