import json
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from config import BOT_TOKEN, ALLOWED_CHAT_IDS, TARGET_URLS_FILE
from search import search_student
from parser import download_file, extract_pdf_links, extract_text_from_html

# Шаги диалога добавления источника
WAITING_URL, WAITING_TYPE_CONFIRM, WAITING_PDF_FILTER, \
WAITING_UNIVERSITY, WAITING_YEAR, WAITING_DESCRIPTION = range(6)


def load_sources() -> list:
    with open(TARGET_URLS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sources(sources: list):
    with open(TARGET_URLS_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)


def is_allowed(user_id: int) -> bool:
    return not ALLOWED_CHAT_IDS or user_id in ALLOWED_CHAT_IDS


# ---------- Обычные команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Команды:\n"
        "/add — добавить источник пошагово\n"
        "/sources — список источников\n"
        "/cancel — прервать диалог добавления\n\n"
        "Или просто отправь ФИО для поиска."
    )


async def list_sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return

    sources = load_sources()
    if not sources:
        await update.message.reply_text("📭 Список источников пуст")
        return

    response = "📚 Подключённые источники:\n\n"
    for i, s in enumerate(sources, 1):
        response += (
            f"{i}. **{s['university']}** ({s['year']})\n"
            f"   {s['description']}\n"
            f"   Тип: {s['type']}\n"
            f"   [URL]({s['url']})\n\n"
        )

    await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)


# ---------- Диалог /add ----------

async def add_source_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return ConversationHandler.END

    context.user_data.clear()

    await update.message.reply_text(
        "📥 Добавление источника\n\n"
        "Отправь URL страницы или PDF:\n"
        "(например: https://bseu.by/list.pdf)\n\n"
        "Для отмены: /cancel"
    )
    return WAITING_URL


async def add_source_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    context.user_data["url"] = url

    # 1) Очевидный PDF — по расширению
    if url.lower().endswith(".pdf"):
        context.user_data["type"] = "pdf"
        await update.message.reply_text("✅ Определён тип: PDF\nОтправь название вуза:")
        return WAITING_UNIVERSITY

    # 2) HTML-страница: анализируем содержимое
    await update.message.reply_text("⏳ Анализирую страницу...")
    try:
        html_bytes = download_file(url)
        extract_text_from_html(html_bytes)
        pdf_links = extract_pdf_links(html_bytes, url, max_links=20)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при анализе: {e}\nОтправь другой URL или /cancel")
        return WAITING_URL

    if len(pdf_links) >= 3:
        await update.message.reply_text(
            f"🔍 На странице найдено ссылок на PDF: {len(pdf_links)}.\n"
            "Это страница-оглавление со списками?\n\n"
            "Отправь 'y' (да) или 'n' (нет):"
        )
        return WAITING_TYPE_CONFIRM

    context.user_data["type"] = "html"
    await update.message.reply_text("✅ Определён тип: HTML (текст на странице)\nОтправь название вуза:")
    return WAITING_UNIVERSITY


async def add_source_type_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().lower()

    if answer in ("y", "yes", "д", "да"):
        context.user_data["type"] = "page_with_pdfs"
        await update.message.reply_text(
            "✅ Тип: page_with_pdfs\n\n"
            "Отправь фильтр для PDF (подстрока в URL, чтобы не качать левые файлы).\n"
            "Например: abiturient\n"
            "Или 'skip' — без фильтра:"
        )
        return WAITING_PDF_FILTER

    context.user_data["type"] = "html"
    await update.message.reply_text("✅ Тип: HTML\nОтправь название вуза:")
    return WAITING_UNIVERSITY


async def add_source_pdf_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pdf_filter = update.message.text.strip()
    if pdf_filter.lower() == "skip":
        pdf_filter = ""
    context.user_data["pdf_filter"] = pdf_filter
    await update.message.reply_text("✅ Фильтр сохранён\nОтправь название вуза:")
    return WAITING_UNIVERSITY


async def add_source_university(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["university"] = update.message.text.strip()
    await update.message.reply_text("Отправь год (например, 2026):")
    return WAITING_YEAR


async def add_source_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["year"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Год должен быть числом. Попробуй ещё раз:")
        return WAITING_YEAR

    await update.message.reply_text("Отправь описание (например, «Списки зачисленных на 1 курс»):")
    return WAITING_DESCRIPTION


async def add_source_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    description = update.message.text.strip()

    sources = load_sources()

    new_source = {
        "id": f"source_{len(sources) + 1}",
        "university": context.user_data["university"],
        "url": context.user_data["url"],
        "type": context.user_data["type"],
        "year": context.user_data["year"],
        "description": description,
    }
    if context.user_data["type"] == "page_with_pdfs":
        new_source["pdf_filter"] = context.user_data.get("pdf_filter", "")
        new_source["max_pdfs"] = 10

    sources.append(new_source)
    save_sources(sources)

    await update.message.reply_text(
        "✅ Источник добавлен:\n"
        f"{new_source['university']} ({new_source['year']})\n"
        f"{new_source['description']}\n"
        f"Тип: {new_source['type']}\n"
        f"URL: {new_source['url']}\n\n"
        "Теперь можно искать ФИО."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Диалог прерван", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ---------- Поиск ФИО ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не установлен в .env")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_source_start)],
        states={
            WAITING_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_url)],
            WAITING_TYPE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_type_confirm)],
            WAITING_PDF_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_pdf_filter)],
            WAITING_UNIVERSITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_university)],
            WAITING_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_year)],
            WAITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_description)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sources", list_sources))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()