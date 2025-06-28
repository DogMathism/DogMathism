from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
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

# === Константы === #
CHOOSING_SUBJECT, ASK_PHONE = range(2)
SUBJECTS = ["Математика", "Русский", "Химия", "Физика", "Биология"]
ADMIN_USERNAMES = ["your_admin_username"]  # Замените на ваш Telegram username без @
GOOGLE_SHEET_NAME = "Название_вашей_таблицы"  # Замените на имя вашей Google таблицы
CREDENTIALS_FILE = "credentials.json"  # Файл ключей от Google API

# === Временное хранилище данных пользователей === #
users_data = {}

# === Функции Google Sheets === #
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
    return sheet.get_all_values()[1:]  # без заголовков

# === Обработчики === #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(subject, callback_data=subject)] for subject in SUBJECTS
    ]
    await update.message.reply_text(
        "👋 Привет! На какой предмет ты хочешь записаться?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_SUBJECT

async def subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data
    user_id = query.from_user.id

    users_data[user_id] = {
        "username": query.from_user.username,
        "subject": subject
    }

    reply_markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить номер", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True
    )

    await query.message.reply_text("Пожалуйста, отправь свой номер телефона:", reply_markup=reply_markup)
    return ASK_PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.message.from_user.id
    phone_number = contact.phone_number

    users_data[user_id]["phone"] = phone_number

    write_to_sheet(
        users_data[user_id].get("username"),
        users_data[user_id]["phone"],
        users_data[user_id]["subject"]
    )

    await update.message.reply_text(
        f"✅ Ты записан на {users_data[user_id]['subject']}!
📚 Напиши /materials, чтобы получить материалы.",
        reply_markup=ReplyKeyboardMarkup([["/materials"]], resize_keyboard=True)
    )
    return ConversationHandler.END

async def send_materials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    user_subject = None

    for user in users_data.values():
        if user.get("username") == username:
            user_subject = user.get("subject")
            break

    if not user_subject:
        await update.message.reply_text("😕 Ты ещё не записан. Напиши /start.")
        return

    materials = {
        "Математика": "📘 Материалы по математике: https://example.com/math",
        "Русский": "📙 Материалы по русскому языку: https://example.com/russian",
        "Химия": "⚗️ Материалы по химии: https://example.com/chemistry",
        "Физика": "📗 Материалы по физике: https://example.com/physics",
        "Биология": "🧬 Материалы по биологии: https://example.com/biology"
    }

    await update.message.reply_text(materials.get(user_subject, "Материалы не найдены."))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    if username not in ADMIN_USERNAMES:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    entries = read_all_entries()
    if not entries:
        await update.message.reply_text("📭 Пока нет заявок.")
        return

    text = "📋 Заявки учеников:

"
    for row in entries:
        text += f"👤 @{row[0]}
📞 {row[1]}
📘 {row[2]}

"

    await update.message.reply_text(text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token("ВАШ_ТОКЕН_ОТ_BOTFATHER").build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_SUBJECT: [CallbackQueryHandler(subject_chosen)],
            ASK_PHONE: [MessageHandler(filters.CONTACT, phone_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("materials", send_materials))
    app.add_handler(CommandHandler("admin", admin_panel))

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()