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

# --- Предметы с падежами ---
SUBJECTS = {
    "Математика": {"nominative": "Математика", "accusative": "математику", "prepositional": "математике"},
    "Физика": {"nominative": "Физика", "accusative": "физику", "prepositional": "физике"},
    "Химия": {"nominative": "Химия", "accusative": "химию", "prepositional": "химии"},
    "Биология": {"nominative": "Биология", "accusative": "биологию", "prepositional": "биологии"},
    "Русский": {"nominative": "Русский язык", "accusative": "русский язык", "prepositional": "русском языке"},
    "Биохимия": {"nominative": "Биохимия", "accusative": "биохимию", "prepositional": "биохимии"}
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
    keyboard = [[InlineKeyboardButton(data["nominative"], callback_data=subject)] for subject, data in SUBJECTS.items()]
    await update.message.reply_text(
        "👋 Добро пожаловать в <b>DogWarts</b> — школа, где знания сильнее магии!\n\n"
        "📚 Доступные предметы:\n\n"
        "🧠 Математика - @DogMathic\n"
        "🧪 Химия - @DogChemik\n"
        "⚛️ Биохимия - @DogBioChemik\n"
        "📖 Русский язык - @DogRussik\n"
        "🌿 Биология - @DogBio\n"
        "⚙️ Физика - @DogPhysic\n\n"
        f"💬 Вопросы и запись — {ADMIN_USERNAME}\n\n"
        "Выбирай предмет 👇",
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

    users_data.setdefault(user_id, {"username": query.from_user.username})
    users_data[user_id]["subject"] = subject

    if "phone" in users_data[user_id]:
        await query.message.reply_text(f"✅ ты выбрал {SUBJECTS[subject]['accusative']} 📚")
        await materials_menu(update, context)
    else:
        reply_markup = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Отправить контакт", request_contact=True)]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
        await query.message.reply_text("Пожалуйста, отправь свой контакт:", reply_markup=reply_markup)

# --- Получение контакта ---
@typing_action
async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.effective_user.id
    if user_id not in users_data or "subject" not in users_data[user_id]:
        await update.message.reply_text("❌ Сначала выбери предмет командой /start.")
        return

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
        f"✅ ты записан на {SUBJECTS[subject]['accusative']} 📚\n"
        "Сейчас покажу доступные материалы 👇",
        reply_markup=ReplyKeyboardMarkup([["📂 материалы"]], resize_keyboard=True)
    )

    # Автоматически показываем материалы
    await materials_menu(update, context)

# --- Проверка подписки ---
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

# --- Меню материалов ---
@typing_action
async def materials_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = users_data.get(user_id)
    if not user_info or "subject" not in user_info or "phone" not in user_info:
        await update.message.reply_text("😕 Сначала выбери предмет и отправь контакт (/start).")
        return

    subject = user_info["subject"]

    try:
        subscribed = await is_subscribed(update, context, subject)
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        subscribed = False

    if not subscribed:
        await update.message.reply_text(
            f"❌ Для получения материалов подпишись на канал {CHANNELS_BY_SUBJECT.get(subject, 'канал')} и попробуй снова."
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
        f"📚 Выбери материал по {SUBJECTS[subject]['prepositional']}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Отправка материалов с прогресс-баром в одном сообщении ---
@typing_action
async def send_material_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, subject, idx_str = query.data.split("|")
        idx = int(idx_str)
    except Exception:
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
            try:
                await progress_msg.edit_text(f"Готовлю твой материал… [{bar}] {percent}%")
            except Exception:
                pass

        with open(filepath, "rb") as f:
            await query.message.reply_document(document=InputFile(f), filename=filename)

        try:
            await progress_msg.delete()
        except Exception:
            pass

    except FileNotFoundError:
        await query.message.reply_text("❌ Файл не найден на сервере.")
    except Exception as e:
        print(f"Ошибка send_material_file: {e}")
        await query.message.reply_text("❌ Произошла ошибка при подготовке материала.")

# --- Админка ---
@typing_action
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    if username != ADMIN_USERNAME.strip("@"):
        await update.message.reply_text("⛔ у вас нет доступа.")
        return
    entries = read_all_entries()
    if not entries:
        await update.message.reply_text("📭 пока нет заявок.")
        return
    text = "📋 Заявки учеников:\n"
    for row in entries:
        text += f"👤 @{row[0]} 📞 {row[1]} 📘 {row[2]}\n"
    await update.message.reply_text(text)

# --- Ошибки ---
async def error_handler(update, context):
    print(f"❌ Ошибка: {context.error}")
    if update:
        try:
            if update.message:
                await update.message.reply_text("Произошла ошибка, попробуйте снова.")
            elif update.callback_query:
                await update.callback_query.message.reply_text("Произошла ошибка, попробуйте снова.")
        except:
            pass

# --- Main ---
def main():
    keep_alive()
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, phone_received))
    app.add_handler(MessageHandler(filters.Regex("^(📂 материалы)$"), materials_menu))
    app.add_handler(CallbackQueryHandler(choose_subject_callback, pattern="^(" + "|".join(SUBJECTS.keys()) + ")$"))
    app.add_handler(CallbackQueryHandler(send_material_file, pattern=r"^material\|"))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_error_handler(error_handler)

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

    


