import os
import asyncio
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
)
from keep_alive import keep_alive
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google-credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("DogWarts_Requests").sheet1

# --- Настройки ---
ADMIN_ID = os.getenv("ADMIN_ID")

materials_files = {
    "Математика": [("Алгебра.pdf", "materials/math/algebra.pdf")],
    "Химия": [("Химия.pdf", "materials/chemistry/chemistry.pdf")],
    "Биология": [("Биология.pdf", "materials/biology/biology.pdf")],
    "Физика": [("Физика.pdf", "materials/physics/physics.pdf")],
    "Русский язык": [("Русский.pdf", "materials/russian/russian.pdf")],
    "Биохимия": [("Биохимия.pdf", "materials/biochem/biochemistry.pdf")]
}

CHANNELS_BY_SUBJECT = {
    "Математика": "@DogMathic",
    "Химия": "@DogChemik",
    "Биология": "@DogBio",
    "Физика": "@DogPhysic",
    "Русский язык": "@DogRussik",
    "Биохимия": "@DogBioChemik"
}

users_data = {}

# --- Вспомогательные функции ---
async def typing_action(func):
    async def wrapper(update, context, *args, **kwargs):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        return await func(update, context, *args, **kwargs)
    return wrapper

def write_to_sheet(data):
    try:
        sheet.append_row([data.get("role"), data.get("nickname"), data.get("phone", "-"),
                          data.get("class", "-"), data.get("subject", "-")])
    except Exception as e:
        print(f"Ошибка записи в Google Sheets: {e}")

async def check_subscription(update, context, subject):
    channel_username = CHANNELS_BY_SUBJECT.get(subject)
    if not channel_username:
        return True
    try:
        member = await context.bot.get_chat_member(channel_username, update.effective_user.id)
        return member.status in ["member", "creator", "administrator"]
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

async def return_to_role_selection(update):
    user_id = update.effective_user.id
    users_data[user_id]["step"] = "role"
    keyboard = [
        [InlineKeyboardButton("Ученик", callback_data="role_student")],
        [InlineKeyboardButton("Родитель", callback_data="role_parent")],
        [InlineKeyboardButton("Студент ВУЗа", callback_data="role_university")],
        [InlineKeyboardButton("Преподаватель", callback_data="role_teacher")]
    ]
    await asyncio.sleep(1)
    await update.callback_query.message.reply_text(
        "Выберите вашу роль, чтобы пройти другой сценарий:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Handlers ---
@typing_action
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_data[user_id] = {"step": "role"}
    await update.message.reply_text(
        "👋 **Добро пожаловать в DogWarts** – школу, где знания сильнее магии\n\n"
        "Выберите вашу роль:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Ученик", callback_data="role_student")],
            [InlineKeyboardButton("Родитель", callback_data="role_parent")],
            [InlineKeyboardButton("Студент ВУЗа", callback_data="role_university")],
            [InlineKeyboardButton("Преподаватель", callback_data="role_teacher")]
        ]),
        parse_mode="Markdown"
    )

async def choose_role(update: Update, context):
    query = update.callback_query
    await query.answer()
    role = query.data.replace("role_", "")
    user_id = update.effective_user.id
    users_data[user_id]["role"] = role

    if role == "student":
        keyboard = [
            [InlineKeyboardButton("Запись на занятия", callback_data="action_register")],
            [InlineKeyboardButton("Полезные материалы", callback_data="action_materials")]
        ]
        await query.message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif role == "parent":
        await query.message.reply_text("Выберите предмет для записи:",
                                       reply_markup=subjects_keyboard(exclude=["Биохимия"]))
    elif role == "university":
        await query.message.reply_text("Доступна запись на предмет Биохимия:",
                                       reply_markup=subjects_keyboard(only=["Биохимия"]))
    else:
        await query.message.reply_text("Если Вы хотите работать у нас, свяжитесь с админом: @DogWarts_admin")

def subjects_keyboard(exclude=None, only=None):
    subjects = [s for s in materials_files.keys() if (not exclude or s not in exclude)]
    if only:
        subjects = [s for s in subjects if s in only]
    return InlineKeyboardMarkup([[InlineKeyboardButton(s, callback_data=f"subject|{s}")] for s in subjects])

async def student_action(update, context):
    query = update.callback_query
    await query.answer()
    action = query.data.replace("action_", "")
    user_id = update.effective_user.id
    users_data[user_id]["action"] = action

    if action == "register":
        await query.message.reply_text("Выберите предмет:", reply_markup=subjects_keyboard(exclude=["Биохимия"]))
    else:
        await query.message.reply_text("Выберите предмет для материалов:", reply_markup=subjects_keyboard())

async def choose_subject(update, context):
    query = update.callback_query
    await query.answer()
    _, subject = query.data.split("|")
    user_id = update.effective_user.id
    users_data[user_id]["subject"] = subject

    await query.message.reply_text("Введите ваш никнейм (@username):")
    users_data[user_id]["step"] = "nickname"

async def nickname_input(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    users_data[user_id]["nickname"] = text

    role = users_data[user_id].get("role")
    action = users_data[user_id].get("action", "")

    if role in ["student", "parent"] and action == "register":
        # Запрос телефона
        button = KeyboardButton("📱 Отправить номер телефона", request_contact=True)
        await update.message.reply_text("Отправьте ваш номер телефона:", reply_markup=ReplyKeyboardMarkup([[button]], resize_keyboard=True))
        users_data[user_id]["step"] = "phone"
    else:
        await save_and_send_materials(update, context)

async def phone_input(update, context):
    user_id = update.effective_user.id
    contact = update.message.contact
    users_data[user_id]["phone"] = contact.phone_number
    await update.message.reply_text("Спасибо! Теперь подготовлю материалы…", reply_markup=ReplyKeyboardRemove())
    await save_and_send_materials(update, context)

async def save_and_send_materials(update, context):
    user_id = update.effective_user.id
    data = users_data[user_id]
    write_to_sheet(data)

    # Уведомление админу
    notify_text = (
        f"🆕 Новая заявка!\n"
        f"👤 {data.get('nickname')}\n"
        f"📞 {data.get('phone', '-')}\n"
        f"📘 {data.get('subject')}\n"
        f"🎓 Роль: {data.get('role')}"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text)
    except Exception as e:
        print(f"Ошибка уведомления админу: {e}")

    # Проверка подписки
    subscribed = await check_subscription(update, context, data.get("subject"))
    if not subscribed:
        await update.message.reply_text(f"❌ Подпишитесь на канал {CHANNELS_BY_SUBJECT[data.get('subject')]} для получения материалов!")
        return

    # Отправка материалов с прогресс-баром
    await send_materials_menu(update, context, user_id)
    await return_to_role_selection(update)

async def send_materials_menu(update, context, user_id):
    subject = users_data[user_id]["subject"]
    files = materials_files.get(subject)
    if files:
        keyboard = [[InlineKeyboardButton(name, callback_data=f"material|{subject}|{idx}")]
                    for idx, (name, _) in enumerate(files)]
        await update.message.reply_text(f"📚 Выберите материал по {subject}:", reply_markup=InlineKeyboardMarkup(keyboard))

async def send_material_file(update, context):
    query = update.callback_query
    await query.answer()
    _, subject, idx_str = query.data.split("|")
    idx = int(idx_str)
    files = materials_files.get(subject)
    if not files or idx >= len(files):
        await query.message.reply_text("❌ Файл не найден.")
        return
    filename, filepath = files[idx]
    progress_msg = await query.message.reply_text("Готовлю материал… [░░░░░░░░░░] 0%")
    total_steps = 10
    for step in range(1, total_steps + 1):
        await asyncio.sleep(0.3)
        bar = "█" * step + "░" * (total_steps - step)
        await progress_msg.edit_text(f"Готовлю материал… [{bar}] {step*10}%")
    with open(filepath, "rb") as f:
        await query.message.reply_document(document=InputFile(f), filename=filename)
    await progress_msg.delete()

# --- Main ---
def main():
    keep_alive()
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(choose_role, pattern="^role_"))
    app.add_handler(CallbackQueryHandler(student_action, pattern="^action_"))
    app.add_handler(CallbackQueryHandler(choose_subject, pattern="^subject\|"))
    app.add_handler(CallbackQueryHandler(send_material_file, pattern="^material\|"))
    app.add_handler(MessageHandler(filters.CONTACT, phone_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nickname_input))

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

    


