"""
whatsapp_webhook.py
--------------------
Integracion de WhatsApp Cloud API (Meta) para el Portal Hidrico Chaco.
Bot SOLO INFORMATIVO: consulta de niveles y zonas vulnerables. No recibe
ni deriva pedidos de auxilio (nadie los atiende desde aca).

COMO INTEGRARLO (al final de main.py):

    from whatsapp_webhook import router as whatsapp_router
    app.include_router(whatsapp_router)

VARIABLES DE ENTORNO EN RENDER (Environment):

    WHATSAPP_TOKEN            -> token de acceso (Meta for Developers)
    WHATSAPP_PHONE_NUMBER_ID  -> ID del numero de WhatsApp Business
    WHATSAPP_VERIFY_TOKEN     -> string inventado por vos (Meta lo pide al
                                 configurar el webhook). Obligatorio.
    WHATSAPP_APP_SECRET       -> "Clave secreta de la app" (Meta for
                                 Developers > Configuracion de la app >
                                 Basica). Se usa para comprobar que cada
                                 mensaje viene realmente de Meta. Obligatorio:
                                 sin esta variable el webhook rechaza todo.

URL del webhook en Meta:  https://<tu-app>.onrender.com/whatsapp/webhook

CAMBIOS (03/10/2026):
- Se verifica la firma X-Hub-Signature-256 de cada mensaje entrante.
- Se elimino /whatsapp/sos-reports y el guardado de ubicaciones: no se
  almacenan telefonos ni coordenadas.
- Los niveles solo se muestran si el dato es en vivo y de las ultimas 48 h.
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request, Response, Query

logger = logging.getLogger("whatsapp_webhook")
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
GRAPH_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

HORAS_MAXIMAS_DATO_VIGENTE = 48

PIE_OFICIAL = "_Información de referencia. Alertas oficiales: Defensa Civil 103, SMN y Prefectura._"

EMERGENCIA_TEXTO = (
    "Este bot es *solo informativo*: no recibe pedidos de auxilio ni guarda tu ubicación.\n\n"
    "Si hay peligro, llamá ahora:\n"
    "• Defensa Civil: *103*\n"
    "• Bomberos: *100*\n"
    "• Prefectura Naval (emergencias en el agua): *106*\n"
    "• Emergencias médicas: *107*\n\n"
    "Cuando llames, tené a mano tu dirección o una referencia, cuántas personas son "
    "y cuánta agua hay."
)

EMOJI_POR_COLOR = {
    "verde": "🟢",
    "azul": "🔵",
    "amarillo": "🟡",
    "naranja": "🟠",
    "rojo": "🔴",
    "violeta": "🟣",
    "blanco": "⚪",
}


# ---------------------------------------------------------------------------
# 1) VERIFICACION DEL WEBHOOK (Meta llama a esto UNA vez al configurarlo)
# ---------------------------------------------------------------------------
@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if (
        VERIFY_TOKEN
        and hub_mode == "subscribe"
        and hmac.compare_digest(hub_verify_token or "", VERIFY_TOKEN)
    ):
        logger.info("Webhook de WhatsApp verificado correctamente")
        return Response(content=hub_challenge or "", media_type="text/plain")
    logger.warning("Verificacion de webhook fallo")
    return Response(content="Verification failed", status_code=403)


# ---------------------------------------------------------------------------
# 2) FIRMA: comprueba que el mensaje realmente lo mando Meta
# ---------------------------------------------------------------------------
def _firma_valida(cuerpo: bytes, firma: str | None) -> bool:
    if not APP_SECRET or not firma or not firma.startswith("sha256="):
        return False
    esperada = hmac.new(APP_SECRET.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma.split("=", 1)[1])


# ---------------------------------------------------------------------------
# 3) RECEPCION DE MENSAJES
# ---------------------------------------------------------------------------
@router.post("/webhook")
async def receive_message(request: Request):
    cuerpo = await request.body()
    if not _firma_valida(cuerpo, request.headers.get("X-Hub-Signature-256")):
        logger.warning("Mensaje de webhook rechazado: firma invalida o faltante")
        return Response(content="Invalid signature", status_code=403)

    try:
        body = json.loads(cuerpo)
        value = body["entry"][0]["changes"][0]["value"]

        if "messages" not in value:
            return {"status": "ignored"}  # ej. confirmaciones de "leido"

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message["type"]

        if msg_type == "text":
            await handle_text_message(from_number, message["text"]["body"].strip())
        elif msg_type == "location":
            await send_whatsapp_message(
                from_number,
                "No guardamos ubicaciones ni las enviamos a nadie.\n\n" + EMERGENCIA_TEXTO,
            )
        else:
            await send_whatsapp_message(
                from_number, "Por ahora solo puedo leer texto. Escribí *ayuda*."
            )

    except (KeyError, IndexError, ValueError) as e:
        logger.info(f"Payload sin mensaje procesable: {e}")

    return {"status": "received"}


# ---------------------------------------------------------------------------
# 4) FORMATEO
# ---------------------------------------------------------------------------
def _dato_en_vivo(registro: dict) -> bool:
    """True solo si el dato es medido (conectado) y de las ultimas 48 h."""
    if not registro.get("conectado"):
        return False
    texto = str(registro.get("ultima_verificacion") or "").replace(" UTC", "+00:00").replace(" ", "T")
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return False
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    horas = (datetime.now(timezone.utc) - fecha).total_seconds() / 3600
    return horas <= HORAS_MAXIMAS_DATO_VIGENTE


def _emoji(datos: dict) -> str:
    return EMOJI_POR_COLOR.get(datos.get("emoji"), "⚪")


def _formatear_localidad(datos: dict, nombre_cuenca: str) -> str:
    nombre = datos["nombre"]
    if not _dato_en_vivo(datos) or datos.get("nivel_metros") is None:
        ultima = datos.get("ultima_verificacion") or "sin registro"
        return (
            f"⚪ *{nombre}* (cuenca: {nombre_cuenca})\n"
            "Sin dato en vivo en este momento: no podemos informar el nivel actual.\n"
            f"Última verificación registrada: {ultima}\n"
            "Para información oficial consultá a Defensa Civil (103).\n\n"
            f"{PIE_OFICIAL}"
        )
    return (
        f"{_emoji(datos)} *{nombre}* (cuenca: {nombre_cuenca})\n"
        f"Nivel: {datos['nivel_metros']} m — Estado: {datos['estado']}\n"
        f"Umbral alerta: {datos['umbral_alerta']} m | evacuación: {datos['umbral_evacuacion']} m\n"
        f"Fuente: {datos['fuente']}\n"
        f"Última verificación: {datos['ultima_verificacion']}\n\n"
        f"{PIE_OFICIAL}"
    )


# ---------------------------------------------------------------------------
# 5) COMANDOS DE TEXTO
# ---------------------------------------------------------------------------
async def handle_text_message(from_number: str, text: str):
    # Import diferido para evitar import circular con main.py.
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
            "Hola! Soy el bot *informativo* del *Portal Hídrico Chaco*.\n\n"
            "Comandos:\n"
            "• *cuencas* — resumen de las cuencas\n"
            "• *nivel [localidad]* — ej: nivel barranqueras\n"
            "• *barrios [localidad]* — zonas vulnerables de esa localidad\n"
            "• *emergencia* — números para pedir ayuda\n\n"
            f"{PIE_OFICIAL}"
        )
        await send_whatsapp_message(from_number, respuesta)
        return

    if comando in ("emergencia", "sos"):
        await send_whatsapp_message(from_number, EMERGENCIA_TEXTO)
        return

    if comando == "cuencas":
        lineas = []
        for clave in CUENCAS:
            c = _cuenca_con_estado(clave)
            if _dato_en_vivo(c) and c.get("nivel_metros") is not None:
                lineas.append(f"{_emoji(c)} *{c['nombre']}*: {c['nivel_metros']} m ({c['estado']})")
            else:
                lineas.append(f"⚪ *{c['nombre']}*: sin dato en vivo")
        await send_whatsapp_message(
            from_number, "*Estado de las cuencas:*\n\n" + "\n".join(lineas) + f"\n\n{PIE_OFICIAL}"
        )
        return

    if comando.startswith("nivel "):
        clave = comando.replace("nivel ", "", 1).strip().replace(" ", "_")
        if clave not in localidades:
            await send_whatsapp_message(
                from_number,
                f"No encontré la localidad '{clave}'. Escribí *ayuda* para ver opciones.",
            )
            return
        loc = _localidad_con_estado(clave)
        cuenca_clave = loc.get("cuenca_clave") or ""
        nombre_cuenca = CUENCAS.get(cuenca_clave, {}).get("nombre", "sin río cercano (lluvia local)")
        await send_whatsapp_message(from_number, _formatear_localidad(loc, nombre_cuenca))
        return

    if comando.startswith("barrios"):
        clave = comando.replace("barrios", "", 1).strip().replace(" ", "_")
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
        marca = _emoji(padre) if _dato_en_vivo(padre) else "⚪"
        texto = f"📍 *Zonas vulnerables en {padre['nombre']}:*\n\n"
        texto += "\n\n".join(f"{marca} *{b['nombre']}*\n{b['motivo']}" for b in barrios)
        texto += f"\n\n{PIE_OFICIAL}"
        await send_whatsapp_message(from_number, texto)
        return

    await send_whatsapp_message(
        from_number, "No entendí ese mensaje. Escribí *ayuda* para ver los comandos disponibles."
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
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(GRAPH_API_URL, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.error(f"Error enviando mensaje WhatsApp: {resp.status_code}")
        return resp
