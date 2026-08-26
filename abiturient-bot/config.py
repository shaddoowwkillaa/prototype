import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Whitelist пользователей
ALLOWED_CHAT_IDS = [int(x.strip()) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()]

# Пути
TARGET_URLS_FILE = "config/target_urls.json"
CACHE_DIR = "cache"
CACHE_TTL_HOURS = 1

# Поиск
CONTEXT_LENGTH = 200  # символов вокруг найденного ФИО