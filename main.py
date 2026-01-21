import os
import json
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

import gspread
from google.oauth2 import service_account

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)

# ================= ENV =================
TOKEN = os.getenv("TOKEN")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

if not TOKEN or not GOOGLE_CREDS:
    raise RuntimeError("❌ Не заданы все переменные окружения")

# ================= LEGAL =================
LEGAL_MAIN = ["ИП Макаров","ИП Гасанов","ИП Норкин","ИП Кистанов","ИП Матвеев","Партнеры"]
LEGAL_PARTNERS = ["ИП Зименко Т.А.","ИП Иванов В.А.","ИП Иванов С.Е","ИП Измайлова Л.Е.","ИП Никифоров","ИП Рязанова","ИП Суворова","ИП Хабибуллин","ООО ФИКСТИ"]

# ================= GOOGLE SHEETS =================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_CREDS)
creds_dict["private_key"] = creds_dict["private_key"].replace("\\n","\n")
creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET_NAME = "NUMBER"
sheet_tel = client.open(SPREADSHEET_NAME).worksheet("tel")
sheet_pass = client.open(SPREADSHEET_NAME).worksheet("pass")
sheet_log = client.open(SPREADSHEET_NAME).worksheet("log")

# ================= STATE =================
user_states = {}

def get_state(chat_id): return user_states.get(chat_id,{})
def save_state(chat_id,state): user_states[chat_id]=state
def clear_state(chat_id): user_states.pop(chat_id,None)

# ================= UTILS =================
def col_to_num(col): return ord(col.upper())-64
def get_object_row(name):
    rows = sheet_tel.get_all_values()
    for r in rows[1:]:
        if r[0]==name: return r
    return None
def get_object_value(obj,col):
    row = get_object_row(obj)
    return row[col_to_num(col)-1] if row else ""
def update_object(obj,col,value):
    rows = sheet_tel.get_all_values()
    for i,r in enumerate(rows[1:],start=2):
        if r[0]==obj:
            sheet_tel.update_cell(i,col_to_num(col),value)
            return
def check_auth(obj,login,password):
    rows = sheet_pass.get_all_values()[1:]
    for r in rows:
        if (r[0]==obj or r[0]=="ADMIN") and r[1]==login and r[2]==password:
            return True
    return False
def log_change(user_id,role,obj,col,old,new):
    row = [str(datetime.now()),user_id,role,obj,col,old,new]
    sheet_log.append_row(row)

# ================= BOT =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    clear_state(chat_id)
    save_state(chat_id,{"step":"role"})
    keyboard = [["Поставщик"],["Сотрудник"],["Администратор"],["УПР / ТУ"],["СОТ"]]
    await update.message.reply_text("Выберите тип пользователя:",reply_markup=ReplyKeyboardMarkup(keyboard,resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    state = get_state(chat_id)

    # MAIN MENU
    if text in ["/start","Выход в главное меню"]:
        await start(update,context)
        return

    # BACK BUTTON
    if text=="Назад":
        prev = state.get("prev_step","role")
        state["step"]=prev
        save_state(chat_id,state)
        if prev=="role": await start(update,context)
        elif prev=="legal": await send_legal_menu(update)
        elif prev=="objects": await send_objects_by_legal(update,state)
        elif prev=="add_field": ask_next_field(update,state)
        return

    # ROLE
    if state.get("step")=="role":
        roles = {"Поставщик":"supplier","Сотрудник":"employee","Администратор":"admin","УПР / ТУ":"uptu","СОТ":"sot"}
        if text in roles:
            state["role"]=roles[text]
            state["prev_step"]="role"
            if text in ["Администратор","УПР / ТУ","СОТ"]:
                state["step"]="login"
                save_state(chat_id,state)
                await update.message.reply_text("Введите логин:",reply_markup=ReplyKeyboardMarkup([["Назад"]],resize_keyboard=True))
            else:
                state["step"]="legal"
                save_state(chat_id,state)
                await send_legal_menu(update)
            return

    # LOGIN
    if state.get("step")=="login":
        state["login"]=text
        state["step"]="password"
        state["prev_step"]="login"
        save_state(chat_id,state)
        await update.message.reply_text("Введите пароль:",reply_markup=ReplyKeyboardMarkup([["Назад"]],resize_keyboard=True))
        return

    # PASSWORD
    if state.get("step")=="password":
        role=state.get("role"); login=state.get("login")
        ok=((role=="admin" and login=="REB" and text=="7920") or
            (role=="uptu" and login=="Ypty" and text=="0933") or
            (role=="sot" and login=="SOT" and text=="71727374"))
        if ok:
            state["auth"]=True
            state["step"]="legal"
            state["prev_step"]="password"
            save_state(chat_id,state)
            await send_legal_menu(update)
            return
        if role=="employee" and check_auth("",login,text):
            state["auth"]=True
            state["step"]="view"
            state["prev_step"]="password"
            save_state(chat_id,state)
            await update.message.reply_text(f"Добро пожаловать, {login}!")
            return
        state["step"]="login"; save_state(chat_id,state)
        await update.message.reply_text("❌ Неверные данные\nВведите логин ещё раз:",reply_markup=ReplyKeyboardMarkup([["Назад"]],resize_keyboard=True))
        return

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data = query.data
    state = get_state(chat_id)

    if data=="BACK":
        prev = state.get("prev_step","role")
        state["step"]=prev
        save_state(chat_id,state)
        if prev=="role": await start(update,context)
        elif prev=="legal": await send_legal_menu(update)
        elif prev=="objects": await send_objects_by_legal(update,state)
        elif prev=="add_field": ask_next_field(update,state)
        return

    if data.startswith("LEGAL_"):
        legal = data.replace("LEGAL_","")
        state["legal"]=legal
        state["step"]="objects"
        state["prev_step"]="legal"
        save_state(chat_id,state)
        await send_objects_by_legal(update,state)
        return

    if data.startswith("OBJ_"):
        obj = data.replace("OBJ_","")
        state["object"]=obj
        state["step"]="view"
        save_state(chat_id,state)
        row = get_object_row(obj)
        text = f"*{row[0]}*\n-ИП: {row[1]}\n-Адрес парковки: {row[2]}\n-Адрес объекта: {row[3]}\n-Метка парковки: {row[4]}\n-Нюансы: {row[5]}\n-Как добраться: {row[6]}\n-Метка объекта: {row[7]}\n-Фото: {row[8]}\n-Телефоны: {row[9]}, {row[10]}, {row[11]}\n-Управляющий: {row[12]}\n-ТУ: {row[13]}"
        kb = [[InlineKeyboardButton("Назад",callback_data="BACK")]]
        await query.message.edit_text(text,parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(kb))
        return

    if data=="ADD_OBJ":
        state["step"]="add_field"
        state["newObject"]={}
        state["fields"]=[("name","Название объекта"),
                         ("legal","Юридическое лицо",state["legal"]),
                         ("parking","Адрес парковки"),
                         ("address","Адрес объекта"),
                         ("parkingTag","Метка парковки"),
                         ("notes","Нюансы"),
                         ("howToGet","Как добраться"),
                         ("objectTag","Метка объекта"),
                         ("photo","Фото"),
                         ("phone1","Телефон 1"),
                         ("phone2","Телефон 2"),
                         ("phone3","Телефон 3"),
                         ("manager","Управляющий"),
                         ("tu","ТУ")]
        state["current_field"]=0
        state["prev_step"]="objects"
        save_state(chat_id,state)
        ask_next_field(update,state)
        return

# ================= ADD / EDIT OBJECT =================
def ask_next_field(update,state):
    chat_id = update.effective_chat.id if hasattr(update,'message') else update.callback_query.message.chat.id
    field = state["fields"][state["current_field"]]
    label = field[1]
    default = f" (по умолчанию: {field[2]})" if len(field)>2 else ""
    kb = [[InlineKeyboardButton("Пропустить",callback_data="SKIP")],[InlineKeyboardButton("Назад",callback_data="BACK")]]
    text = f"Введите {label}{default}:"
    if hasattr(update,"callback_query"):
        update.callback_query.message.reply_text(text,reply_markup=InlineKeyboardMarkup(kb))
    else:
        update.message.reply_text(text,reply_markup=InlineKeyboardMarkup(kb))

# ================= MENUS =================
async def send_legal_menu(update):
    keyboard = [[InlineKeyboardButton(l,callback_data=f"LEGAL_{l}")] for l in LEGAL_MAIN]
    keyboard.append([InlineKeyboardButton("Назад",callback_data="BACK")])
    markup = InlineKeyboardMarkup(keyboard)
    if getattr(update,"callback_query",None):
        await update.callback_query.message.edit_text("Выберите юридическое лицо:",reply_markup=markup)
    else:
        await update.message.reply_text("Выберите юридическое лицо:",reply_markup=markup)

async def send_objects_by_legal(update,state):
    legal = state.get("legal")
    data_rows = sheet_tel.get_all_values()[1:]
    objs = [r[0] for r in data_rows if r[1]==legal]
    keyboard = [[InlineKeyboardButton(o,callback_data=f"OBJ_{o}")] for o in objs]
    if state.get("role") in ["admin","sot","uptu"]:
        keyboard.append([InlineKeyboardButton("Добавить объект",callback_data="ADD_OBJ")])
    keyboard.append([InlineKeyboardButton("Назад",callback_data="BACK")])
    markup = InlineKeyboardMarkup(keyboard)
    if getattr(update,"callback_query",None):
        await update.callback_query.message.edit_text(f"Список объектов для {legal}:",reply_markup=markup)
    else:
        await update.message.reply_text(f"Список объектов для {legal}:",reply_markup=markup)

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start",start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_message))
app.add_handler(CallbackQueryHandler(callback_handler))
app.run_polling()
