import time
import sys
import os

# Добавляем текущую папку в пути, чтобы внутренние импорты пакета работали
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from magazinoff_pkg.collector import run_collection

def main():
    start = time.time()
    print("🚀 Запуск модуля Magazinnoff внутри архитектуры...")
    
    # Запускаем сбор
    try:
        all_data = run_collection()
        finish = time.time()
        print(f"✅ Модуль Magazinnoff завершил работу за {(finish - start) / 60:.2f} мин.")
        return all_data
    except Exception as e:
        print(f"❌ Ошибка в magazinnoff.main: {e}")
        return []

if __name__ == "__main__":
    main()