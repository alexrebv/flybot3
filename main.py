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
    filters,
    ContextTypes
)

import gspread
from google.oauth2 import service_account


# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)


# ================= ENV =================
TOKEN = os.getenv("TOKEN")
SHEET_TEL = os.getenv("SHEET_TEL")
SHEET_PASS = os.getenv("SHEET_PASS")
SHEET_LOG = os.getenv("SHEET_LOG")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

if not all([TOKEN, SHEET_TEL, SHEET_PASS, SHEET_LOG, GOOGLE_CREDS]):
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


# ================= GOOGLE SHEETS (RENDER FIX) =================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(GOOGLE_CREDS)

# 🔥 КРИТИЧЕСКИ ВАЖНО ДЛЯ RENDER
creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

creds = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=SCOPES
)

client = gspread.authorize(creds)

sheet_tel = client.open(SHEET_TEL).sheet1
sheet_pass = client.open(SHEET_PASS).sheet1
sheet_log = client.open(SHEET_LOG).sheet1


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

    # ROLE
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
                await update.message.reply_text("Введите логин:")
            else:
                state["step"] = "legal"
                await send_legal_menu(update)

            save_state(chat_id, state)
            return

    # LOGIN
    if state.get("step") == "login":
        state["login"] = text
        state["step"] = "password"
        save_state(chat_id, state)
        await update.message.reply_text("Введите пароль:")
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


# ================= MENUS =================
async def send_legal_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton(l, callback_data=f"LEGAL_{l}")]
        for l in LEGAL_MAIN
    ]

    await update.message.reply_text(
        "Выберите юридическое лицо:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
