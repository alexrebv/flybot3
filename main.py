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


# ================= GOOGLE SHEETS (RENDER FIX) =================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(GOOGLE_CREDS)

# 🔥 КРИТИЧЕСКИ ВАЖНО ДЛЯ Render
creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

creds = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=SCOPES
)

client = gspread.authorize(creds)

# Название таблицы
SPREADSHEET_NAME = "Number"

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
            (role ==
