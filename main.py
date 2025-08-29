# -----------------------------------------------------------------------------
# BOT DE GASTOS PARA TELEGRAM (VERSIÓN CORREGIDA PARA VERCELL)
#
# Corrección:
# 1.  Se reestructura el final del código para exponer una variable `app`.
#     Vercel busca esta variable para manejar las peticiones web.
# 2.  Se adapta la inicialización para que funcione en un entorno "serverless",
#     donde el bot se inicia y se apaga con cada mensaje.
# -----------------------------------------------------------------------------

import logging
import os
import gspread
import json
import asyncio
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# --- Configuración Inicial ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')

# --- Conexión a Google Sheets ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

def conectar_a_sheets():
    try:
        if GOOGLE_CREDENTIALS_JSON:
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
            client = gspread.authorize(creds)
            sheet = client.open("Mis Gastos Personales").sheet1
            return sheet
        logger.error("Variable de entorno GOOGLE_CREDENTIALS_JSON no encontrada.")
        return None
    except Exception as e:
        logger.error(f"Error al conectar con Google Sheets: {e}")
        return None

def guardar_gasto_en_sheets(user_id, categoria, monto, descripcion):
    sheet = conectar_a_sheets()
    if sheet:
        try:
            now = datetime.now()
            fila = [
                str(user_id),
                now.strftime('%Y-%m-%d %H:%M:%S'),
                now.strftime('%Y-%m-%d'),
                monto,
                categoria.capitalize(),
                descripcion
            ]
            sheet.append_row(fila)
            logger.info("Fila añadida a Google Sheets exitosamente.")
            return True
        except Exception as e:
            logger.error(f"No se pudo escribir en Google Sheets: {e}")
            return False
    return False

CATEGORIAS = {
    'alimentacion': '🥦 Alimentación',
    'vivienda': '🏠 Vivienda',
    'transporte': '🚗 Transporte',
    'salud': '🏥 Salud',
    'entretenimiento': '🎮 Entretenimiento',
    'ropa': '👕 Ropa',
    'otros': '📝 Otros'
}

# --- Funciones del Bot (Handlers) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    mensaje = (
        f"¡Hola, {user_name}! 👋\n\n"
        "Soy tu asistente de gastos personal.\n\n"
        "Para registrar un nuevo gasto, simplemente usa el comando /gasto."
    )
    await update.message.reply_text(mensaje)

async def nuevo_gasto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # (El código de esta función y las siguientes no cambia, se omite por brevedad)
    # ... (pega aquí el resto de las funciones: nuevo_gasto, seleccionar_categoria, etc.)
    # ...
    # ¡Asegúrate de copiar el resto de las funciones del bot del código anterior!
    # Por ejemplo:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = []
    row = []
    for key, value in CATEGORIAS.items():
        row.append(InlineKeyboardButton(value, callback_data=f'categoria_{key}'))
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
    categoria_seleccionada = query.data.split('_')[1]
    context.user_data['categoria'] = categoria_seleccionada
    await query.edit_message_text(
        text=f"Categoría: {CATEGORIAS[categoria_seleccionada]}\n\n"
             "Ahora, envía el monto y la descripción.\n\n"
             "👉 **Formato:** `monto descripción`\n"
             "👉 **Ejemplo:** `35.50 Almuerzo con amigos`"
    )

async def procesar_mensaje_gasto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'categoria' not in context.user_data:
        await update.message.reply_text("Por favor, inicia con /gasto para seleccionar una categoría.")
        return

    try:
        texto_mensaje = update.message.text
        partes = texto_mensaje.split(' ', 1)
        monto = float(partes[0].replace(',', '.'))
        descripcion = partes[1] if len(partes) > 1 else "Sin descripción"
        categoria = context.user_data['categoria']
        user_id = update.effective_user.id
        
        exito = guardar_gasto_en_sheets(user_id, categoria, monto, descripcion)
        
        if exito:
            respuesta = (
                "✅ ¡Gasto registrado con éxito!\n\n"
                f"**Categoría:** {CATEGORIAS[categoria]}\n"
                f"**Monto:** {monto}\n"
                f"**Descripción:** {descripcion}"
            )
        else:
            respuesta = "❌ Hubo un error al guardar el gasto. Revisa los logs de Vercel."
            
        await update.message.reply_text(respuesta)
        context.user_data.clear()

    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ **Error de formato.**\n\n"
            "Usa el formato: `monto descripción`\n"
            "Ejemplo: `120 Pasajes de micro`"
        )


# --- Punto de Entrada para Vercel ---
# Vercel necesita una variable 'app' que pueda manejar las peticiones web.
# Creamos la aplicación de Telegram aquí.
application = Application.builder().token(TOKEN).build()

# Añadimos los manejadores de comandos y mensajes
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("gasto", nuevo_gasto))
application.add_handler(CallbackQueryHandler(seleccionar_categoria, pattern='^categoria_'))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje_gasto))

# Esta es la función principal que Vercel ejecutará
async def app(request):
    """Maneja las peticiones webhook de Telegram."""
    # Vercel pasa la petición web como un objeto. Necesitamos el cuerpo (body).
    body = await request.json()
    update = Update.de_json(body, application.bot)
    await application.process_update(update)
    # Devolvemos una respuesta vacía para decirle a Telegram "OK, recibido".
    return ('', 204)
