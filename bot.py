import os
import asyncio
from functools import wraps
from keep_alive import keep_alive
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, InputFile, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Предметы ---
SUBJECTS = {
    "Математика": {"nominative": "Математика", "accusative": "математику"},
    "Физика": {"nominative": "Физика", "accusative": "физику"},
    "Химия": {"nominative": "Химия", "accusative": "химию"},
    "Биология": {"nominative": "Биология", "accusative": "биологию"},
    "Русский": {"nominative": "Русский язык", "accusative": "русский язык"},
    "Биохимия": {"nominative": "Биохимия", "accusative": "биохимию"}
}

# --- Админ ---
ADMIN_ID = 7972251746
ADMIN_USERNAME = "@dogwarts_admin"

# --- Google Sheets ---
GOOGLE_SHEET_NAME = "DogMathism"
CREDENTIALS_FILE = "credentials.json"

# --- Каналы ---
CHANNELS_BY_SUBJECT = {
    "Математика": "@DogMathic",
    "Физика": "@DogPhysic",
    "Химия": "@DogChemik",
    "Биология": "@DogBio",
    "Русский": "@DogRussik",
    "Биохимия": "@DogBioChemik",
}

# --- Материалы ---
materials_files = {
    "Математика": [("Свойства окружности.pdf", "materials/math/Circle.pdf"),
                   ("Гайд векторы.pdf", "materials/math/Vectors.pdf")],
    "Физика": [("Основы механики.pdf", "materials/physics_mechanics.pdf")],
    "Химия": [("Таблица Менделеева.pdf", "materials/chem_periodic_table.pdf")],
    "Биология": [("Клеточная биология.pdf", "materials/bio_cell_biology.pdf")],
    "Русский": [("Правила орфографии.pdf", "materials/rus_orthography_rules.pdf")],
    "Биохимия": [("Основы биохимии.pdf", "materials/biochem_basics.pdf")],
}

# --- Пользователи ---
users_data = {}

# --- Декоратор "печатает" ---
def typing_action(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.message:
            await update.message.reply_chat_action("typing")
        elif update.callback_query:
            await update.callback_query.message.reply_chat_action("typing")
        await asyncio.sleep(0.7)
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Запись в Google Sheets ---
def write_to_sheet(data):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    row = [
        data.get("nickname", "—"),
        data.get("phone", "—"),
        data.get("role", "—"),
        data.get("subject", "—"),
        data.get("class", "—"),
        data.get("exam", "—")
    ]
    sheet.append_row(row)

# --- /start ---
@typing_action
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_data[user_id] = {"step": "role"}
    keyboard = [
        [InlineKeyboardButton("Ученик", callback_data="role_student")],
        [InlineKeyboardButton("Родитель", callback_data="role_parent")],
        [InlineKeyboardButton("Студент ВУЗа", callback_data="role_university")],
        [InlineKeyboardButton("Преподаватель", callback_data="role_teacher")]
    ]
    await update.message.reply_text(
        "👋 Добро пожаловать в <b>DogWarts</b> - <b>школу</b>, где знания сильнее <b>магии</b>\n\n"
        "Выберите вашу роль:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Выбор роли ---
@typing_action
async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    role = query.data.split("_")[1]
    users_data[user_id]["role"] = role

    if role in ["student", "parent"]:
        users_data[user_id]["step"] = "action"
        keyboard = [
            [InlineKeyboardButton("Запись на занятия", callback_data="action_register")],
            [InlineKeyboardButton("Получить полезные материалы", callback_data="action_materials")]
        ]
        await query.message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif role == "university":
        users_data[user_id]["subject"] = "Биохимия"
        await send_class_menu(update, context)
        users_data[user_id]["step"] = "class"
    elif role == "teacher":
        await query.message.reply_text(f"Если Вы хотите работать у нас, свяжитесь с админом {ADMIN_USERNAME}")
        users_data[user_id]["step"] = None

# --- Действие ученика/родителя ---
@typing_action
async def student_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    action = query.data.split("_")[1]
    users_data[user_id]["action"] = action

    if action == "register":
        keyboard = [
            [InlineKeyboardButton(subj, callback_data=f"subject|{subj}")]
            for subj in SUBJECTS if subj != "Биохимия"
        ]
        users_data[user_id]["step"] = "subject"
        await query.message.reply_text("Выберите предмет:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif action == "materials":
        users_data[user_id]["step"] = "class"
        await send_class_menu(update, context)

# --- Выбор предмета ---
@typing_action
async def choose_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    subject = query.data.split("|")[1]
    users_data[user_id]["subject"] = subject
    users_data[user_id]["step"] = "class"
    await send_class_menu(update, context)

# --- Класс ---
async def send_class_menu(update, context):
    keyboard = [
        [InlineKeyboardButton("5", callback_data="class|5"),
         InlineKeyboardButton("6", callback_data="class|6")],
        [InlineKeyboardButton("7", callback_data="class|7"),
         InlineKeyboardButton("8", callback_data="class|8")],
        [InlineKeyboardButton("10", callback_data="class|10")],
        [InlineKeyboardButton("Подготовка к ОГЭ", callback_data="class|OGE"),
         InlineKeyboardButton("Подготовка к ЕГЭ", callback_data="class|EGE")]
    ]
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.message.reply_text("Выберите класс:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Выберите класс:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Выбор класса ---
@typing_action
async def class_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    class_name = query.data.split("|")[1]
    users_data[user_id]["class"] = class_name
    users_data[user_id]["nickname"] = update.effective_user.username or "—"

    role = users_data[user_id]["role"]
    if role in ["student", "parent"] and users_data[user_id].get("action") == "register":
        users_data[user_id]["step"] = "phone"
        await query.message.reply_text(
            "Отправьте ваш контакт:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Отправить контакт", request_contact=True)]],
                resize_keyboard=True, one_time_keyboard=True
            )
        )
    else:
        # сразу показать материалы
        write_to_sheet(users_data[user_id])
        await send_materials_menu(update, context, user_id)
        users_data[user_id]["step"] = "done"
        await return_to_main_menu(update, context)

# --- Телефон ---
@typing_action
async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    contact = update.message.contact
    users_data[user_id]["phone"] = contact.phone_number
    write_to_sheet(users_data[user_id])
    await send_materials_menu(update, context, user_id)
    users_data[user_id]["step"] = "done"
    await return_to_main_menu(update, context)

# --- Проверка подписки ---
async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str) -> bool:
    channel_username = CHANNELS_BY_SUBJECT.get(subject)
    try:
        member = await context.bot.get_chat_member(channel_username, update.effective_user.id)
        return member.status in ["member", "creator", "administrator"]
    except:
        return False

# --- Материалы ---
@typing_action
async def send_materials_menu(update, context, user_id):
    subject = users_data[user_id].get("subject")
    if not subject:
        return
    subscribed = await is_subscribed(update, context, subject)
    if not subscribed:
        await context.bot.send_message(chat_id=user_id,
            text=f"❌ Подпишитесь на канал {CHANNELS_BY_SUBJECT.get(subject, 'канал')} и попробуйте снова.")
        return
    files = materials_files.get(subject)
    if not files:
        await context.bot.send_message(chat_id=user_id, text="📂 Для этого предмета пока нет материалов.")
        return
    keyboard = [[InlineKeyboardButton(name, callback_data=f"material|{subject}|{idx}")] for idx, (name, _) in enumerate(files)]
    await context.bot.send_message(chat_id=user_id,
        text=f"📚 Выберите материал по {subject}:",
        reply_markup=InlineKeyboardMarkup(keyboard))

# --- Прогресс-бар и отправка файла ---
@typing_action
async def send_material_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, subject, idx_str = query.data.split("|")
        idx = int(idx_str)
    except:
        await query.message.reply_text("❌ Ошибка обработки запроса.")
        return
    files = materials_files.get(subject)
    if not files or idx >= len(files):
        await query.message.reply_text("❌ Материал не найден.")
        return
    filename, filepath = files[idx]
    try:
        progress_msg = await query.message.reply_text("Готовлю твой материал… [░░░░░░░░░░] 0%")
        total_steps = 10
        for step in range(1, total_steps + 1):
            await asyncio.sleep(0.3)
            bar = "█" * step + "░" * (total_steps - step)
            percent = step * 10
            await progress_msg.edit_text(f"Готовлю твой материал… [{bar}] {percent}%")
        with open(filepath, "rb") as f:
            await query.message.reply_document(document=InputFile(f), filename=filename)
        await progress_msg.delete()
    except FileNotFoundError:
        await query.message.reply_text("❌ Файл не найден.")
    except Exception as e:
        print(f"Ошибка send_material_file: {e}")
        await query.message.reply_text("❌ Ошибка при подготовке материала.")

# --- Главное меню для повторного выбора ---
async def return_to_main_menu(update, context):
    user_id = update.effective_user.id
    users_data[user_id]["step"] = "role"
    keyboard = [
        [InlineKeyboardButton("Главное меню", callback_data="menu_main")]
    ]
    if update.callback_query:
        await update.callback_query.message.reply_text("Вы можете вернуться в главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Вы можете вернуться в главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Ошибки ---
async def error_handler(update, context):
    print(f"❌ Ошибка: {context.error}")

# --- Main ---
def main():
    keep_alive()
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(choose_role, pattern="^role_"))
    app.add_handler(CallbackQueryHandler(student_action, pattern="^action_"))
    app.add_handler(CallbackQueryHandler(choose_subject, pattern="^subject\|"))
    app.add_handler(CallbackQueryHandler(class_choice, pattern="^class\|"))
    app.add_handler(CallbackQueryHandler(send_material_file, pattern="^material\|"))
    app.add_handler(MessageHandler(filters.CONTACT, phone_input))
    app.add_error_handler(error_handler)

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

    


