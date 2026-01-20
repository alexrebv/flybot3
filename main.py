import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logging.basicConfig(level=logging.INFO)

# ====== Telegram / Sheets ======
TOKEN = os.getenv("TOKEN")
SHEET_TEL = os.getenv("SHEET_TEL")
SHEET_PASS = os.getenv("SHEET_PASS")
SHEET_LOG = os.getenv("SHEET_LOG")

LEGAL_MAIN = ["ИП Макаров","ИП Гасанов","ИП Норкин","ИП Кистанов","ИП Матвеев","Партнеры"]
LEGAL_PARTNERS = ["ИП Зименко Т.А.","ИП Иванов В.А.","ИП Иванов С.Е","ИП Измайлова Л.Е.","ИП Никифоров","ИП Рязанова","ИП Суворова","ИП Хабибуллин","ООО ФИКСТИ"]

# ===== Google Sheets через ENV =====
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds_json = os.getenv("GOOGLE_CREDS")
if not creds_json:
    raise Exception("Переменная окружения GOOGLE_CREDS не задана!")
creds_dict = json.loads(creds_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet_tel = client.open(SHEET_TEL).sheet1
sheet_pass = client.open(SHEET_PASS).sheet1
sheet_log = client.open(SHEET_LOG).sheet1

# ===== State =====
user_states = {}

def col_to_num(c):
    return ord(c.upper()) - 64

def get_state(chat_id):
    return user_states.get(chat_id, {})

def save_state(chat_id, state):
    user_states[chat_id] = state

def clear_state(chat_id):
    if chat_id in user_states:
        del user_states[chat_id]

# ===== Bot logic =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    clear_state(chat_id)
    save_state(chat_id, {"step":"role"})
    keyboard = [["Поставщик"],["Сотрудник"],["Администратор"],["УПР / ТУ"],["СОТ"]]
    await update.message.reply_text("Выберите тип пользователя:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    state = get_state(chat_id)
    
    # START / MAIN MENU
    if text in ["/start","Выход в главное меню"]:
        clear_state(chat_id)
        save_state(chat_id, {"step":"role"})
        await start(update, context)
        return

    # Step ROLE
    if state.get("step") == "role":
        role_map = {
            "Поставщик":"supplier",
            "Сотрудник":"employee",
            "Администратор":"admin",
            "УПР / ТУ":"uptu",
            "СОТ":"sot"
        }
        if text in role_map:
            state["role"] = role_map[text]
            if text in ["Администратор","УПР / ТУ","СОТ"]:
                state["step"] = "login"
                await update.message.reply_text("Введите логин:")
            else:
                state["step"] = "legal"
                await send_legal_menu(update, state)
            save_state(chat_id, state)
            return

    # Step LOGIN
    if state.get("step") == "login":
        state["login"] = text
        state["step"] = "password"
        save_state(chat_id, state)
        await update.message.reply_text("Введите пароль:")
        return

    # Step PASSWORD
    if state.get("step") == "password":
        role = state.get("role")
        login = state.get("login")
        ok = (
            (role=="admin" and login=="REB" and text=="7920") or
            (role=="uptu" and login=="Ypty" and text=="0933") or
            (role=="sot" and login=="SOT" and text=="71727374")
        )
        if ok:
            state["auth"] = True
            state["step"] = "legal"
            save_state(chat_id, state)
            await send_legal_menu(update, state)
            return
        # Employee check
        if role=="employee":
            if any(r[0]==login and r[1]==text for r in sheet_pass.get_all_values()[1:]):
                state["auth"] = True
                state["step"] = "view"
                save_state(chat_id, state)
                await update.message.reply_text(f"Добро пожаловать, {login}!")
                return
        state["step"] = "login"
        save_state(chat_id, state)
        await update.message.reply_text("❌ Неверные данные. Введите логин ещё раз:")
        return

    # Step LEGAL selection
    if state.get("step") == "legal":
        if text.startswith("LEGAL_"):
            legal = text.replace("LEGAL_","")
            state["legal"] = legal
            state["step"] = "objects"
            save_state(chat_id, state)
            await send_objects_by_legal(update, state)
            return

async def send_legal_menu(update: Update, state):
    keyboard = [[InlineKeyboardButton(l, callback_data=f"LEGAL_{l}")] for l in LEGAL_MAIN]
    await update.message.reply_text("Выберите юридическое лицо:", reply_markup=InlineKeyboardMarkup(keyboard))

async def send_objects_by_legal(update: Update, state):
    legal = state.get("legal")
    role = state.get("role")
    data = sheet_tel.get_all_values()[1:]
    objs = [r[0] for r in data if r[1]==legal]
    keyboard = [[InlineKeyboardButton(o, callback_data=f"OBJ_{o}")] for o in objs]
    await update.message.reply_text("Список объектов:", reply_markup=InlineKeyboardMarkup(keyboard))
    if role in ["admin","sot","uptu"]:
        kb2 = [["Добавить объект"],["Выход в главное меню"]]
    else:
        kb2 = [["Выход в главное меню"]]
    await update.message.reply_text("Доступные действия:", reply_markup=ReplyKeyboardMarkup(kb2, resize_keyboard=True))

# ===== Run bot =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
