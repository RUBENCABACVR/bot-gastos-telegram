# -----------------------------------------------------------------------------
# BOT DE GASTOS PARA TELEGRAM (VERSIÓN FINAL PARA VERCELL)
#
# Funcionalidad:
# 1.  Se conecta a Telegram.
# 2.  Permite registrar gastos mediante un menú de botones.
# 3.  Se conecta de forma segura a Google Sheets usando una Cuenta de Servicio.
# 4.  Guarda cada gasto en una nueva fila en la hoja de cálculo.
# -----------------------------------------------------------------------------

import logging
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# --- Configuración Inicial ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Tu token de Telegram (lo leeremos de las variables de entorno de Vercel)
TOKEN = os.environ.get('TELEGRAM_TOKEN', 'TU_TOKEN_DE_TELEGRAM')

# --- Conexión a Google Sheets ---
# Define los "scopes" o permisos que necesita nuestro bot
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# Vercel no puede leer un archivo JSON directamente de la forma tradicional.
# En su lugar, copiaremos el contenido del archivo JSON a una variable de entorno.
# Aquí, intentamos leer esa variable de entorno.
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')

# Función para autorizar y conectarse a Google Sheets
def conectar_a_sheets():
    """Se conecta a la API de Google Sheets usando las credenciales."""
    try:
        if GOOGLE_CREDENTIALS_JSON:
            import json
            # Carga las credenciales desde la variable de entorno
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            # Si no está en Vercel, busca el archivo localmente (para pruebas)
            creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", SCOPE)
        
        client = gspread.authorize(creds)
        # Abre la hoja de cálculo por su nombre y selecciona la primera hoja
        sheet = client.open("Mis Gastos Personales").sheet1
        return sheet
    except Exception as e:
        logger.error(f"Error al conectar con Google Sheets: {e}")
        return None

def guardar_gasto_en_sheets(user_id, categoria, monto, descripcion):
    """Añade una nueva fila a la hoja de cálculo con los datos del gasto."""
    sheet = conectar_a_sheets()
    if sheet:
        try:
            now = datetime.now()
            # Formatea los datos para la nueva fila
            fila = [
                str(user_id),
                now.strftime('%Y-%m-%d %H:%M:%S'), # Timestamp
                now.strftime('%Y-%m-%d'), # Fecha
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

# Categorías de gastos con emojis
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
        
        # --- ¡AQUÍ OCURRE LA MAGIA! ---
        # Llamamos a la función para guardar los datos en la hoja de cálculo
        exito = guardar_gasto_en_sheets(user_id, categoria, monto, descripcion)
        
        if exito:
            respuesta = (
                "✅ ¡Gasto registrado con éxito!\n\n"
                f"**Categoría:** {CATEGORIAS[categoria]}\n"
                f"**Monto:** {monto}\n"
                f"**Descripción:** {descripcion}"
            )
        else:
            respuesta = "❌ Hubo un error al intentar guardar el gasto en la base de datos. Por favor, intenta de nuevo."
            
        await update.message.reply_text(respuesta)
        context.user_data.clear()

    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ **Error de formato.**\n\n"
            "Usa el formato: `monto descripción`\n"
            "Ejemplo: `120 Pasajes de micro`"
        )

# --- Esta parte es solo para pruebas locales ---
def main():
    print("Iniciando bot para pruebas locales...")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("gasto", nuevo_gasto))
    application.add_handler(CallbackQueryHandler(seleccionar_categoria, pattern='^categoria_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje_gasto))
    application.run_polling()

if __name__ == '__main__':
    # Antes de ejecutar localmente, asegúrate de tener tu archivo "credenciales.json"
    # y tu TOKEN de telegram en las variables de entorno o directamente en el código.
    main()
