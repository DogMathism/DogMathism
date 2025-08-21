import os
import asyncio
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
    ConversationHandler,
    ContextTypes,
    filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Состояния ---
CHOOSING_SUBJECT, ASK_PHONE, MATERIALS_MENU = range(3)

# --- Предметы ---
SUBJECTS = ["Математика", "Физика", "Химия", "Биология", "Русский", "Биохимия"]

# --- Админ ---
ADMIN_USERNAMES = ["dogmathism_admin"]
ADMIN_ID = 7972251746

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

# --- Команды ---
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
        "💬 Вопросы и запись - @DogWarts_admin\n\n"
        "Выбирай предмет и начни свой путь к успеху 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_SUBJECT

async def subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data
    user_id = query.from_user.id

    # если уже есть телефон → сразу даём материалы
    if user_id in users_data and "phone" in users_data[user_id]:
        users_data[user_id]["subject"] = subject
        await query.message.reply_text(f"✅ Ты выбрал {subject}! 📚")
        return await materials_menu(update, context)

    # если телефона ещё нет → стандартный сценарий
    users_data[user_id] = {
        "username": query.from_user.username,
        "subject": subject
    }
    reply_markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить контакт", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True
    )
    await query.message.reply_text("Пожалуйста, отправь свой тг:", reply_markup=reply_markup)
    return ASK_PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.message.from_user.id
    phone_number = contact.phone_number
    users_data[user_id]["phone"] = phone_number
    username = users_data[user_id].get("username")
    subject = users_data[user_id]["subject"]

    write_to_sheet(username, phone_number, subject)

    notify_text = (
        f"🆕 Новая заявка!\n"
        f"👤 @{username or '—'}\n"
        f"📞 {phone_number}\n"
        f"📘 Предмет: {subject}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text)

    await update.message.reply_text(
        f"✅ Ты записан на {subject}! 📚 Напиши /materials, чтобы получить материалы.",
        reply_markup=ReplyKeyboardMarkup([["/materials"]], resize_keyboard=True)
    )
    return ConversationHandler.END

async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str) -> bool:
    channel_username = CHANNELS_BY_SUBJECT.get(subject)
    if not channel_username:
        return True
    try:
        member = await context.bot.get_chat_member(channel_username, update.effective_user.id)
        return member.status in ["member", "creator", "administrator"]
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

async def send_material_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    if len(data) != 3:
        await query.message.reply_text("Ошибка обработки запроса.")
        return
    _, subject, idx_str = data
    idx = int(idx_str)

    files = materials_files.get(subject)
    if not files or idx >= len(files):
        await query.message.reply_text("Материал не найден.")
        return

    filename, filepath = files[idx]

    try:
        await query.message.reply_chat_action("typing")  
        await asyncio.sleep(1.5)  
        await query.message.reply_text("Вот твой материал 👇")

        with open(filepath, "rb") as f:
            await query.message.reply_document(document=InputFile(f), filename=filename)
    except FileNotFoundError:
        await query.message.reply_text("Файл с материалом не найден на сервере.")

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
            f"❌ Для получения материалов подпишись на наш канал {CHANNELS_BY_SUBJECT.get(subject, 'канал')} и попробуй снова."
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
    keyboard.append([InlineKeyboardButton("🔙 Выбрать другой предмет", callback_data="choose_subject")])

    await update.message.reply_text(
        f"📚 Выбери материал по {subject}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MATERIALS_MENU

async def back_to_subjects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await start(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    if username not in ADMIN_USERNAMES:
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

def main():
    keep_alive()
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_SUBJECT: [CallbackQueryHandler(subject_chosen)],
            ASK_PHONE: [MessageHandler(filters.CONTACT, phone_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("materials", materials_menu))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_handler(CallbackQueryHandler(send_material_file, pattern=r"^material\|"))
    app.add_handler(CallbackQueryHandler(back_to_subjects, pattern="^choose_subject$"))

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
