"""
alertas_dispatcher.py
----------------------
Portal Hidrico Chaco - Despachador de alertas tempranas.

Conecta lo que YA EXISTIA pero no estaba unido:
  - motor_decision.py    -> decide la FASE (Normal/Monitoreo/Atencion/
                             Alerta/Evacuacion) y redacta el mensaje para
                             vecinos y para Defensa Civil, por separado.
  - whatsapp_webhook.py  -> ya sabe mandar un mensaje de WhatsApp 1 a 1
                             (send_whatsapp_message).
  - bot.py (Telegram)    -> ya tiene el TOKEN, pero corre como bot de
                             consulta (responde comandos), no como
                             despachador de avisos.

Este script se corre PERIODICAMENTE (ver mas abajo "COMO PROGRAMARLO"),
compara la fase de cada localidad contra la ULTIMA fase que ya se
avisó, y si cambió, dispara los mensajes correspondientes.

POR QUE COMPARAR CONTRA LA ULTIMA FASE (y no mandar siempre que corre):
Si esto corriera cada 10 minutos y mandara el mensaje cada vez, en una
crecida larga (dias) se manda el mismo aviso "ALERTA" cientos de veces
- la gente deja de leerlos (fatiga de alerta) y es spam para Meta/
Telegram. Por eso se guarda la ULTIMA fase avisada por localidad y solo
se dispara en un CAMBIO de fase.

CANALES, Y POR QUE CADA UNO FUNCIONA DISTINTO (esto es importante,
léelo antes de armar los grupos):

  1) TELEGRAM (recomendado para avisos públicos)
     Los canales de Telegram (no grupos) son de difusión: cualquiera
     se suscribe UNA vez y el bot puede postear cuando quiera, sin
     restricciones. Es el mas simple de los tres para avisos masivos.
     Necesitas crear un canal, agregar el bot como administrador, y
     poner su ID (empieza con "-100...") en TELEGRAM_CANAL_PUBLICO_ID.

  2) WHATSAPP - dos mecanismos MUY distintos, no confundir:
     a) WhatsApp Business API (Meta) - la que ya tienen conectada en
        whatsapp_webhook.py - es para conversaciones 1 a 1. Por
        politica de Meta, NO se puede mandar un mensaje de texto libre
        a alguien que no te escribio en las ultimas 24hs, salvo que
        uses una "plantilla" (template) pre-aprobada por Meta. Sirve
        perfecto para el aviso a Defensa Civil/Bomberos (son pocos
        numeros, conocidos, que ya interactuan con el bot), pero NO
        sirve para "avisar a todo el barrio" sin que ellos hayan
        escrito primero.
     b) WhatsApp Channels (Canales) - es la funcion nueva de Meta,
        pensada exactamente para esto: difusion uno-a-muchos, sin el
        limite de 24hs, la gente se suscribe una vez. Se crea desde la
        app de WhatsApp Business, no requiere token de Meta for
        Developers. Es el equivalente de WhatsApp a un canal de
        Telegram - ESTE es el que hay que usar para avisar a vecinos,
        no la Business API.

  3) GOOGLE / Firebase Cloud Messaging (FCM) - notificaciones push
     directo al navegador/celu de quien tenga el sitio abierto o
     instalado como PWA, sin necesitar numero de telefono. Firebase ya
     esta importado en el frontend (src/lib/firebase.ts) pero no se
     usa todavia. Requiere: activar Cloud Messaging en la consola de
     Firebase, un service worker en el frontend para recibir el push,
     guardar el "token" de cada dispositivo que acepta notificaciones,
     y mandar desde el backend con el SDK de administracion de
     Firebase. Es mas trabajo que Telegram/WhatsApp Channels, pero
     llega a cualquiera que visito el sitio, sin necesidad de
     instalar nada aparte. Recomendado como TERCER canal, no el primero.

PERSISTENCIA DEL ESTADO (evitar reenviar la misma alerta):
Si Supabase esta configurado (mismo que ya usan para sos_tickets y
reportes_ciudadanos), se guarda ahi en una tabla nueva
"estado_fases_localidad" (id_localidad, fase, timestamp). Si no,
cae a un archivo JSON local (estado_fases.json) - funciona igual en
una corrida sola, pero se pierde si Render reinicia el proceso (por
eso se recomienda Supabase para este dato en produccion).

COMO PROGRAMARLO (elegir uno):
  - GitHub Actions (igual patron que actualizar_niveles.py /
    actualizar_vertederos.py que ya tienen): un workflow que corre
    cada 10-15 minutos y ejecuta este script con
    `python alertas_dispatcher.py`.
  - APScheduler dentro del mismo proceso de FastAPI (agregar un
    @app.on_event("startup") que dispare un loop cada N minutos). Mas
    simple de mantener en un solo lugar (Render), pero si Render
    reinicia el servicio (deploys, sleep en el plan free) se corta el
    loop hasta el proximo request - por eso GitHub Actions es mas
    confiable para esto en particular.

VARIABLES DE ENTORNO NUEVAS A CONFIGURAR:
    TFG_BOT_TOKEN                  (ya la tienen, se reusa)
    TELEGRAM_CANAL_PUBLICO_ID      -> ID del canal de Telegram publico
    TELEGRAM_GRUPO_DEFENSA_CIVIL_ID -> ID del grupo interno de Defensa Civil
    WHATSAPP_NUMEROS_DEFENSA_CIVIL -> numeros separados por coma, ej:
                                       "5493624000001,5493624000002"
                                       (Defensa Civil/Bomberos - via
                                       WhatsApp Business API, la que ya
                                       tienen conectada)
    BACKEND_URL                    (ya la tienen)
"""

import os
import json
import logging
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alertas_dispatcher")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:10000")
TFG_BOT_TOKEN = os.environ.get("TFG_BOT_TOKEN", "")
TELEGRAM_CANAL_PUBLICO_ID = os.environ.get("TELEGRAM_CANAL_PUBLICO_ID", "")
TELEGRAM_GRUPO_DEFENSA_CIVIL_ID = os.environ.get("TELEGRAM_GRUPO_DEFENSA_CIVIL_ID", "")
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
# IMPORTANTE: la FASE se toma del campo "estado" que ya devuelve
# /localidades (calculado por calcular_estado() en main.py) - la MISMA
# funcion que pinta las tarjetas de la web. A proposito NO se usa
# motor_decision.py/determinar_fase() aca: ese modulo calcula la fase
# con un criterio distinto (proyeccion de tendencia en vez de % del
# umbral) y en la practica puede dar una fase diferente para el mismo
# dato - por ejemplo, hoy Bermejo (3.31m) da MONITOREO en la web pero
# NORMAL con el motor de tendencia. Mandar una alerta con una fase que
# no coincide con lo que la persona ve en la web genera confusion justo
# en el peor momento. Si en el futuro quieren sumar la proyeccion de
# tendencia (es una mejora real, avisa CON mas anticipacion), lo
# correcto es integrarla DENTRO de calcular_estado() en main.py para
# que siga habiendo una sola fuente de verdad - no como un calculo
# paralelo separado.
#
# El texto de estos mensajes esta basado en el que ya habian redactado
# en motor_decision.py (_fase_atencion, _fase_alerta, etc.), reusando
# ese trabajo pero atado a la fase autoritativa de la web.
# ---------------------------------------------------------------------
def _mensajes_por_fase(fase: str, loc: dict) -> dict:
    nombre = loc["nombre"]
    nivel = loc["nivel_metros"]
    umbral_alerta = loc["umbral_alerta"]
    umbral_evacuacion = loc["umbral_evacuacion"]

    if fase == "NORMAL":
        return {
            "mostrar_a_vecinos": True,
            "mensaje_vecino": f"El río en {nombre} está en su nivel normal ({nivel:.2f} m). No hay riesgo por ahora.",
            "mensaje_tecnico": f"Nivel actual {nivel:.2f} m, dentro de rango normal. Sin acción requerida.",
        }
    if fase == "MONITOREO":
        return {
            "mostrar_a_vecinos": False,  # a proposito: no se avisa al vecino todavia
            "mensaje_vecino": None,
            "mensaje_tecnico": (
                f"[SOLO PERSONAL] {nombre}: nivel {nivel:.2f} m (por encima del 70% del "
                f"umbral de alerta de {umbral_alerta:.2f} m). Empezar a seguir de cerca."
            ),
        }
    if fase == "ATENCION":
        return {
            "mostrar_a_vecinos": True,
            "mensaje_vecino": (
                f"El río en {nombre} está subiendo ({nivel:.2f} m, cerca del umbral de alerta "
                f"de {umbral_alerta:.2f} m). Todavía no hay riesgo, pero es buen momento para "
                f"revisar lo esencial (documentos, medicamentos) y estar atento a próximos avisos."
            ),
            "mensaje_tecnico": (
                f"[DEFENSA CIVIL / BOMBEROS] {nombre}: nivel {nivel:.2f} m, acercándose al "
                f"umbral de alerta ({umbral_alerta:.2f} m). Recomendado iniciar preparativos."
            ),
        }
    if fase == "ALERTA":
        return {
            "mostrar_a_vecinos": True,
            "mensaje_vecino": (
                f"⚠️ El río en {nombre} superó el nivel de alerta ({umbral_alerta:.2f} m), "
                f"ahora en {nivel:.2f} m. Prestá atención a los avisos de Defensa Civil y "
                f"tené preparado lo esencial para vos, tu familia y tus mascotas."
            ),
            "mensaje_tecnico": (
                f"[ALERTA ACTIVA] {nombre}: nivel {nivel:.2f} m, superó umbral de alerta "
                f"({umbral_alerta:.2f} m). Faltan {umbral_evacuacion - nivel:.2f} m para evacuación."
            ),
        }
    if fase == "EVACUACION":
        return {
            "mostrar_a_vecinos": True,
            "mensaje_vecino": (
                f"🔴 El río en {nombre} superó el nivel de evacuación ({umbral_evacuacion:.2f} m), "
                f"ahora en {nivel:.2f} m. Seguí las indicaciones de Defensa Civil y Bomberos de tu "
                f"zona. Priorizá tu seguridad y la de tu familia y mascotas."
            ),
            "mensaje_tecnico": (
                f"[EVACUACIÓN ACTIVA] {nombre}: nivel {nivel:.2f} m, superó umbral de evacuación "
                f"({umbral_evacuacion:.2f} m). Activar protocolo con barrios vulnerables de la zona."
            ),
        }
    # SIN_DATO no debería llegar aca (se filtra antes), pero por las dudas:
    return {"mostrar_a_vecinos": False, "mensaje_vecino": None, "mensaje_tecnico": f"{nombre}: sin dato."}



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
    # Fallback a archivo local (no persiste entre reinicios de Render,
    # pero sirve para pruebas locales y como respaldo).
    estado = {}
    if ESTADO_LOCAL_PATH.exists():
        estado = json.loads(ESTADO_LOCAL_PATH.read_text(encoding="utf-8"))
    estado[clave] = fase
    ESTADO_LOCAL_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------
# ENVIO - Telegram (canal publico + grupo Defensa Civil)
# ---------------------------------------------------------------------
async def enviar_telegram(chat_id: str, texto: str):
    if not TFG_BOT_TOKEN or not chat_id:
        logger.warning("Falta TFG_BOT_TOKEN o chat_id, no se manda por Telegram.")
        return
    url = f"https://api.telegram.org/bot{TFG_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"chat_id": chat_id, "text": texto})
        if resp.status_code >= 400:
            logger.error(f"Error Telegram: {resp.status_code} {resp.text}")


# ---------------------------------------------------------------------
# ENVIO - WhatsApp (solo Defensa Civil/Bomberos - ver nota de arriba
# sobre por que NO se usa para avisos masivos a vecinos)
# ---------------------------------------------------------------------
async def enviar_whatsapp_defensa_civil(texto: str):
    if not WHATSAPP_NUMEROS_DEFENSA_CIVIL:
        logger.warning("WHATSAPP_NUMEROS_DEFENSA_CIVIL vacio, no se manda por WhatsApp.")
        return
    # Import local para no obligar a tener whatsapp_webhook.py cuando
    # este script corre standalone (ej. en un runner de GitHub Actions
    # separado del backend).
    from whatsapp_webhook import send_whatsapp_message
    for numero in WHATSAPP_NUMEROS_DEFENSA_CIVIL:
        await send_whatsapp_message(numero, texto)


# ---------------------------------------------------------------------
# LOOP PRINCIPAL
# ---------------------------------------------------------------------
async def revisar_y_despachar():
    estado_previo = cargar_estado_previo()

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BACKEND_URL}/localidades", timeout=15)
        localidades = resp.json()["localidades"]

        for clave, loc in localidades.items():
            fase_nueva = loc["estado"]  # ya calculada por main.py, misma que ve la web
            if fase_nueva == "SIN_DATO":
                continue  # sin estacion (fluvial sin cobertura, o pluvial) - no aplica este motor

            fase_anterior = estado_previo.get(clave)
            if fase_nueva == fase_anterior:
                continue  # sin cambios, no se manda nada (evita spam)

            logger.info(f"{clave}: {fase_anterior} -> {fase_nueva}")

            resultado = _mensajes_por_fase(fase_nueva, loc)

            # Mensaje tecnico: SIEMPRE a Defensa Civil (Telegram + WhatsApp)
            texto_tecnico = f"[{loc['nombre']}] {resultado['mensaje_tecnico']}"
            await enviar_telegram(TELEGRAM_GRUPO_DEFENSA_CIVIL_ID, texto_tecnico)
            await enviar_whatsapp_defensa_civil(texto_tecnico)

            # Mensaje a vecinos: SOLO si corresponde mostrarlo (Monitoreo
            # se guarda solo para uso tecnico interno, no genera alarma
            # publica por una tendencia que todavia puede no confirmarse)
            if resultado["mostrar_a_vecinos"] and resultado["mensaje_vecino"]:
                texto_vecino = f"📍 {loc['nombre']}\n\n{resultado['mensaje_vecino']}"
                await enviar_telegram(TELEGRAM_CANAL_PUBLICO_ID, texto_vecino)
                # WhatsApp a vecinos: NO via Business API (ver nota arriba) -
                # correspondería mandarlo por un WhatsApp Channel, que se
                # publica desde la app de WhatsApp Business directamente,
                # no desde este script.

            guardar_fase(clave, fase_nueva)


if __name__ == "__main__":
    import asyncio
    asyncio.run(revisar_y_despachar())
