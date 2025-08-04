import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from user_data import users_data  # если у тебя есть отдельный файл с user-данными

def get_topic_keyboard(subject):
    path = os.path.join("materials", subject)
    if not os.path.exists(path):
        return None

    files = [
        f for f in os.listdir(path)
        if os.path.isfile(os.path.join(path, f)) and f.endswith((".pdf", ".docx", ".png", ".jpg"))
    ]

    buttons = [
        [InlineKeyboardButton(text=os.path.splitext(f)[0], callback_data=f"{subject}|{f}")]
        for f in files
    ]

    return InlineKeyboardMarkup(buttons)


async def send_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    user_subject = None

    for user in users_data.values():
        if user.get("username") == username:
            user_subject = user.get("subject")
            break

    if not user_subject:
        await update.message.reply_text("Ты пока не записан. Напиши /start.")
        return

    keyboard = get_topic_keyboard(user_subject)
    if keyboard:
        await update.message.reply_text(
            f"📚 Выбери тему по предмету: {user_subject}",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text("⚠️ Материалы по этому предмету пока не добавлены.")


async def handle_material_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        subject, filename = query.data.split("|")
        filepath = os.path.join("materials", subject, filename)

        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📘 Тема: {os.path.splitext(filename)[0]}"
                )
        else:
            await query.message.reply_text("Файл не найден.")
    except Exception as e:
        await query.message.reply_text(f"Ошибка при отправке файла: {e}")
