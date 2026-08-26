import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, ALLOWED_CHAT_IDS, TARGET_URLS_FILE
from search import search_student

def load_sources() -> list:
    """Загружает список источников из JSON"""
    with open(TARGET_URLS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def is_allowed(user_id: int) -> bool:
    """Проверяет, есть ли пользователь в whitelist"""
    return not ALLOWED_CHAT_IDS or user_id in ALLOWED_CHAT_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Отправь мне полное ФИО студента (например, 'Мироевский Сергей Николаевич'), "
        "и я поищу его в списках зачисленных."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    full_name = update.message.text.strip()
    
    if len(full_name) < 5:
        await update.message.reply_text("❌ Слишком короткое ФИО")
        return
    
    await update.message.reply_text(f"⏳ Ищу '{full_name}' в списках...")
    
    sources = load_sources()
    results = search_student(full_name, sources)
    
    if not results:
        await update.message.reply_text("❌ Не найден ни в одном источнике")
        return
    
    response = f"✅ Найдено совпадений: {len(results)}\n\n"
    
    for i, result in enumerate(results, 1):
        response += (
            f"{i}. **{result['university']}** ({result['year']})\n"
            f"   {result['description']}\n"
            f"   Специальность: {result['specialty']}\n"
            f"   [Источник]({result['source_url']})\n"
        )
        if result["file_url"] != result["source_url"]:
            response += f"   📄 [Файл списка PDF]({result['file_url']})\n"
        response += "\n"
    
    await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не установлен в .env")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()