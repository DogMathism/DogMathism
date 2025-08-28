import os
import asyncio
from functools import wraps
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pytz  # нужно установить: pip install pytz

# ================== НАСТРОЙКИ ==================

# Админ
ADMIN_ID = 7972251746  # int
ADMIN_USERNAME = "@dogwarts_admin"

# Google Sheets
GOOGLE_SHEET_NAME = "DogMathism"
CREDENTIALS_FILE = "credentials.json"

# Каналы по предметам
CHANNELS_BY_SUBJECT = {
    "Математика": "@DogMathic",
    "Физика": "@DogPhysic",
    "Химия": "@DogChemik",
    "Биология": "@DogBio",
    "Русский": "@DogRussik",
    "Биохимия": "@DogBioChemik",
}

# Материалы (название, путь к файлу)
materials_files = {
    "Математика": [("Свойства окружности.pdf", "materials/math/Circle.pdf"),
                   ("Гайд векторы.pdf", "materials/math/Vectors.pdf")],
    "Физика": [("Основы механики.pdf", "materials/physics_mechanics.pdf")],
    "Химия": [("Таблица Менделеева.pdf", "materials/chem_periodic_table.pdf")],
    "Биология": [("Клеточная биология.pdf", "materials/bio_cell_biology.pdf")],
    "Русский": [("Правила орфографии.pdf", "materials/rus_orthography_rules.pdf")],
    "Биохимия": [("Аминокислоты.pdf", "materials/biochem/Аминокислоты.pdf"),
                 ("Полипептиды.pdf", "materials/biochem/Полипептиды.pdf")],
}

# Служебное состояние пользователей
users_data = {}

# ================== УТИЛИТЫ ==================

def typing_action(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except:
                pass
        await asyncio.sleep(0.2)
        return await func(update, context, *args, **kwargs)
    return wrapped

def write_to_sheet(row_dict: dict):
    """Пишем строку в Google Sheets."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        row = [
            row_dict.get("timestamp", "-"),
            row_dict.get("role", "-"),
            row_dict.get("action", "-"),
            row_dict.get("subject", "-"),
            row_dict.get("class", "-"),
            row_dict.get("nickname", "-"),
            row_dict.get("phone", "-"),
            str(row_dict.get("user_id", "-")),
        ]
        sheet.append_row(row)
    except Exception as e:
        print(f"[Sheets] Ошибка записи: {e}")

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text)
    except Exception as e:
        print(f"[Admin] Ошибка отправки админу: {e}")

def subjects_keyboard(exclude=None, only=None):
    subjects_all = list(materials_files.keys())
    if exclude:
        subjects = [s for s in subjects_all if s not in exclude]
    elif only:
        subjects = [s for s in subjects_all if s in only]
    else:
        subjects = subjects_all
    rows = [[InlineKeyboardButton(s, callback_data=f"subject|{s}")] for s in subjects]
    return InlineKeyboardMarkup(rows)

def class_keyboard():
    rows = [
        [InlineKeyboardButton("5", callback_data="class|5"),
         InlineKeyboardButton("6", callback_data="class|6")],
        [InlineKeyboardButton("7", callback_data="class|7"),
         InlineKeyboardButton("8", callback_data="class|8")],
        [InlineKeyboardButton("10", callback_data="class|10")],
        [InlineKeyboardButton("Подготовка к ОГЭ", callback_data="class|OGE"),
         InlineKeyboardButton("Подготовка к ЕГЭ", callback_data="class|EGE")],
    ]
    return InlineKeyboardMarkup(rows)

async def check_subscription(context: ContextTypes.DEFAULT_TYPE, user_id: int, subject: str) -> bool:
    channel = CHANNELS_BY_SUBJECT.get(subject)
    if not channel:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ("member", "creator", "administrator")
    except Exception as e:
        print(f"[Subscribe] Ошибка проверки ({channel}): {e}")
        return False

async def reply(update: Update, text: str, **kwargs):
    """Удобная отправка в текущий поток (message или callback)."""
    if update.message:
        return await update.message.reply_text(text, **kwargs)
    elif update.callback_query:
        return await update.callback_query.message.reply_text(text, **kwargs)

def get_username(update: Update) -> str:
    uname = update.effective_user.username
    if uname:
        if not uname.startswith("@"):
            uname = f"@{uname}"
        return uname
    return ""  # нет username — попросим ввести вручную

# ================== ХЕНДЛЕРЫ ==================

# /start
@typing_action
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_data[user_id] = {"step": "role"}  # сброс сценария
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ученик", callback_data="role|student")],
        [InlineKeyboardButton("Родитель", callback_data="role|parent")],
        [InlineKeyboardButton("Студент ВУЗа", callback_data="role|university")],
        [InlineKeyboardButton("Преподаватель", callback_data="role|teacher")],
    ])
    await update.message.reply_text(
        "👋 Добро пожаловать в <b>DogWarts</b> - <b>школу</b>, где знания сильнее <b>магии</b>\n\n"
        "А пока подпишись на наши каналы, чтобы получить <b>бесплатные материалы:</b>\n\n"
        "🧠 Математика - @DogMathic\n"
        "🧪 Химия - @DogChemik\n"
        "⚛️ Биохимия - @DogBioChemik\n"
        "📖 Русский язык - @DogRussik\n"
        "🌿 Биология - @DogBio\n"
        "⚙️ Физика - @DogPhysic\n\n"
        "💬 По любому вопросу всегда можешь обратиться к <b>нашему менеджеру</b> - @DogWarts_admin\n\n"
        "<b>Начни свой путь к успеху</b> 👇\n\n",
        parse_mode="HTML",
        reply_markup=kb
    )

# Выбор роли
@typing_action
async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    role = q.data.split("|")[1]  # student / parent / university / teacher
    users_data[user_id] = {"step": None, "role": role, "user_id": user_id}

    if role == "teacher":
        await q.message.reply_text(f"Если вы хотите работать у нас, свяжитесь с админом: {ADMIN_USERNAME}")
        await return_to_role_selection(update)
        return

    if role == "university":
        # Студент ВУЗа: только биохимия, без телефона/класса
        users_data[user_id]["action"] = "register"  # по сути запись на биохимию
        users_data[user_id]["subject"] = "Биохимия"
        await ensure_nickname_then_continue(update, context, need_class=False, need_phone=False)
        return

    if role == "parent":
        # Только запись
        users_data[user_id]["action"] = "register"
        await q.message.reply_text("Выберите предмет:", reply_markup=subjects_keyboard(exclude=["Биохимия"]))
        return

    if role == "student":
        # Выбор действия
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Запись на занятия", callback_data="action|register")],
            [InlineKeyboardButton("Получить полезные материалы", callback_data="action|materials")],
        ])
        await q.message.reply_text("Выберите действие:", reply_markup=kb)
        return

# Действия ученика
@typing_action
async def student_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    action = q.data.split("|")[1]  # register / materials
    users_data[user_id]["action"] = action

    if action == "register":
        await q.message.reply_text("Выберите предмет:", reply_markup=subjects_keyboard(exclude=["Биохимия"]))
    else:
        await q.message.reply_text("Выберите предмет для материалов:", reply_markup=subjects_keyboard())

# Выбор предмета
@typing_action
async def choose_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    subject = q.data.split("|")[1]
    users_data[user_id]["subject"] = subject

    role = users_data[user_id].get("role")
    action = users_data[user_id].get("action")

    # Требования по сбору данных:
    # - Запись (student/parent): НИК + КЛАСС + ТЕЛЕФОН
    # - Материалы (student): НИК + КЛАСС, телефон не нужен
    if role in ("student", "parent") and action == "register":
        await ensure_nickname_then_continue(update, context, need_class=True, need_phone=True)
    elif role == "student" and action == "materials":
        await ensure_nickname_then_continue(update, context, need_class=True, need_phone=False)
    elif role == "university":
        # сюда обычно не попадем, но на всякий случай
        await ensure_nickname_then_continue(update, context, need_class=False, need_phone=False)
    else:
        await ensure_nickname_then_continue(update, context, need_class=False, need_phone=False)

# --- СБОР НИКНЕЙМА / КЛАССА / ТЕЛЕФОНА ---

async def ensure_nickname_then_continue(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                        need_class: bool, need_phone: bool):
    user_id = update.effective_user.id
    # Попробуем взять username
    username = get_username(update)
    if username:
        users_data[user_id]["nickname"] = username
        if need_class:
            users_data[user_id]["next_need_phone"] = need_phone
            await ask_class(update)
        else:
            if need_phone:
                await ask_phone(update)
            else:
                await finalize_and_materials(update, context)
    else:
        # Просим никнейм текстом
        users_data[user_id]["step"] = "nickname"
        await reply(update, "Введите ваш никнейм (в формате @username):")

@typing_action
async def nickname_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Обрабатываем только если ждём ник
    if users_data.get(user_id, {}).get("step") != "nickname":
        return
    text = (update.message.text or "").strip()
    if not text.startswith("@") or len(text) < 2:
        await update.message.reply_text("Пожалуйста, пришлите ник в формате @username.")
        return
    users_data[user_id]["nickname"] = text
    users_data[user_id]["step"] = None

    # Определяем, что дальше нужно
    role = users_data[user_id].get("role")
    action = users_data[user_id].get("action")
    if role in ("student", "parent") and action == "register":
        # Нужен класс + телефон
        users_data[user_id]["next_need_phone"] = True
        await ask_class(update)
    elif role == "student" and action == "materials":
        # Нужен только класс
        users_data[user_id]["next_need_phone"] = False
        await ask_class(update)
    else:
        # Студент ВУЗа / прочее — без класса/телефона
        await finalize_and_materials(update, context)

async def ask_class(update: Update):
    await reply(update, "Выберите класс:", reply_markup=class_keyboard())

@typing_action
async def class_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    choice = q.data.split("|")[1]  # 5/6/7/8/10/OGE/EGE
    users_data[user_id]["class"] = choice

    need_phone = users_data[user_id].pop("next_need_phone", False)
    if need_phone:
        await ask_phone(update)
    else:
        await finalize_and_materials(update, context)

async def ask_phone(update: Update):
    users_data[update.effective_user.id]["step"] = "phone"
    kb = ReplyKeyboardMarkup([[KeyboardButton("📱 Отправить контакт", request_contact=True)]],
                             resize_keyboard=True, one_time_keyboard=True)
    await reply(update, "Отправьте ваш номер телефона:", reply_markup=kb)

@typing_action
async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if users_data.get(user_id, {}).get("step") != "phone":
        return
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Пожалуйста, отправьте контакт кнопкой ниже.")
        return
    users_data[user_id]["phone"] = contact.phone_number
    users_data[user_id]["step"] = None
    await update.message.reply_text("Спасибо!", reply_markup=ReplyKeyboardRemove())
    await finalize_and_materials(update, context)

# --- ФИНАЛ: СОХРАНЕНИЕ + ПОДПИСКА + МЕНЮ МАТЕРИАЛОВ ---

async def finalize_and_materials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = users_data.get(user_id, {}).copy()
    data.setdefault("subject", "-")
    data.setdefault("class", "-")
    data.setdefault("phone", "-")
    data.setdefault("role", "-")
    data.setdefault("action", "-")
    tz = pytz.timezone("Europe/Moscow")
    now = datetime.datetime.now(tz)
    timestamp_for_sheets = now.strftime("%Y-%m-%d %H:%M:%S")  # ISO для Google Sheets
    timestamp_for_admin = now.strftime("%d.%m.%Y %H:%M")      # Красиво для сообщения
    data["timestamp"] = timestamp_for_sheets


    # Пишем в Google Sheets
    await asyncio.to_thread(write_to_sheet, {
        "timestamp": timestamp_for_sheets,
        "role": data["role"],
        "action": data["action"],
        "subject": data["subject"],
        "class": data["class"],
        "nickname": data.get("nickname", "-"),
        "phone": data.get("phone", "-"),
        "user_id": user_id
    })

    # Уведомление админу
    note = (
        "🆕 Новая заявка/запрос материалов\n"
        f"📅 Время: {timestamp_for_admin}\n"
        f"🎓 Роль: {data['role']}\n"
        f"🧩 Действие: {data['action']}\n"
        f"📘 Предмет: {data['subject']}\n"
        f"🧑‍🎓 Класс/подготовка: {data['class']}\n"
        f"👤 Ник: {data.get('nickname', '-')}\n"
        f"📞 Телефон: {data.get('phone', '-')}\n"
        f"🆔 ID: {user_id}"
    )
    await notify_admin(context, note)

    # Проверка подписки на канал предмета — перед показом материалов
    subject = data["subject"]
    if subject and subject in CHANNELS_BY_SUBJECT:
        subscribed = await check_subscription(context, user_id, subject)
        if not subscribed:
            keyboard = [
                    [InlineKeyboardButton("✅ Проверить подписку", callback_data=f"check_sub_{subject}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await reply(
                update,
                f"❌ Для получения материалов подпишитесь на канал {CHANNELS_BY_SUBJECT[subject]} и попробуйте снова.",
                reply_markup=reply_markup
            )
            
            return

    # Показ меню материалов по предмету
    await send_materials_menu(update, context, subject)

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    subject = query.data.replace("check_sub_", "")
    
       # Имитация прогресса проверки
    progress = await query.message.reply_text("Проверяю подписку… [░░░░░░░░░░] 0%")
    total = 10
    for step in range(1, total + 1):
        await asyncio.sleep(0.2)  # скорость "анимации"
        bar = "█" * step + "░" * (total - step)
        await progress.edit_text(f"Проверяю подписку… [{bar}] {step*10}%")

    subscribed = await check_subscription(context, user_id, subject)
    
    try:
        await progress.delete()  # удаляем сообщение прогресса
    except:
        pass
        
    if subscribed:
        await query.edit_message_text("✅ Подписка подтверждена! Вот ваши материалы:")
        await send_materials_menu(update, context, subject)
    else:
        keyboard = [
            [InlineKeyboardButton("✅ Проверить подписку", callback_data=f"check_sub_{subject}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"❌ Вы всё ещё не подписаны на {CHANNELS_BY_SUBJECT[subject]}.\n"
            "Подпишитесь и нажмите кнопку ещё раз.",
            reply_markup=reply_markup
        )


async def send_materials_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str):
    files = materials_files.get(subject, [])
    if not files:
        await reply(update, "📂 Для выбранного предмета пока нет материалов.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(name, callback_data=f"material|{subject}|{i}")]
        for i, (name, _) in enumerate(files)
    ])
    await reply(update, f"📚 Выберите материал по {subject}:", reply_markup=kb)

@typing_action
async def send_material_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, subject, idx_str = q.data.split("|")
        idx = int(idx_str)
    except Exception:
        await q.message.reply_text("❌ Ошибка обработки запроса.")
        return

    files = materials_files.get(subject, [])
    if idx >= len(files):
        await q.message.reply_text("❌ Материал не найден.")
        return

    filename, filepath = files[idx]
    try:
        progress = await q.message.reply_text("Готовлю материал… [░░░░░░░░░░] 0%")
        total = 10
        for step in range(1, total + 1):
            await asyncio.sleep(0.25)
            bar = "█" * step + "░" * (total - step)
            await progress.edit_text(f"Готовлю материал… [{bar}] {step*10}%")
        with open(filepath, "rb") as f:
            await q.message.reply_document(document=InputFile(f), filename=filename)
        try:
            await progress.delete()
        except:
            pass

    except FileNotFoundError:
        await q.message.reply_text("❌ Файл не найден на сервере.")
    except Exception as e:
        print(f"[Material] Ошибка: {e}")
        await q.message.reply_text("❌ Произошла ошибка при подготовке материала.")
        return

    # ✅ Возврат к выбору роли после успешного скачивания
    await return_to_role_selection(update)

# Возврат к выбору роли
async def return_to_role_selection(update: Update):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ученик", callback_data="role|student")],
        [InlineKeyboardButton("Родитель", callback_data="role|parent")],
        [InlineKeyboardButton("Студент ВУЗа", callback_data="role|university")],
        [InlineKeyboardButton("Преподаватель", callback_data="role|teacher")],
    ])
    await asyncio.sleep(0.6)
    await reply(update, "Можете выбрать другой сценарий:", reply_markup=kb)

# ================== MAIN ==================

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("❌ BOT_TOKEN не задан в переменных окружения.")
        return

    app = ApplicationBuilder().token(token).build()

    # Команды
    app.add_handler(CommandHandler("start", start))

    # Callback-кнопки
    app.add_handler(CallbackQueryHandler(choose_role, pattern=r"^role\|"))
    app.add_handler(CallbackQueryHandler(student_action, pattern=r"^action\|"))
    app.add_handler(CallbackQueryHandler(choose_subject, pattern=r"^subject\|"))
    app.add_handler(CallbackQueryHandler(class_choice, pattern=r"^class\|"))
    app.add_handler(CallbackQueryHandler(send_material_file, pattern=r"^material\|"))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern=r"^check_sub_"))

    # Текст для никнейма (только когда step == nickname)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nickname_input))

    # Контакт (телефон)
    app.add_handler(MessageHandler(filters.CONTACT, phone_input))

    print("🤖 Бот запущен...")
    app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()

    


