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
    InputFile,
    ReplyKeyboardRemove
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

# --- Google Sheets запись ---
def write_to_sheet(username, phone, subject):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    sheet.append_row([username or "—", phone, subject])

# --- Старт ---
@typing_action
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(data["nominative"], callback_data=subject)] for subject, data in SUBJECTS.items()]
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

# --- Выбор предмета ---
@typing_action
async def choose_subject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data.strip()
    user_id = update.effective_user.id

    users_data[user_id] = {"username": query.from_user.username, "subject": subject}

    # Запрос телефона всегда
    reply_markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить контакт", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True
    )
    await query.message.reply_text(
        f"Ты выбрал {SUBJECTS[subject]['accusative']} ✅\nТеперь отправь свой контакт:",
        reply_markup=reply_markup
    )

# --- Получение телефона ---
@typing_action
async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.effective_user.id

    if user_id not in users_data or "subject" not in users_data[user_id]:
        await update.message.reply_text("❌ Сначала выбери предмет через /start.")
        return

    phone_number = contact.phone_number
    subject = users_data[user_id]["subject"]
    username = users_data[user_id].get("username")

    # Удаляем клавиатуру
    await update.message.reply_text("✅ Контакт получен!", reply_markup=ReplyKeyboardRemove())

    # Записываем в Google Sheets
    write_to_sheet(username, phone_number, subject)

    # Уведомляем админа
    notify_text = (
        f"🆕 Новая заявка!\n"
        f"👤 @{username or '—'}\n"
        f"📞 {phone_number}\n"
        f"📘 Предмет: {subject}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text)

    # Проверяем подписку
    subscribed = await is_subscribed(update, context, subject)
    if not subscribed:
        await update.message.reply_text(
            f"❌ Для получения материалов подпишись на {CHANNELS_BY_SUBJECT[subject]} и отправь контакт снова."
        )
        return

    await update.message.reply_text(
        f"✅ Отлично! Сейчас загружаю материалы по {SUBJECTS[subject]['accusative']}…"
    )

    # Отправка материалов с прогресс-баром
    await send_all_materials_with_progress(update, context, subject)

# --- Проверка подписки ---
async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str) -> bool:
    channel_username = CHANNELS_BY_SUBJECT.get(subject)
    try:
        member = await context.bot.get_chat_member(channel_username, update.effective_user.id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- Отправка всех материалов с прогресс-баром ---
async def send_all_materials_with_progress(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str):
    files = materials_files.get(subject, [])
    if not files:
        await update.message.reply_text("📂 Для этого предмета пока нет материалов.")
        return

    progress_msg = await update.message.reply_text("📦 Загружаю материалы… [░░░░░░░░░░] 0%")
    total = len(files)
    for i, (filename, filepath) in enumerate(files, start=1):
        # Прогресс-бар
        percent = int((i / total) * 100)
        filled = int(percent / 10)
        bar = "█" * filled + "░" * (10 - filled)
        try:
            await progress_msg.edit_text(f"📦 Загружаю материалы… [{bar}] {percent}%")
        except:
            pass

        # Отправка файла
        try:
            with open(filepath, "rb") as f:
                await update.message.reply_document(document=InputFile(f), filename=filename)
        except FileNotFoundError:
            await update.message.reply_text(f"❌ Файл {filename} не найден.")

        await asyncio.sleep(0.5)

    await progress_msg.edit_text("✅ Все материалы отправлены!")

# --- Админка ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    if username != ADMIN_USERNAME.strip("@"):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    # Здесь можешь добавить просмотр заявок

# --- Ошибки ---
async def error_handler(update, context):
    print(f"❌ Ошибка: {context.error}")

# --- Main ---
def main():
    keep_alive()
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(choose_subject_callback, pattern="^(" + "|".join(SUBJECTS.keys()) + ")$"))
    app.add_handler(MessageHandler(filters.CONTACT, phone_received))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_error_handler(error_handler)

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

    


