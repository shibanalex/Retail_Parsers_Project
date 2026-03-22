import time
import sys
import os

# Добавляем путь к текущей папке, чтобы Python видел внутренние пакеты
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from cataloged_pkg.crawler import run_collection

def main():
    start = time.time()
    print("🚀 Запуск парсера Cataloged.ru...")
    
    try:
        all_data = run_collection()
        finish = time.time()
        print(f"✅ Cataloged завершен. Время: {(finish - start) / 60:.2f} мин. Собрано: {len(all_data)} товаров.")
        return all_data
    except Exception as e:
        print(f"❌ Критическая ошибка Cataloged: {e}")
        return []

if __name__ == "__main__":
    main()