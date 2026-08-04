import logging
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from datos_cuencas import CUENCAS, obtener_estado, resumen_todas

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


def formatear_cuenca(datos: dict) -> str:
    aviso = "" if datos["conectado"] else "\n⚠️ _Dato de demostración, sin conexión automática aún._"
    return (
        f"{datos['emoji']} *{datos['nombre']}* ({datos['estacion']})\n"
        f"Nivel: {datos['nivel_metros']} m — Estado: {datos['estado']}\n"
        f"Umbral alerta: {datos['umbral_alerta']} m | evacuación: {datos['umbral_evacuacion']} m\n"
        f"Fuente: {datos['fuente_datos']}\n"
        f"Última verificación: {datos['ultima_verificacion']}"
        f"{aviso}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🌊 *Portal Hídrico Chaco - Bot*\n\n"
        "Monitoreo de 4 cuencas: Paraná, Paraguay, Bermejo y Pilcomayo.\n\n"
        "Comandos:\n"
        "/cuencas - resumen de las 4\n"
        "/parana - detalle Río Paraná\n"
        "/paraguay - detalle Río Paraguay\n"
        "/bermejo - detalle Río Bermejo\n"
        "/pilcomayo - detalle Río Pilcomayo"
    )
    await update.message.reply_markdown(texto)


async def cuencas_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lineas = [
        f"{c['emoji']} {c['nombre']}: {c['nivel_metros']} m ({c['estado']})"
        for c in resumen_todas()
    ]
    await update.message.reply_text("📊 Estado de las 4 cuencas:\n\n" + "\n".join(lineas))


def hacer_handler_cuenca(clave: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        datos = obtener_estado(clave)
        await update.message.reply_markdown(formatear_cuenca(datos))
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

    logger.info("Bot iniciado, esperando mensajes (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()