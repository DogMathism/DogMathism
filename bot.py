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
    MessageHandler, ContextTypes, filters, ConversationHandler
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Роли и состояния ---
ROLE, STUDENT_ACTION, SUBJECT_CHOICE, CLASS_INPUT, EXAM_PREP, NICKNAME_INPUT, PHONE_INPUT = range(7)

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
        data.get("exam_prep", "—")
    ]
    sheet.append_row(row)

# --- /start ---
@typing_action
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    return ROLE

# --- Выбор роли ---
@typing_action
async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    users_data[user_id] = {"role": query.data.split("_")[1]}  # student, parent, university, teacher

    role = users_data[user_id]["role"]

    if role in ["student", "parent"]:
        keyboard = [
            [InlineKeyboardButton("Запись на занятия", callback_data="action_register")],
            [InlineKeyboardButton("Получить полезные материалы", callback_data="action_materials")]
        ]
        await query.message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))
        return STUDENT_ACTION
    elif role == "university":
        # Студент ВУЗа: сразу запись на биохимию, только никнейм
        users_data[user_id]["subject"] = "Биохимия"
        await query.message.reply_text("Введите ваш никнейм для записи на биохимию:")
        return NICKNAME_INPUT
    elif role == "teacher":
        await query.message.reply_text(f"Если Вы хотите работать у нас, свяжитесь с админом {ADMIN_USERNAME}")
        return ConversationHandler.END

# --- Выбор действия ученика/родителя ---
@typing_action
async def student_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    action = query.data.split("_")[1]  # register / materials
    users_data[user_id]["action"] = action

    if action == "register":
        # Список предметов (кроме биохимии)
        keyboard = [
            [InlineKeyboardButton(subj, callback_data=f"subject|{subj}")]
            for subj in SUBJECTS if subj != "Биохимия"
        ]
        await query.message.reply_text("Выберите предмет:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SUBJECT_CHOICE
    elif action == "materials":
        # Запрашиваем только класс и экзамен-подготовку
        await query.message.reply_text("Введите ваш класс (например, 9, 10, 11) или подготовка к ОГЭ/ЕГЭ:")
        return CLASS_INPUT

# --- Выбор предмета ---
@typing_action
async def choose_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    subject = query.data.split("|")[1]
    users_data[user_id]["subject"] = subject
    await query.message.reply_text("Введите ваш класс (например, 9, 10, 11) или подготовка к ОГЭ/ЕГЭ:")
    return CLASS_INPUT

# --- Ввод класса ---
@typing_action
async def class_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_data[user_id]["class"] = update.message.text
    await update.message.reply_text("Уточните, если подготовка к экзаменам: ОГЭ/ЕГЭ или оставьте пустым:")
    return EXAM_PREP

# --- Подготовка к экзамену ---
@typing_action
async def exam_prep_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_data[user_id]["exam_prep"] = update.message.text
    await update.message.reply_text("Введите ваш никнейм в Telegram:")
    return NICKNAME_INPUT

# --- Ввод никнейма ---
@typing_action
async def nickname_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_data[user_id]["nickname"] = update.message.text

    role = users_data[user_id]["role"]
    if role in ["student", "parent"]:
        # Запрос телефона
        await update.message.reply_text(
            "Отправьте ваш контакт:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Отправить контакт", request_contact=True)]],
                resize_keyboard=True, one_time_keyboard=True
            )
        )
        return PHONE_INPUT
    else:
        # Студент ВУЗа: сразу выдаем материалы
        await send_materials_menu(update, context, user_id)
        return ConversationHandler.END

# --- Ввод телефона ---
@typing_action
async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.effective_user.id
    users_data[user_id]["phone"] = contact.phone_number

    # Сохраняем в Google Sheets
    write_to_sheet(users_data[user_id])

    # Проверка подписки и выдача материалов
    await send_materials_menu(update, context, user_id)
    return ConversationHandler.END

# --- Проверка подписки ---
async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str) -> bool:
    channel_username = CHANNELS_BY_SUBJECT.get(subject)
    try:
        member = await context.bot.get_chat_member(channel_username, update.effective_user.id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- Показ материалов с кнопками ---
@typing_action
async def send_materials_menu(update, context, user_id):
    subject = users_data[user_id]["subject"]
    subscribed = await is_subscribed(update, context, subject)
    if not subscribed:
        await update.message.reply_text(
            f"❌ Подпишитесь на {CHANNELS_BY_SUBJECT[subject]} и попробуйте снова."
        )
        return

    files = materials_files.get(subject, [])
    if not files:
        await update.message.reply_text("📂 Для вашего предмета пока нет материалов.")
        return

    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"material|{subject}|{idx}")]
        for idx, (name, _) in enumerate(files)
    ]
    await update.message.reply_text(
        f"📚 Выберите материал по {SUBJECTS[subject]['accusative']}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Отправка материала с прогресс-баром ---
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

    files = materials_files.get(subject, [])
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
            except:
                pass

        with open(filepath, "rb") as f:
            await query.message.reply_document(document=InputFile(f), filename=filename)
        try:
            await progress_msg.delete()
        except:
            pass
    except FileNotFoundError:
        await query.message.reply_text("❌ Файл не найден на сервере.")
    except Exception as e:
        print(f"Ошибка send_material_file: {e}")
        await query.message.reply_text("❌ Произошла ошибка при подготовке материала.")

# --- Main ---
def main():
    keep_alive()
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ROLE: [CallbackQueryHandler(choose_role, pattern="^role_")],
            STUDENT_ACTION: [CallbackQueryHandler(student_action, pattern="^action_")],
            SUBJECT_CHOICE: [CallbackQueryHandler(choose_subject, pattern="^subject\|")],
            CLASS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, class_input)],
            EXAM_PREP: [MessageHandler(filters.TEXT & ~filters.COMMAND, exam_prep_input)],
            NICKNAME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, nickname_input)],
            PHONE_INPUT: [MessageHandler(filters.CONTACT, phone_input)],
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(send_material_file, pattern=r"^material\|"))

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

    


