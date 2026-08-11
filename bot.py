import logging
import os
from dotenv import load_dotenv
load_dotenv()

import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TFG_BOT_TOKEN")

# El bot y el backend corren en el mismo contenedor de Render, asi que
# hablamos por localhost salvo que se indique otra cosa con BACKEND_URL.
PUERTO = os.environ.get("PORT", "10000")
BACKEND_URL = os.environ.get("BACKEND_URL", f"http://localhost:{PUERTO}")

CLAVES_CUENCAS = ["parana", "paraguay", "bermejo", "pilcomayo"]
CLAVES_CIUDADES = [
    "resistencia", "barranqueras", "corrientes", "formosa", "puerto_bermejo",
    "el_sauzalito", "isla_del_cerrito", "puerto_vilelas", "la_leonesa",
    "pampa_del_indio", "villa_rio_bermejito", "fuerte_esperanza",
]


def _get(path: str, timeout: float = 8.0):
    """GET al backend con manejo de errores simple, para no tirar abajo el bot."""
    try:
        r = requests.get(f"{BACKEND_URL}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.exception(f"Error consultando el backend en {path}")
        return None


def formatear_cuenca(datos: dict) -> str:
    aviso = "" if datos["conectado"] else "\n⚠️ <i>Dato de demostracion, sin conexion automatica aun.</i>"
    texto = (
        f"{datos['emoji']} <b>{datos['nombre']}</b> ({datos['estacion']})\n"
        f"Nivel: {datos['nivel_metros']} m — Estado: {datos['estado']}\n"
        f"Umbral alerta: {datos['umbral_alerta']} m | evacuacion: {datos['umbral_evacuacion']} m\n"
        f"Fuente: {datos['fuente']}\n"
        f"Ultima verificacion: {datos['ultima_verificacion']}"
        f"{aviso}"
    )
    return texto


def formatear_ciudad(datos: dict, nombre_cuenca: str) -> str:
    aviso = "" if datos["conectado"] else "\n⚠️ <i>Dato de demostracion, sin conexion automatica aun.</i>"
    return (
        f"{datos['emoji']} <b>{datos['nombre']}</b> (cuenca: {nombre_cuenca})\n"
        f"Nivel: {datos['nivel_metros']} m — Estado: {datos['estado']}\n"
        f"Umbral alerta: {datos['umbral_alerta']} m | evacuacion: {datos['umbral_evacuacion']} m\n"
        f"Fuente: {datos['fuente']}\n"
        f"Ultima verificacion: {datos['ultima_verificacion']}"
        f"{aviso}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "/cuencas - resumen de las 4 cuencas\n"
        "/parana /paraguay /bermejo /pilcomayo - detalle por cuenca\n\n"
        "<b>Por Localidad:</b>\n"
        "/resistencia - Resistencia\n"
        "/barranqueras - Barranqueras\n"
        "/corrientes - Corrientes capital\n"
        "/formosa - Formosa capital\n"
        "/puerto_bermejo - Puerto Bermejo\n"
        "/el_sauzalito - El Sauzalito\n"
        "/isla_del_cerrito - Isla del Cerrito\n"
        "/puerto_vilelas - Puerto Vilelas\n"
        "/la_leonesa - La Leonesa\n"
        "/pampa_del_indio - Pampa del Indio\n"
        "/villa_rio_bermejito - Villa Rio Bermejito\n"
        "/fuerte_esperanza - Fuerte Esperanza"
    )
    await update.message.reply_text(texto, parse_mode='HTML')


async def cuencas_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    datos = _get("/cuencas")
    if not datos:
        await update.message.reply_text("No pude consultar el backend, probá de nuevo en unos segundos.")
        return
    lineas = [
        f"{c['emoji']} <b>{c['nombre']}</b>: {c['nivel_metros']} m ({c['estado']})"
        for c in datos["cuencas"].values()
    ]
    await update.message.reply_text(
        "<b>Estado de las 4 cuencas:</b>\n\n" + "\n".join(lineas),
        parse_mode='HTML'
    )


def hacer_handler_cuenca(clave: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        datos = _get(f"/cuencas/{clave}")
        if not datos or "cuenca" not in datos:
            await update.message.reply_text("No pude consultar el backend, probá de nuevo en unos segundos.")
            return
        texto = formatear_cuenca(datos["cuenca"])
        if datos["localidades"]:
            texto += "\n\n📍 <b>Localidades monitoreadas en esta cuenca:</b>"
            for c in datos["localidades"]:
                texto += f"\n{c['emoji']} {c['nombre']}: {c['nivel_metros']} m ({c['estado']})"
        await update.message.reply_text(texto, parse_mode='HTML')
    return handler


def hacer_handler_ciudad(clave: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        datos = _get(f"/localidades/{clave}")
        if not datos or "localidad" not in datos:
            await update.message.reply_text("No pude consultar el backend, probá de nuevo en unos segundos.")
            return
        loc = datos["localidad"]
        cuenca_info = _get(f"/cuencas/{loc['cuenca_clave']}")
        nombre_cuenca = cuenca_info["cuenca"]["nombre"] if cuenca_info else loc["cuenca_clave"]
        await update.message.reply_text(formatear_ciudad(loc, nombre_cuenca), parse_mode='HTML')
    return handler


# ---------------------------------------------------------------------
# AGREGAR a bot.py
# ---------------------------------------------------------------------

def formatear_barrio(datos: dict) -> str:
    return (
        f"{datos['emoji']} <b>{datos['nombre']}</b>\n"
        f"{datos['motivo']}\n"
        f"<i>Ubicación: {datos['precision']}</i>"
    )


async def barrios_vulnerables(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /barrios: lista todos los barrios vulnerables conocidos."""
    datos = _get("/barrios")
    if not datos or "barrios" not in datos or not datos["barrios"]:
        await update.message.reply_text("No pude consultar el backend, probá de nuevo en unos segundos.")
        return
    texto = "<b>📍 Barrios y zonas históricamente más vulnerables:</b>\n\n"
    texto += "\n\n".join(formatear_barrio(b) for b in datos["barrios"].values())
    texto += "\n\n<i>Basado en investigación histórica (crecidas de 1982, 1998, 2014, 2023), no es un registro oficial completo.</i>"
    await update.message.reply_text(texto, parse_mode='HTML')


# En hacer_handler_ciudad(), agregar despues de mostrar la localidad,
# para que cada comando de localidad tambien muestre sus barrios:
#
#   barrios_data = _get(f"/barrios/{clave}")
#   if barrios_data and barrios_data.get("barrios"):
#       texto_extra = "\n\n📍 <b>Zonas vulnerables en esta localidad:</b>"
#       for b in barrios_data["barrios"].values():
#           texto_extra += f"\n{b['emoji']} {b['nombre']}"
#       await update.message.reply_text(texto_extra, parse_mode='HTML')

# En main(), agregar junto a los otros add_handler:
#   app.add_handler(CommandHandler("barrios", barrios_vulnerables))

# En start(), agregar a la lista de comandos:
#   "/barrios - zonas históricamente más vulnerables\n"
def main():
    if not TOKEN:
        raise RuntimeError(
            "Falta la variable de entorno TFG_BOT_TOKEN. "
            "Configurala local o en Render, nunca la escribas en el codigo."
        )

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cuencas", cuencas_resumen))
    for clave in CLAVES_CUENCAS:
        app.add_handler(CommandHandler(clave, hacer_handler_cuenca(clave)))
    for clave in CLAVES_CIUDADES:
        app.add_handler(CommandHandler(clave, hacer_handler_ciudad(clave)))

    logger.info(f"Bot iniciado, consultando backend en {BACKEND_URL}, esperando mensajes (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
