# api/index.py
import logging
import os
import json
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- Log ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("gastos-bot")

# --- ENV ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

if not TOKEN:
    logger.error("Falta TELEGRAM_TOKEN en variables de entorno.")

# --- Google Sheets ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]

def conectar_a_sheets():
    try:
        if not GOOGLE_CREDENTIALS_JSON:
            logger.error("GOOGLE_CREDENTIALS_JSON no configurado.")
            return None
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        # Asegúrate de compartir esta hoja con el email del service account
        sheet = client.open("Mis Gastos Personales").sheet1
        return sheet
    except Exception as e:
        logger.error(f"Error al conectar con Google Sheets: {e}")
        return None

def guardar_gasto_en_sheets(user_id, categoria, monto, descripcion):
    sheet = conectar_a_sheets()
    if not sheet:
        return False
    try:
        now = datetime.now()
        fila = [
            str(user_id),
            now.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d"),
            float(monto),
            categoria.capitalize(),
            descripcion,
        ]
        sheet.append_row(fila)
        logger.info("Fila añadida a Google Sheets exitosamente.")
        return True
    except Exception as e:
        logger.error(f"No se pudo escribir en Google Sheets: {e}")
        return False

CATEGORIAS = {
    "alimentacion": "🥦 Alimentación",
    "vivienda": "🏠 Vivienda",
    "transporte": "🚗 Transporte",
    "salud": "🏥 Salud",
    "entretenimiento": "🎮 Entretenimiento",
    "ropa": "👕 Ropa",
    "otros": "📝 Otros",
}

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name or "allí"
    mensaje = (
        f"¡Hola, {user_name}! 👋\n\n"
        "Soy tu asistente de gastos personal.\n\n"
        "Usa /gasto para registrar un nuevo gasto."
    )
    await update.message.reply_text(mensaje)

async def nuevo_gasto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = []
    row = []
    for key, value in CATEGORIAS.items():
        row.append(InlineKeyboardButton(value, callback_data=f"categoria_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛒 Por favor, selecciona una categoría:", reply_markup=reply_markup)

async def seleccionar_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    categoria_seleccionada = query.data.split("_", 1)[1]
    context.user_data["categoria"] = categoria_seleccionada
    texto = (
        f"Categoría: {CATEGORIAS[categoria_seleccionada]}\n\n"
        "Ahora, envía el monto y la descripción.\n\n"
        "👉 Formato: monto descripción\n"
        "👉 Ejemplo: 35.50 Almuerzo con amigos"
    )
    await query.edit_message_text(text=texto)

async def procesar_mensaje_gasto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "categoria" not in context.user_data:
        await update.message.reply_text("Por favor, inicia con /gasto para seleccionar una categoría.")
        return
    try:
        texto_mensaje = update.message.text.strip()
        partes = texto_mensaje.split(" ", 1)
        monto = float(partes[0].replace(",", "."))
        descripcion = partes[1] if len(partes) > 1 else "Sin descripción"
        categoria = context.user_data["categoria"]
        user_id = update.effective_user.id

        exito = guardar_gasto_en_sheets(user_id, categoria, monto, descripcion)

        if exito:
            respuesta = (
                "✅ ¡Gasto registrado con éxito!\n\n"
                f"Categoría: {CATEGORIAS[categoria]}\n"
                f"Monto: {monto}\n"
                f"Descripción: {descripcion}"
            )
        else:
            respuesta = "❌ Hubo un error al guardar el gasto. Revisa los logs de Vercel."
        await update.message.reply_text(respuesta)
        context.user_data.clear()

    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Error de formato.\n\n"
            "Usa el formato: monto descripción\n"
            "Ejemplo: 120 Pasajes de micro"
        )

# --- Telegram Application ---
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("gasto", nuevo_gasto))
application.add_handler(CallbackQueryHandler(seleccionar_categoria, pattern=r"^categoria_"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje_gasto))

# --- FastAPI App (lo que Vercel exporta) ---
app = FastAPI()

@app.get("/")
async def health():
    return {"ok": True}

@app.post("/")
async def telegram_webhook(request: Request):
    """
    Endpoint para webhook de Telegram.
    En entorno serverless iniciamos y apagamos la app en cada request.
    """
    try:
        body = await request.json()
    except Exception:
        # Si Telegram envía algo que no es JSON
        return Response(status_code=400)

    try:
        update = Update.de_json(body, application.bot)
        # Ciclo recomendado en modo manual/serverless:
        await application.initialize()
        await application.start()
        await application.process_update(update)
        await application.stop()
        await application.shutdown()
        return Response(status_code=204)
    except Exception as e:
        logger.exception(f"Error procesando update: {e}")
        return Response(status_code=500)

