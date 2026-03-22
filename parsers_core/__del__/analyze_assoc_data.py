# analyze_assoc_data.py
"""
Утилита для анализа сохраненных данных ассоциаций
"""
import sys
import os
from pathlib import Path
import json

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from parsers_core.assoc_save_file import get_assoc_saver

def analyze_all_files():
    """Анализирует все сохраненные файлы"""
    saver = get_assoc_saver()
    
    print("🔍 Анализ сохраненных данных ассоциаций")
    print("=" * 60)
    
    # Файлы для обучения
    train_files = saver.list_training_files()
    print(f"\n📁 Файлы для обучения: {len(train_files)}")
    
    for filepath in train_files[-5:]:  # Последние 5 файлов
        info = saver.get_file_info(filepath)
        print(f"\n  📄 {Path(filepath).name}:")
        print(f"     • Парсер: {info.get('parser', 'unknown')}")
        print(f"     • Записей: {info.get('records', 0)}")
        print(f"     • Время: {info.get('timestamp', '')}")
        print(f"     • Размер: {info.get('file_size', 0) / 1024:.1f} KB")
    
    # Сырые файлы
    raw_files = saver.list_raw_files()
    print(f"\n📄 Сырые файлы: {len(raw_files)}")
    
    # Детальный анализ последнего файла
    if train_files:
        latest = train_files[-1]
        print(f"\n📊 Детальный анализ последнего файла: {Path(latest).name}")
        
        analysis = saver.analyze_data(latest)
        if analysis:
            print(f"   • Всего записей: {analysis.get('total_records', 0)}")
            print(f"   • Поля в данных:")
            for field, stats in analysis.get('fields', {}).items():
                print(f"     - {field}: {stats['count']} раз, типы: {', '.join(stats['types'])}")
            
            sample = analysis.get('sample_record', {})
            if sample:
                print(f"\n   🧪 Пример записи:")
                for key, value in list(sample.items())[:10]:  # Первые 10 полей
                    print(f"     • {key}: {value}")

def compare_parser_data(parser_name: str):
    """Сравнивает данные разных запусков одного парсера"""
    saver = get_assoc_saver()
    
    files = saver.list_training_files(parser_name)
    if not files:
        print(f"❌ Нет файлов для парсера '{parser_name}'")
        return
    
    print(f"\n📊 Сравнение данных для '{parser_name}':")
    print(f"   Найдено {len(files)} файлов")
    
    results = []
    for filepath in files[-3:]:  # Последние 3 файла
        data = saver.load_training_data(filepath)
        if data:
            results.append({
                "file": Path(filepath).name,
                "count": data.get("count", 0),
                "timestamp": data.get("timestamp", ""),
                "metadata": data.get("metadata", {})
            })
    
    for result in results:
        print(f"\n  📅 {result['timestamp']} ({result['file']}):")
        print(f"     • Записей: {result['count']}")
        meta = result.get('metadata', {})
        if 'cities' in meta:
            print(f"     • Города: {meta['cities']}")
        if 'search_requests' in meta:
            print(f"     • Запросы: {meta['search_requests']}")

if __name__ == "__main__":
    print("🔧 Утилита анализа данных ассоциаций")
    print("=" * 50)
    
    print("\n🎯 Варианты анализа:")
    print("  1. Общий анализ всех файлов")
    print("  2. Сравнение данных конкретного парсера")
    print("  3. Очистить старые файлы (старше 30 дней)")
    
    choice = input("\nВыберите действие (1-3): ").strip()
    
    saver = get_assoc_saver()
    
    if choice == "1":
        analyze_all_files()
        
    elif choice == "2":
        parser_name = input("Введите имя парсера: ").strip()
        if parser_name:
            compare_parser_data(parser_name)
        else:
            print("❌ Не указано имя парсера")
            
    elif choice == "3":
        confirm = input("Удалить файлы старше 30 дней? (y/N): ").strip().lower()
        if confirm == 'y':
            saver.clear_old_files(30)
            print("✅ Очистка завершена")
        else:
            print("❌ Отменено")
            
    else:
        print("❌ Неверный выбор")