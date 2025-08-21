import os
import asyncio
from functools import wraps
from keep_alive import keep_alive
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Предметы ---
SUBJECTS = ["Математика", "Физика", "Химия", "Биология", "Русский", "Биохимия"]

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
    "Математика": [
        ("Свойства окружности.pdf", "materials/math/Circle.pdf"),
        ("Гайд векторы.pdf", "materials/math/Vectors.pdf"),
    ],
    "Физика": [
        ("Основы механики.pdf", "materials/physics_mechanics.pdf"),
    ],
    "Химия": [
        ("Таблица Менделеева.pdf", "materials/chem_periodic_table.pdf"),
    ],
    "Биология": [
        ("Клеточная биология.pdf", "materials/bio_cell_biology.pdf"),
    ],
    "Русский": [
        ("Правила орфографии.pdf", "materials/rus_orthography_rules.pdf"),
    ],
    "Биохимия": [
        ("Основы биохимии.pdf", "materials/biochem_basics.pdf"),
    ],
}

# --- Пользователи ---
users_data = {}

# --- typing эффект ---
def typing_action(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.message:
            await update.message.chat.send_action("typing")
        elif update.callback_query:
            await update.callback_query.message.chat.send_action("typing")
        await asyncio.sleep(0.5)
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Работа с таблицей ---
def write_to_sheet(username, phone, subject):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    sheet.append_row([username or "—", phone, subject])

def read_all_entries():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    return sheet.get_all_values()[1:]

# --- Старт ---
@typing_action
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(subject, callback_data=subject)] for subject in SUBJECTS]
    await update.message.reply_text(
        "👋 Добро пожаловать в <b>DogWarts</b> - <b>школу</b>, где знания сильнее <b>магии</b>\n\n"
        "📚 Предметы:\n\n"
        "🧠 Математика - @DogMathic\n"
        "🧪 Химия - @DogChemik\n"
        "⚛️ Биохимия - @DogBioChemik\n"
        "📖 Русский язык - @DogRussik\n"
        "🌿 Биология - @DogBio\n"
        "⚙️ Физика - @DogPhysic\n\n"
        f"💬 Вопросы и запись - {ADMIN_USERNAME}\n\n"
        "Выбирай предмет и начни свой путь к успеху 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Обработка выбора предмета ---
@typing_action
async def choose_subject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data
    user_id = update.effective_user.id

    users_data[user_id] = {"username": query.from_user.username, "subject": subject}

    reply_markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить контакт", request_contact=True)]],
        resize_keyboard=True
    )
    await query.message.reply_text("📲 Пожалуйста, отправь свой тг:", reply_markup=reply_markup)

# --- Получение телефона ---
@typing_action
async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.contact:
        return

    contact = update.message.contact
    user_id = update.effective_user.id
    phone_number = contact.phone_number
    username = update.effective_user.username
    subject = users_data.get(user_id, {}).get("subject")

    if not subject:
        await update.message.reply_text("Сначала выбери предмет через /start.")
        return

    # Записываем
    users_data[user_id].update({"phone": phone_number})
    write_to_sheet(username, phone_number, subject)

    notify_text = (
        f"🆕 Новая заявка!\n"
        f"👤 @{username or '—'}\n"
        f"📞 {phone_number}\n"
        f"📘 Предмет: {subject}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text)

    await update.message.reply_text(
        f"✅ Ты записан на предмет!\n\n"
        "Теперь ты можешь получить материалы, нажав на кнопку ниже 👇",
        reply_markup=ReplyKeyboardMarkup([["📚 Материалы"]], resize_keyboard=True)
    )

# --- Проверка подписки ---
async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str) -> bool:
    channel_username = CHANNELS_BY_SUBJECT.get(subject)
    if not channel_username:
        return True
    try:
        member = await context.bot.get_chat_member(channel_username, update.effective_user.id)
        return member.status in ["member", "creator", "administrator"]
    except Exception:
        return False

# --- Прогресс-бар и отправка материалов ---
@typing_action
async def send_material_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, subject, idx_str = query.data.split("|")
    idx = int(idx_str)

    files = materials_files.get(subject)
    if not files or idx >= len(files):
        await query.message.reply_text("Материал не найден.")
        return

    filename, filepath = files[idx]

    try:
        progress_msg = await query.message.reply_text("Готовлю твой материал… [░░░░░░░░░░] 0%")
        total_steps = 10
        for step in range(1, total_steps + 1):
            await asyncio.sleep(0.4)
            bar = "█" * step + "░" * (total_steps - step)
            percent = step * 10
            await progress_msg.edit_text(f"Готовлю твой материал… [{bar}] {percent}%")

        with open(filepath, "rb") as f:
            await query.message.reply_document(document=InputFile(f), filename=filename)

        await progress_msg.delete()
    except FileNotFoundError:
        await query.message.reply_text("Файл не найден.")

# --- Меню материалов ---
@typing_action
async def materials_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = users_data.get(user_id)
    if not user_info:
        await update.message.reply_text("😕 Ты ещё не записан. Напиши /start.")
        return

    subject = user_info.get("subject")
    subscribed = await is_subscribed(update, context, subject)
    if not subscribed:
        await update.message.reply_text(
            f"❌ Подпишись на канал {CHANNELS_BY_SUBJECT.get(subject, 'канал')} и попробуй снова."
        )
        return

    files = materials_files.get(subject)
    if not files:
        await update.message.reply_text("📂 Для твоего предмета пока нет материалов.")
        return

    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"material|{subject}|{idx}")]
        for idx, (name, _) in enumerate(files)
    ]
    await update.message.reply_text(
        f"📚 Выбери материал по {subject}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Админка ---
@typing_action
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    if username != ADMIN_USERNAME.strip("@"):
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    entries = read_all_entries()
    if not entries:
        await update.message.reply_text("📭 Пока нет заявок.")
        return
    text = "📋 Заявки учеников:\n"
    for row in entries:
        text += f"👤 @{row[0]} 📞 {row[1]} 📘 {row[2]}\n"
    await update.message.reply_text(text)

# --- Main ---
def main():
    keep_alive()
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    # команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("materials", materials_menu))
    app.add_handler(CommandHandler("admin", admin_panel))

    # выбор предмета
    app.add_handler(CallbackQueryHandler(choose_subject_callback, pattern="^(" + "|".join(SUBJECTS) + ")$"))

    # получение контакта
    app.add_handler(MessageHandler(filters.CONTACT, phone_received))

    # кнопка 📚 Материалы
    app.add_handler(MessageHandler(filters.Regex("^📚 Материалы$"), materials_menu))

    # загрузка материалов
    app.add_handler(CallbackQueryHandler(send_material_file, pattern=r"^material\|"))

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

