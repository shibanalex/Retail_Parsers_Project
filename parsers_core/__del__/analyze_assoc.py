# analyze_assoc.py
"""
Анализ сохраненных данных ассоциаций
Запуск: python analyze_assoc.py
"""
import sys
import os
from datetime import datetime
from pathlib import Path

#sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Добавляем путь к проекту
#project_root = Path(__file__).parent
#sys.path.insert(0, str(project_root))


#from .assoc_manager import get_assoc_manager
#from .assoc_save_file import get_assoc_saver
#assoc_saver = get_assoc_saver()
#import json
# Получаем текущую директорию и родительскую
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # c:\Retail Parsers

# Добавляем родительскую директорию в sys.path
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Теперь импортируем модули
try:
    # Пробуем импортировать как абсолютные импорты
    from parsers_core.assoc_manager import get_assoc_manager
    from parsers_core.assoc_save_file import get_assoc_saver
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print(f"   current_dir: {current_dir}")
    print(f"   parent_dir: {parent_dir}")
    print(f"   sys.path: {sys.path}")
    sys.exit(1)

# Создаем экземпляры
assoc_saver = get_assoc_saver()



def check_unknown_items(parser_name: str):
    """
    Проверяет неизвестные товары для парсера через базу ассоциаций
    Использует: assoc_saver (из parsers_core.assoc_save_file)
               и get_assoc_manager (из parsers_core.assoc_manager)
    """
    # Используем assoc_saver из глобальной области видимости
    files = assoc_saver.list_training_files(parser_name)
    if not files:
        print(f"❌ Нет файлов для парсера '{parser_name}'")
        return

    latest_file = files[-1]
    # Используем метод assoc_saver для загрузки данных
    data = assoc_saver.load_training_data(latest_file)

    if not data or 'data' not in data:
        print("❌ Не удалось загрузить данные")
        return

    print(f"\n🔍 Анализ неизвестных товаров для '{parser_name}':")
    print("=" * 60)

    # Используем менеджер ассоциаций из parsers_core.assoc_manager
    #from parsers_core.assoc_manager import get_assoc_manager
    assoc_manager = get_assoc_manager()

    # Используем метод assoc_manager.find_unknown_products
    unknown_items = assoc_manager.find_unknown_products(parser_name, data['data'])

    total_items = len(data['data'])
    known_items = total_items - len(unknown_items)

    print(f"📊 Статистика:")
    print(f"   • Всего товаров в файле: {total_items}")
    print(f"   • Уже в базе ассоциаций: {known_items}")
    print(f"   • Неизвестных товаров: {len(unknown_items)}")
    print(f"   • Файл: {Path(latest_file).name}")

    if unknown_items:
        print(f"\n📝 ПЕРВЫЕ 10 НЕИЗВЕСТНЫХ ТОВАРОВ:")
        for i, item in enumerate(unknown_items[:10], 1):
            prod_name = item.get('product_name', 'N/A')
            brand = item.get('brand', '')
            price = item.get('original', {}).get('Цена', '')

            # Обрезаем длинные названия
            display_name = prod_name
            if len(display_name) > 70:
                display_name = display_name[:67] + "..."

            print(f"\n   {i:2d}. {display_name}")
            if brand:
                print(f"       Бренд: {brand}")
            if price:
                print(f"       Цена: {price} руб")

        if len(unknown_items) > 10:
            print(f"\n   ... и еще {len(unknown_items) - 10} товаров")

        # Предлагаем добавить ассоциации
        print(f"\n{'=' * 60}")
        print(f"💾 ДОБАВЛЕНИЕ В БАЗУ АССОЦИАЦИЙ")
        print("=" * 60)
        print(f"   Добавить {len(unknown_items)} ассоциаций?")
        print("   y - добавить ВСЕ")
        print("   n - не добавлять (по умолчанию)")
        print("   s - статистика базы")
        print("=" * 60)

        choice = input("   Ваш выбор (y/n/s): ").strip().lower()

        if choice == 'y':
            # Используем метод assoc_manager.batch_add_associations
            added, skipped = assoc_manager.batch_add_associations(parser_name, unknown_items)
            print(f"\n✅ Результат добавления:")
            print(f"   • Успешно добавлено: {added} ассоциаций")
            print(f"   • Пропущено (дубли): {skipped}")

            # Показываем обновленную статистику через assoc_manager.get_statistics
            stats = assoc_manager.get_statistics(parser_name)
            print(f"   • Теперь в базе для '{parser_name}': {stats.get('total', 0)} ассоциаций")

        elif choice == 's':
            # Используем assoc_manager для получения статистики
            stats = assoc_manager.get_statistics(parser_name)
            print(f"\n📊 СТАТИСТИКА БАЗЫ ДЛЯ '{parser_name}':")
            print(f"   • Всего ассоциаций: {stats.get('total', 0)}")

            if stats.get('by_category'):
                print(f"   • По категориям:")
                for category, count in stats['by_category'].items():
                    print(f"     - {category}: {count}")

            # Снова предлагаем добавить
            print(f"\n💾 Добавить ассоциации после просмотра статистики? (y/n): ", end="")
            if input().strip().lower() == 'y':
                added, skipped = assoc_manager.batch_add_associations(parser_name, unknown_items)
                print(f"✅ Добавлено: {added}, Пропущено: {skipped}")

        else:
            print("ℹ️ Ассоциации не добавлены")

        # Сохраняем список неизвестных товаров в файл через assoc_saver
        if unknown_items:
            save_dir = Path("unknown_items")
            save_dir.mkdir(exist_ok=True)
            save_path = save_dir / f"unknown_{parser_name}_{Path(latest_file).stem}.txt"

            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(f"Неизвестные товары для парсера: {parser_name}\n")
                f.write(f"Дата анализа: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Всего товаров: {total_items}, Неизвестных: {len(unknown_items)}\n")
                f.write("=" * 80 + "\n\n")

                for i, item in enumerate(unknown_items, 1):
                    f.write(f"{i:4d}. {item.get('product_name', 'N/A')}\n")
                    if item.get('brand'):
                        f.write(f"     Бренд: {item.get('brand')}\n")
                    if item.get('original', {}).get('Цена'):
                        f.write(f"     Цена: {item.get('original', {}).get('Цена')} руб\n")
                    f.write("\n")

            print(f"\n💾 Список сохранен в файл: {save_path}")

    else:
        print("\n✅ Все товары уже есть в базе ассоциаций!")
        print("=" * 60)

        # Показываем статистику базы через assoc_manager
        stats = assoc_manager.get_statistics(parser_name)
        print(f"📊 Статистика базы для '{parser_name}':")
        print(f"   • Всего ассоциаций: {stats.get('total', 0)}")

        if stats.get('by_category'):
            print(f"   • По категориям:")
            for category, count in list(stats['by_category'].items())[:10]:
                print(f"     - {category}: {count}")
            if len(stats['by_category']) > 10:
                print(f"     ... и еще {len(stats['by_category']) - 10} категорий")
    pass

def main():
    print("🔍 Анализ сохраненных данных ассоциаций")
    print("=" * 60)

    # 1. Получаем список файлов
    files = assoc_saver.list_training_files()
    print(f"\n📁 Найдено {len(files)} файлов для обучения:")

    for i, filepath in enumerate(files[-10:], 1):
        info = assoc_saver.get_file_info(filepath)
        print(f"{i:2d}. {Path(filepath).name}")
        print(f"    • Парсер: {info.get('parser', 'unknown')}")
        print(f"    • Записей: {info.get('records', 0)}")
        print(f"    • Время: {info.get('timestamp', '')}")

    if not files:
        print("❌ Нет файлов для анализа")
        return

    # 2. Выбираем файл для анализа
    print("\n🎯 Выберите файл для анализа (номер) или Enter для последнего:")
    choice = input("> ").strip()

    if choice:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                file_to_analyze = files[idx]
            else:
                print("❌ Неверный номер, беру последний файл")
                file_to_analyze = files[-1]
        except ValueError:
            print("❌ Введите число, беру последний файл")
            file_to_analyze = files[-1]
    else:
        file_to_analyze = files[-1]

    # 3. Анализируем выбранный файл
    print(f"\n📊 Анализ файла: {Path(file_to_analyze).name}")
    analysis = assoc_saver.analyze_data(file_to_analyze)

    if not analysis:
        print("❌ Не удалось проанализировать файл")
        return

    print(f"   • Всего записей: {analysis.get('total_records', 0)}")

    fields = analysis.get('fields', {})
    if fields:
        print(f"\n   📋 Поля в данных:")
        for field, stats in fields.items():
            print(f"     - {field}: встречается {stats['count']} раз")
            print(f"       Типы значений: {', '.join(stats['types'])}")

    # 4. Показываем пример записи
    sample = analysis.get('sample_record', {})
    if sample:
        print(f"\n   🧪 Пример записи (первые 10 полей):")
        for i, (key, value) in enumerate(list(sample.items())[:10], 1):
            value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
            print(f"     {i:2d}. {key}: {value_str}")

    # 5. Загружаем полные данные для глубокого анализа
    print(f"\n📈 Детальный анализ:")
    full_data = assoc_saver.load_training_data(file_to_analyze)
    if full_data:
        metadata = full_data.get('metadata', {})
        parser_name = full_data.get('parser_name', 'unknown')
        print(f"   • Парсер: {parser_name}")
        print(f"   • Retail ID: {metadata.get('retail_id', 'не указан')}")
        print(f"   • Города: {metadata.get('cities', 'не указано')}")
        print(f"   • Запросы поиска: {metadata.get('search_requests', 'не указано')}")
        print(f"   • Данных для ассоциаций: {metadata.get('assoc_input_count', 'не указано')}")

        # Анализ категорий если есть
        data_records = full_data.get('data', [])
        if data_records:
            categories = {}
            for record in data_records:
                cat = record.get('retail_cat') or record.get('category') or record.get('Категория')
                if cat:
                    categories[cat] = categories.get(cat, 0) + 1

            if categories:
                print(f"\n   🏷️ Категории товаров:")
                for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"     • {cat}: {count}")

    # 6. ################### ВОТ СЮДА ДОБАВЬТЕ ПРОВЕРКУ С assoc_manager ###################
    print("\n" + "=" * 60)
    print("🔍 ПРОВЕРКА НЕИЗВЕСТНЫХ ТОВАРОВ (БАЗА АССОЦИАЦИЙ)")
    print("=" * 60)

    # Инициализируем менеджер ассоциаций
    manager = get_assoc_manager()

    if full_data and 'data' in full_data:
        parser_name = full_data.get('parser_name', 'unknown')
        data_records = full_data.get('data', [])

        # Находим товары, которых нет в базе ассоциаций
        unknown_products = manager.find_unknown_products(parser_name, data_records)

        print(f"   • Всего товаров в файле: {len(data_records)}")
        print(f"   • Уже в базе ассоциаций: {len(data_records) - len(unknown_products)}")
        print(f"   • Неизвестных товаров: {len(unknown_products)}")

        if unknown_products:
            print(f"\n📝 ПЕРВЫЕ 10 НЕИЗВЕСТНЫХ ТОВАРОВ:")
            for i, product in enumerate(unknown_products[:10], 1):
                prod_name = product.get('product_name', 'N/A')
                brand = product.get('brand', '')
                price = product.get('original', {}).get('Цена', '')

                # Обрезаем длинные названия
                if len(prod_name) > 70:
                    prod_name = prod_name[:67] + "..."

                print(f"   {i:2d}. {prod_name}")
                if brand:
                    print(f"       Бренд: {brand}")
                if price:
                    print(f"       Цена: {price} руб")

            if len(unknown_products) > 10:
                print(f"   ... и еще {len(unknown_products) - 10} товаров")

            # Предлагаем добавить ассоциации
            print(f"\n{'=' * 60}")
            print(f"💾 Добавить {len(unknown_products)} ассоциаций в базу?")
            print("   y - добавить ВСЕ")
            print("   n - не добавлять (по умолчанию)")
            print("   p - предпросмотр всех")
            print(f"{'=' * 60}")
            choice = input("Ваш выбор (y/n/p): ").strip().lower()

            if choice == 'y':
                # Добавляем все
                added, skipped = manager.batch_add_associations(parser_name, unknown_products)
                print(f"\n✅ Результат:")
                print(f"   • Добавлено: {added} ассоциаций")
                print(f"   • Пропущено (дубли): {skipped}")

                # Показываем обновленную статистику
                stats = manager.get_statistics(parser_name)
                print(f"   • Теперь в базе для '{parser_name}': {stats.get('total', 0)} ассоциаций")

            elif choice == 'p':
                # Показать все товары с пагинацией
                page_size = 20
                total_pages = (len(unknown_products) + page_size - 1) // page_size

                for page in range(total_pages):
                    start_idx = page * page_size
                    end_idx = min(start_idx + page_size, len(unknown_products))

                    print(f"\n📄 Страница {page + 1}/{total_pages} "
                          f"(товары {start_idx + 1}-{end_idx}):")

                    for i, product in enumerate(unknown_products[start_idx:end_idx], start_idx + 1):
                        print(f"{i:4d}. {product.get('product_name', 'N/A')}")

                    if page < total_pages - 1:
                        print("\nПоказать следующую страницу? (Enter - продолжить, q - выйти): ", end="")
                        if input().strip().lower() == 'q':
                            break

                print(f"\n💾 Добавить все {len(unknown_products)} ассоциаций? (y/n): ", end="")
                if input().strip().lower() == 'y':
                    added, skipped = manager.batch_add_associations(parser_name, unknown_products)
                    print(f"✅ Добавлено: {added}, Пропущено: {skipped}")

            else:
                print("ℹ️ Ассоциации не добавлены")

        else:
            print("✅ Все товары уже есть в базе ассоциаций!")

    # 7. Показываем статистику базы
    print(f"\n{'=' * 60}")
    print("📊 СТАТИСТИКА БАЗЫ АССОЦИАЦИЙ")
    print("=" * 60)

    stats = manager.get_statistics()
    print(f"   • Всего ассоциаций в базе: {stats.get('total', 0)}")

    if stats.get('by_parser'):
        print(f"   • По парсерам:")
        for parser, count in sorted(stats['by_parser'].items()):
            print(f"     - {parser}: {count}")
    pass

if __name__ == "__main__":
    # Для быстрого анализа конкретного парсера
    import sys
    
    if len(sys.argv) > 1:
        parser_name = sys.argv[1]
        check_unknown_items(parser_name)
    else:
        main()
