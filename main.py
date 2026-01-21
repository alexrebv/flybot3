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

# ================= GOOGLE SHEETS =================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(GOOGLE_CREDS)
creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
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

    # MAIN MENU
    if text in ["/start", "Выход в главное меню"]:
        await start(update, context)
        return

    # BUTTON BACK
    if text == "Назад":
        prev_step = state.get("prev_step", "role")
        state["step"] = prev_step
        save_state(chat_id, state)

        if prev_step == "role":
            await start(update, context)
        elif prev_step == "login":
            await update.message.reply_text(
                "Введите логин:",
                reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
            )
        elif prev_step == "password":
            await update.message.reply_text(
                "Введите пароль:",
                reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
            )
        elif prev_step == "legal":
            await send_legal_menu(update)
        elif prev_step == "objects":
            await send_objects_by_legal(update, state)
        return

    # ROLE SELECTION
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
            state["prev_step"] = "role"

            if text in ["Администратор", "УПР / ТУ", "СОТ"]:
                state["step"] = "login"
                save_state(chat_id, state)
                await update.message.reply_text(
                    "Введите логин:",
                    reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
                )
            else:
                state["step"] = "legal"
                save_state(chat_id, state)
                await send_legal_menu(update)
            return

    # LOGIN
    if state.get("step") == "login":
        state["login"] = text
        state["step"] = "password"
        state["prev_step"] = "login"
        save_state(chat_id, state)
        await update.message.reply_text(
            "Введите пароль:",
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
        )
        return

    # PASSWORD
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
            state["prev_step"] = "password"
            save_state(chat_id, state)
            await send_legal_menu(update)
            return

        if role == "employee":
            for r in sheet_pass.get_all_values()[1:]:
                if r[0] == login and r[1] == text:
                    state["auth"] = True
                    state["step"] = "view"
                    state["prev_step"] = "password"
                    save_state(chat_id, state)
                    await update.message.reply_text(f"Добро пожаловать, {login}!")
                    return

        state["step"] = "login"
        save_state(chat_id, state)
        await update.message.reply_text(
            "❌ Неверные данные. Введите логин ещё раз:",
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
        )
        return

# ================= CALLBACK HANDLER =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    state = get_state(chat_id)

    # Кнопка назад
    if data == "BACK":
        prev_step = state.get("prev_step", "role")
        state["step"] = prev_step
        save_state(chat_id, state)

        if prev_step == "role":
            await start(update, context)
        elif prev_step == "legal":
            await send_legal_menu(update)
        elif prev_step == "objects":
            await send_objects_by_legal(update, state)
        return

    # Выбор юридического лица
    if data.startswith("LEGAL_"):
        legal = data.replace("LEGAL_", "")
        state["legal"] = legal
        state["step"] = "objects"
        state["prev_step"] = "legal"
        save_state(chat_id, state)
        await send_objects_by_legal(update, state)
        return

    # Выбор объекта
    if data.startswith("OBJ_"):
        obj = data.replace("OBJ_", "")
        # Получаем данные объекта из sheet_tel
        rows = sheet_tel.get_all_values()[1:]
        obj_data = [r for r in rows if r[0] == obj]
        msg = f"Вы выбрали объект: {obj}\n"
        if obj_data:
            msg += f"Данные: {obj_data[0]}"
        else:
            msg += "Данных нет"

        keyboard = [[InlineKeyboardButton("Назад", callback_data="BACK")]]
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
        return

# ================= MENUS =================
async def send_legal_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton(l, callback_data=f"LEGAL_{l}")]
        for l in LEGAL_MAIN
    ]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="BACK")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if getattr(update, "callback_query", None):
        await update.callback_query.message.edit_text(
            "Выберите юридическое лицо:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Выберите юридическое лицо:",
            reply_markup=reply_markup
        )

async def send_objects_by_legal(update: Update, state):
    legal = state.get("legal")
    data_rows = sheet_tel.get_all_values()[1:]
    objs = [r[0] for r in data_rows if r[1] == legal]

    keyboard = [[InlineKeyboardButton(o, callback_data=f"OBJ_{o}")] for o in objs]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="BACK")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if getattr(update, "callback_query", None):
        await update.callback_query.message.edit_text(
            f"Список объектов для {legal}:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"Список объектов для {legal}:",
            reply_markup=reply_markup
        )

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(callback_handler))
app.run_polling()
