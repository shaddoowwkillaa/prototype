import json
import sys
from parser import get_documents_from_source

def preload_all_sources():
    """Скачивает все источники в кэш заранее"""
    try:
        with open("config/target_urls.json", "r", encoding="utf-8") as f:
            sources = json.load(f)
    except FileNotFoundError:
        print("❌ Файл config/target_urls.json не найден")
        return
    
    print(f"📥 Начинаю загрузку {len(sources)} источников...\n")
    
    total_docs = 0
    total_chars = 0
    errors = 0
    
    for i, source in enumerate(sources, 1):
        print(f"[{i}/{len(sources)}] {source['university']}")
        print(f"   URL: {source['url']}")
        print(f"   Тип: {source['type']}")
        
        try:
            docs = get_documents_from_source(source)
            total_text = sum(len(d["text"]) for d in docs)
            total_docs += len(docs)
            total_chars += total_text
            print(f"   ✅ Загружено документов: {len(docs)}, символов: {total_text}\n")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}\n")
            errors += 1
    
    print("=" * 60)
    print(f"✨ Готово!")
    print(f"   Всего источников: {len(sources)}")
    print(f"   Загружено документов: {total_docs}")
    print(f"   Всего символов: {total_chars}")
    print(f"   Ошибок: {errors}")
    print(f"\nКэш заполнен на 1 час. Бот будет искать мгновенно.")

if __name__ == "__main__":
    preload_all_sources()