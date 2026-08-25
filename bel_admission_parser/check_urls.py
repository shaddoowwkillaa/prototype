import json

def check_target_urls():
    try:
        with open("config/target_urls.json", "r", encoding="utf-8") as f:
            urls = json.load(f)
        
        print(f"✅ Файл валиден! Всего добавлено ссылок: {len(urls)}")
        
        # Проверка на дубликаты
        unique_urls = set(urls)
        if len(urls) != len(unique_urls):
            duplicates = len(urls) - len(unique_urls)
            print(f"⚠️ Найдено дубликатов ссылок: {duplicates}")
        else:
            print("✨ Дубликатов не обнаружено.")

        # Вывод первых и последних 3 ссылок для контроля
        print("\nПервые 3 ссылки:", urls[:3])
        print("Последние 3 ссылки:", urls[-3:])

    except json.JSONDecodeError as e:
        print(f"❌ Ошибка в синтаксисе JSON! Проверьте запятые и скобки:\n{e}")
    except FileNotFoundError:
        print("❌ Файл config/target_urls.json не найден. Проверьте путь.")

if __name__ == "__main__":
    check_target_urls()