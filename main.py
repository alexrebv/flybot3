import os
import json
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
import gspread
from google.oauth2 import service_account

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)

# ================= ENV =================
TOKEN = os.getenv("TOKEN")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

if not all([TOKEN, GOOGLE_CREDS]):
    raise RuntimeError("❌ Не заданы все переменные окружения")

# ================= LEGAL =================
LEGAL_MAIN = [
    "ИП Макаров", "ИП Гасанов", "ИП Норкин",
    "ИП Кистанов", "ИП Матвеев", "Партнеры"
]

LEGAL_PARTNERS = [
    "ИП Зименко Т.А.", "ИП Иванов В.А.", "ИП Иванов С.Е",
    "ИП Измайлова Л.Е.", "ИП Никифоров", "ИП Рязанова",
    "ИП Суворова", "ИП Хабибуллин", "ООО ФИКСТИ"
]

# ================= GOOGLE SHEETS =================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(GOOGLE_CREDS)
creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

creds = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=SCOPES
)

client = gspread.authorize(creds)

SPREADSHEET_NAME = "NUMBER"
sheet_tel = client.open(SPREADSHEET_NAME).worksheet("tel")
sheet_pass = client.open(SPREADSHEET_NAME).worksheet("pass")
sheet_log = client.open(SPREADSHEET_NAME).worksheet("log")

# ================= STATE =================
user_states = {}

def get_state(chat_id):
    return user_states.get(chat_id, {})

def save_state(chat_id, state):
    user_states[chat_id] = state

def clear_state(chat_id):
    user_states.pop(chat_id, None)

# ================= BOT LOGIC =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    clear_state(chat_id)
    save_state(chat_id, {"step": "role"})
    keyboard = [
        ["Поставщик"],
        ["Сотрудник"],
        ["Администратор"],
        ["УПР / ТУ"],
        ["СОТ"]
    ]
    await update.message.reply_text(
        "Выберите тип пользователя:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    state = get_state(chat_id)

    # ===== MAIN MENU =====
    if text in ["/start", "Выход в главное меню"]:
        await start(update, context)
        return

    # ===== НАЗАД =====
    if text == "Назад к юр.лицам":
        state["step"] = "legal"
        save_state(chat_id, state)
        await send_legal_menu(update)
        return

    # ===== РОЛИ =====
    if state.get("step") == "role":
        role_map = {
            "Поставщик": "supplier",
            "Сотрудник": "employee",
            "Администратор": "admin",
            "УПР / ТУ": "uptu",
            "СОТ": "sot"
        }
        if text in role_map:
            state["role"] = role_map[text]
            if text in ["Администратор", "УПР / ТУ", "СОТ"]:
                state["step"] = "login"
                save_state(chat_id, state)
                await update.message.reply_text("Введите логин:")
            else:
                state["step"] = "legal"
                save_state(chat_id, state)
                await send_legal_menu(update)
            return

    # ===== LOGIN =====
    if state.get("step") == "login":
        state["login"] = text
        state["step"] = "password"
        save_state(chat_id, state)
        await update.message.reply_text("Введите пароль:")
        return

    # ===== PASSWORD =====
    if state.get("step") == "password":
        role = state.get("role")
        login = state.get("login")
        ok = (
            (role == "admin" and login == "REB" and text == "7920") or
            (role == "uptu" and login == "Ypty" and text == "0933") or
            (role == "sot" and login == "SOT" and text == "71727374")
        )
        if ok:
            state["auth"] = True
            state["step"] = "legal"
            save_state(chat_id, state)
            await send_legal_menu(update)
            return
        if role == "employee":
            for r in sheet_pass.get_all_values()[1:]:
                if r[0] == login and r[1] == text:
                    state["auth"] = True
                    state["step"] = "view"
                    save_state(chat_id, state)
                    await update.message.reply_text(f"Добро пожаловать, {login}!")
                    return
        state["step"] = "login"
        save_state(chat_id, state)
        await update.message.reply_text("❌ Неверные данные. Введите логин ещё раз:")
        return

# ===== ФУНКЦИИ ДЛЯ ОБЪЕКТОВ =====
def get_object_row(name):
    """Возвращает строку объекта по названию"""
    data = sheet_tel.get_all_values()
    for row in data[1:]:
        if row[0] == name:
            return row
    return None

async def send_object(update, state):
    """Красиво показывает данные объекта"""
    chat_id = update.effective_chat.id if hasattr(update,"message") else update.callback_query.message.chat.id
    obj = state.get("object")
    row = get_object_row(obj)
    if not row:
        await update.message.reply_text("❌ Объект не найден")
        return

    text = f"*Название объекта:* {row[0]}\n"
    text += f"- ИП: {row[1]}\n"
    text += f"- Адрес парковки: {row[2]}\n"
    text += f"- Адрес объекта: {row[3]}\n"
    text += f"- Метка парковки: {row[4]}\n"
    text += f"- Нюансы: {row[5]}\n"
    text += f"- Как добраться: {row[6]}\n"
    text += f"- Метка объекта: {row[7]}\n"
    text += f"- Фото: {row[8]}\n\n"
    text += f"- Телефон 1: {row[9]}\n"
    text += f"- Телефон 2: {row[10]}\n"
    text += f"- Телефон 3: {row[11]}\n\n"
    text += f"- Управляющий: {row[12]}\n"
    text += f"- ТУ: {row[13]}"

    kb = [[InlineKeyboardButton("Назад к юр.лицам", callback_data="BACK")]]
    if state.get("role") in ["admin","sot","uptu"]:
        kb.insert(0,[InlineKeyboardButton("Редактировать", callback_data="EDIT_OBJ")])

    if hasattr(update,"callback_query") and update.callback_query:
        await update.callback_query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
        )

async def send_objects_by_legal(update, state):
    """Показывает список объектов по выбранному юр.лицу"""
    chat_id = update.effective_chat.id if hasattr(update,"message") else update.callback_query.message.chat.id
    legal = state.get("legal")
    role = state.get("role")

    data = sheet_tel.get_all_values()[1:]
    objs = [r[0] for r in data if r[1] == legal]

    if not objs:
        await update.message.reply_text("❌ Объектов для этого юр.лица нет")
        return

    kb = [[InlineKeyboardButton(o, callback_data=f"OBJ_{o}")] for o in objs]
    await update.message.reply_text("Выберите объект:", reply_markup=InlineKeyboardMarkup(kb))

    if role in ["admin","sot","uptu"]:
        kb2 = [["Добавить объект"],["Выход в главное меню"]]
    else:
        kb2 = [["Выход в главное меню"]]

    await update.message.reply_text(
        "Доступные действия:", reply_markup=ReplyKeyboardMarkup(kb2, resize_keyboard=True)
    )

# ===== MENUS =====
async def send_legal_menu(update):
    keyboard = [[InlineKeyboardButton(l, callback_data=f"LEGAL_{l}")] for l in LEGAL_MAIN]
    if hasattr(update,"callback_query") and update.callback_query:
        await update.callback_query.message.edit_text(
            "Выберите юридическое лицо:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "Выберите юридическое лицо:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ===== CALLBACK HANDLER =====
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    state = get_state(chat_id)

    if data == "BACK":
        state["step"] = "legal"
        save_state(chat_id, state)
        await send_legal_menu(update)
        return

    if data == "EDIT_OBJ":
        await query.message.reply_text("Функция редактирования пока не реализована")
        return

    if data.startswith("LEGAL_"):
        legal = data.replace("LEGAL_","")
        state["legal"] = legal
        state["step"] = "objects"
        save_state(chat_id, state)
        await send_objects_by_legal(update, state)
        return

    if data.startswith("OBJ_"):
        obj = data.replace("OBJ_","")
        state["object"] = obj
        state["step"] = "view"
        save_state(chat_id, state)
        await send_object(update, state)
        return

# ===== RUN BOT =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(handle_callback))
app.run_polling()
