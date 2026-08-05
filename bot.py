import logging
import os
from dotenv import load_dotenv
load_dotenv()


from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from datos_cuencas import (
    CUENCAS,
    CIUDADES,
    obtener_estado,
    obtener_estado_ciudad,
    ciudades_de_cuenca,
    resumen_todas,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TFG_BOT_TOKEN")



def formatear_cuenca(clave_cuenca: str, datos: dict) -> str:
    aviso = "" if datos["conectado"] else "\n⚠️ _Dato de demostración, sin conexión automática aún._"
    texto = (
        f"{datos['emoji']} *{datos['nombre']}* ({datos['estacion']})\n"
        f"Nivel: {datos['nivel_metros']} m — Estado: {datos['estado']}\n"
        f"Umbral alerta: {datos['umbral_alerta']} m | evacuación: {datos['umbral_evacuacion']} m\n"
        f"Fuente: {datos['fuente_datos']}\n"
        f"Última verificación: {datos['ultima_verificacion']}"
        f"{aviso}"
    )
    ciudades = ciudades_de_cuenca(clave_cuenca)
    if ciudades:
        texto += "\n\n📍 *Localidades monitoreadas en esta cuenca:*"
        for c in ciudades:
            texto += f"\n{c['emoji']} {c['nombre']}: {c['nivel_metros']} m ({c['estado']})"
    return texto


def formatear_ciudad(datos: dict) -> str:
    aviso = "" if datos["conectado"] else "\n⚠️ _Dato de demostración, sin conexión automática aún._"
    return (
        f"{datos['emoji']} *{datos['nombre']}* (cuenca: {CUENCAS[datos['cuenca']]['nombre']})\n"
        f"Nivel: {datos['nivel_metros']} m — Estado: {datos['estado']}\n"
        f"Umbral alerta: {datos['umbral_alerta']} m | evacuación: {datos['umbral_evacuacion']} m\n"
        f"Fuente: {datos['fuente_datos']}\n"
        f"Última verificación: {datos['ultima_verificacion']}"
        f"{aviso}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = (
        "/pilcomayo - detalle Río Pilcomayo\n\n"
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
        "/villa_rio_bermejito - Villa Río Bermejito\n"
        "/fuerte_esperanza - Fuerte Esperanza"
    )
    # Cambiamos reply_markdown por reply_text con parse_mode='HTML'
    await update.message.reply_text(texto, parse_mode='HTML')


async def cuencas_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Quitamos los asteriscos y corchetes conflictivos de Markdown
    lineas = [
        f"{i['emoji']} <b>{i['nombre']}</b>: {i['nivel_metros']} m ({i['estado']})"
        for i in resumen_todas()
    ]
    # Cambiamos reply_text normal por uno con soporte HTML
    await update.message.reply_text(
        "<b>Estado de las 4 cuencas:</b>\n\n" + "\n".join(lineas),
        parse_mode='HTML'
    )


def hacer_handler_cuenca(clave: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        datos = obtener_estado(clave)
        # Cambiamos reply_markdown por reply_text con soporte HTML
        await update.message.reply_text(formatear_cuenca(clave, datos), parse_mode='HTML')
    return handler

def hacer_handler_ciudad(clave: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        datos = obtener_estado_ciudad(clave)
        await update.message.reply_markdown(formatear_ciudad(datos))
    return handler


def main():
    if not TOKEN:
        raise RuntimeError(
            "Falta la variable de entorno TELEGRAM_BOT_TOKEN. "
            "Configurala local o en Render, nunca la escribas en el código."
        )

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cuencas", cuencas_resumen))
    for clave in CUENCAS:
        app.add_handler(CommandHandler(clave, hacer_handler_cuenca(clave)))
    for clave in CIUDADES:
        app.add_handler(CommandHandler(clave, hacer_handler_ciudad(clave)))

    logger.info("Bot iniciado, esperando mensajes (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
