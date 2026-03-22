# find_unknown.py
import sys
import json
from parsers_core.assoc_manager import get_assoc_manager

def main():
    if len(sys.argv) < 2:
        print("Использование: python find_unknown.py <имя_парсера> [путь_к_файлу]")
        sys.exit(1)
    
    parser_name = sys.argv[1]
    file_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Загрузка данных
    if file_path:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        # Или загрузите из стандартного места
        pass
    
    manager = get_assoc_manager()
    unknown = manager.find_unknown_products(parser_name, data.get('data', []))
    
    print(f"Найдено {len(unknown)} неизвестных товаров")
    
    # Сохранить в файл для ручной обработки
    if unknown:
        with open(f'unknown_{parser_name}.json', 'w', encoding='utf-8') as f:
            json.dump(unknown, f, ensure_ascii=False, indent=2)
        print(f"Сохранено в unknown_{parser_name}.json")

if __name__ == "__main__":
    main()