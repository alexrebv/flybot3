import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
SHEET_TEL = os.getenv("SHEET_TEL")
SHEET_PASS = os.getenv("SHEET_PASS")
SHEET_LOG = os.getenv("SHEET_LOG")

LEGAL_MAIN = ["ИП Макаров","ИП Гасанов","ИП Норкин","ИП Кистанов","ИП Матвеев","Партнеры"]
LEGAL_PARTNERS = ["ИП Зименко Т.А.","ИП Иванов В.А.","ИП Иванов С.Е","ИП Измайлова Л.Е.","ИП Никифоров","ИП Рязанова","ИП Суворова","ИП Хабибуллин","ООО ФИКСТИ"]

# Настройка Google Sheets
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
client = gspread.authorize(creds)
sheet_tel = client.open(SHEET_TEL).sheet1
sheet_pass = client.open(SHEET_PASS).sheet1
sheet_log = client.open(SHEET_LOG).sheet1

logging.basicConfig(level=logging.INFO)

user_states = {}

# ===== Команды =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_states[chat_id] = {"step":"role"}
    keyboard = [["Поставщик"],["Сотрудник"],["Администратор"],["УПР / ТУ"],["СОТ"]]
    await update.message.reply_text("Выберите тип пользователя:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    state = user_states.get(chat_id, {"step":"role"})

    if text in ["/start","Выход в главное меню"]:
        user_states[chat_id] = {"step":"role"}
        await start(update, context)
        return

    # Тут добавь логику ролей, объектов и авторизации по аналогии с JS-версией

# ===== Запуск бота =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
