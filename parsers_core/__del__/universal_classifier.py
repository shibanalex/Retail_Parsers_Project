# C:\Retail Parsers\parsers_core\universal_classifier.py
"""
🎯 УНИВЕРСАЛЬНЫЙ КЛАССИФИКАТОР ДАННЫХ
Работает с любыми структурированными данными:
- Python списки/словари
- Pandas DataFrame
- Excel файлы
- SQLite/PostgreSQL результаты
- Горячий поток парсера
Версия 2.0 - универсальная обработка
"""

import pandas as pd
import os
import yaml
import sqlite3
from pathlib import Path
import warnings
import re
from typing import Dict, List, Any, Optional, Union, Tuple
import json
import numpy as np

warnings.filterwarnings('ignore')

class UniversalDataClassifier:
    """Универсальный классификатор для любых структурированных данных"""
    
    def __init__(self, rules_path: str = None, db_path: str = None):
        """
        Инициализация классификатора
        
        Args:
            rules_path: путь к файлу rules.yaml
            db_path: путь к базе данных associations.db
        """
        self.rules_path = rules_path or self._find_rules_path()
        self.db_path = db_path or self._find_db_path()
        
        print(f"🔍 Правила: {self.rules_path or 'Не найдены'}")
        print(f"🔍 База данных: {self.db_path or 'Не найдена'}")
        
        self._rules = None
        self._db_conn = None
    
    def _find_rules_path(self) -> Optional[str]:
        """Находит путь к файлу правил"""
        current_dir = os.getcwd()
        possible_paths = [
            os.path.join(current_dir, "_associations", "data", "rules.yaml"),
            os.path.join(current_dir, "Parsers", "_associations", "data", "rules.yaml"),
            "./_associations/data/rules.yaml",
            "../_associations/data/rules.yaml",
            "P:/_SrvShare_/rules.yaml",
            os.path.join(os.path.dirname(__file__), "..", "_associations", "data", "rules.yaml"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def _find_db_path(self) -> Optional[str]:
        """Находит путь к базе данных"""
        current_dir = os.getcwd()
        possible_paths = [
            os.path.join(current_dir, "_associations", "data", "associations.db"),
            os.path.join(current_dir, "Parsers", "_associations", "data", "associations.db"),
            "./_associations/data/associations.db",
            "../_associations/data/associations.db",
            "P:/__SrvShare_/associations.db",
            os.path.join(os.path.dirname(__file__), "..", "_associations", "data", "associations.db"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def detect_fields_smart(self, data: Any) -> Tuple[Optional[str], Optional[str]]:
        """
        УМНОЕ определение полей для названия и бренда в ЛЮБЫХ данных
        
        Поддерживает:
        - Список словарей
        - Pandas DataFrame
        - Единый словарь
        
        Returns:
            (name_field, brand_field) или (None, None) если не найдено
        """
        # Конвертируем данные в DataFrame для унификации
        df = self._convert_to_dataframe(data)
        if df is None or df.empty:
            return None, None
        
        # ПРИОРИТЕТНЫЕ ТОЧНЫЕ ИМЕНА ПОЛЕЙ
        NAME_PRIORITY = [
            'Название продукта', 'product_name', 'name', 'Название',
            'Товар', 'Наименование', 'Продукт', 'title', 'item_name'
        ]
        
        BRAND_PRIORITY = [
            'Бренд', 'brand', 'Производитель', 'manufacturer',
            'Марка', 'brand_name', 'производитель'
        ]
        
        # ПОЛЯ-ИСКЛЮЧЕНИЯ (НЕ МОГУТ быть названием товара)
        EXCLUDE_FIELDS = [
            'фото', 'photo', 'image', 'картинка', 'изображение',
            'ссылка', 'url', 'link', 'gtin', 'артикул', 'sku',
            'id', 'код', 'рейтинг', 'rating', 'цена', 'price',
            'остаток', 'stock', 'количество', 'объем', 'volume',
            'вес', 'weight', 'номер', 'number', 'адрес', 'address'
        ]
        
        # Шаг 1: ТОЧНЫЙ поиск по приоритетным именам
        for col in df.columns:
            col_name = str(col).strip().lower()
            
            # Проверяем точные совпадения для названия
            for priority_name in NAME_PRIORITY:
                if col_name == priority_name.lower():
                    name_field = col
                    print(f"✅ Найдено приоритетное поле названия: '{col}'")
                    
                    # Ищем бренд
                    for brand_col in df.columns:
                        brand_col_name = str(brand_col).strip().lower()
                        for priority_brand in BRAND_PRIORITY:
                            if brand_col_name == priority_brand.lower():
                                print(f"✅ Найдено приоритетное поле бренда: '{brand_col}'")
                                return name_field, brand_col
                    
                    return name_field, None
        
        # Шаг 2: Поиск по частичному совпадению (исключая запрещенные)
        for col in df.columns:
            col_name = str(col).strip().lower()
            
            # Пропускаем исключенные поля
            if any(exclude in col_name for exclude in EXCLUDE_FIELDS):
                continue
            
            # Проверяем на содержание ключевых слов названия
            if any(keyword in col_name for keyword in ['назван', 'name', 'товар', 'продукт']):
                # Проверяем содержимое поля
                try:
                    sample = df[col].dropna().head(3).astype(str).tolist()
                    if not sample:
                        continue
                    
                    # Проверяем, что это не ссылки/фото
                    is_url_or_photo = any(
                        re.search(r'(\.jpg|\.png|\.jpeg|\.webp|http://|https://)', s.lower())
                        for s in sample
                    )
                    
                    if not is_url_or_photo and len(sample[0]) > 5:
                        print(f"🔍 Выбрано поле названия: '{col}'")
                        print(f"   Пример: '{sample[0][:50]}...'")
                        
                        # Ищем бренд среди оставшихся полей
                        brand_field = self._find_brand_field(df, col, BRAND_PRIORITY)
                        return col, brand_field
                        
                except Exception:
                    continue
        
        # Шаг 3: Последняя попытка - первое неисключенное поле
        for col in df.columns:
            col_name = str(col).strip().lower()
            if not any(exclude in col_name for exclude in EXCLUDE_FIELDS):
                print(f"⚠️ Используем поле как название: '{col}'")
                brand_field = self._find_brand_field(df, col, BRAND_PRIORITY)
                return col, brand_field
        
        return None, None
    
    def _find_brand_field(self, df: pd.DataFrame, exclude_field: str, 
                         brand_priority: List[str]) -> Optional[str]:
        """Ищет поле для бренда"""
        for col in df.columns:
            if str(col).strip().lower() == str(exclude_field).strip().lower():
                continue
                
            col_name = str(col).strip().lower()
            
            # Проверяем приоритетные имена
            for priority_brand in brand_priority:
                if col_name == priority_brand.lower():
                    print(f"✅ Найдено поле бренда: '{col}'")
                    return col
            
            # Проверяем по содержимому
            if 'бренд' in col_name or 'brand' in col_name or 'марк' in col_name:
                print(f"🔍 Найдено вероятное поле бренда: '{col}'")
                return col
        
        return None
    
    def _convert_to_dataframe(self, data: Any) -> Optional[pd.DataFrame]:
        """
        Конвертирует ЛЮБЫЕ данные в DataFrame
        
        Поддерживает:
        - Список словарей
        - Единый словарь
        - Pandas DataFrame
        - Список списков
        - JSON строка
        """
        if data is None:
            return None
        
        # Если уже DataFrame
        if isinstance(data, pd.DataFrame):
            return data
        
        # Если список словарей
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return pd.DataFrame(data)
        
        # Если единый словарь
        if isinstance(data, dict):
            return pd.DataFrame([data])
        
        # Если список списков (с заголовками)
        if isinstance(data, list) and len(data) > 1 and isinstance(data[0], list):
            # Первый список - заголовки
            headers = data[0]
            rows = data[1:]
            return pd.DataFrame(rows, columns=headers)
        
        # Если JSON строка
        if isinstance(data, str):
            try:
                json_data = json.loads(data)
                return self._convert_to_dataframe(json_data)
            except:
                pass
        
        print(f"⚠️ Неподдерживаемый формат данных: {type(data)}")
        return None
    
    def normalize_brand(self, brand: Any) -> str:
        """Нормализует название бренда"""
        if not isinstance(brand, str):
            if brand is None or (isinstance(brand, float) and np.isnan(brand)):
                return ""
            return str(brand).strip()
        
        brand_str = str(brand).strip()
        if not brand_str or brand_str.lower() in ['nan', 'none', 'null', '']:
            return ""
        
        # Известные бренды для нормализации
        known_brands = {
            'домик в деревне': 'Домик в Деревне',
            'простоквашино': 'Простоквашино',
            'эконива': 'Эконива',
            'агуша': 'Агуша',
            'фрутоняня': 'ФрутоНяня',
            'правильное молоко': 'Правильное Молоко',
            'viola': 'Viola',
            'му-у': 'Му-У',
            'княгинино': 'Княгинино',
            'ополье': 'Ополье',
            'president': 'President',
            'natura': 'Natura',
            'метро': 'Метро',
            'spar': 'Spar',
            'дикси': 'Дикси',
            'smart': 'Smart',
            'maxi': 'Maxi',
            'перекресток': 'Перекресток',
            'ашан': 'Ашан',
            'лента': 'Лента',
            'магнит': 'Магнит',
        }
        
        brand_lower = brand_str.lower()
        if brand_lower in known_brands:
            return known_brands[brand_lower]
        
        # Общая нормализация регистра
        words = brand_lower.split()
        LOWERCASE_WORDS = {
            'в', 'и', 'с', 'у', 'о', 'на', 'под', 'за', 'по', 'из', 
            'от', 'до', 'без', 'для', 'к', 'со', 'не', 'ли', 'же'
        }
        
        result_words = []
        for i, word in enumerate(words):
            if i > 0 and word in LOWERCASE_WORDS:
                result_words.append(word)
            else:
                if word:
                    # Для иностранных слов/аббревиатур
                    if word.isupper() and len(word) > 1:
                        result_words.append(word)
                    else:
                        result_words.append(word[0].upper() + word[1:] if len(word) > 1 else word.upper())
        
        return ' '.join(result_words)
    
    def load_rules(self) -> Dict:
        """Загружает правила из YAML"""
        if self._rules is not None:
            return self._rules
        
        if not self.rules_path or not os.path.exists(self.rules_path):
            print("⚠️ Файл правил не найден, использую пустые правила")
            self._rules = {}
            return self._rules
        
        try:
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                self._rules = yaml.safe_load(f) or {}
            print(f"✅ Загружено правил: {len(self._rules)}")
        except Exception as e:
            print(f"❌ Ошибка загрузки правил: {e}")
            self._rules = {}
        
        return self._rules
    
    def get_db_connection(self) -> Optional[sqlite3.Connection]:
        """Возвращает соединение с БД"""
        if self._db_conn is None and self.db_path and os.path.exists(self.db_path):
            try:
                self._db_conn = sqlite3.connect(self.db_path)
                print(f"✅ Подключено к БД: {os.path.basename(self.db_path)}")
            except Exception as e:
                print(f"❌ Ошибка подключения к БД: {e}")
                self._db_conn = None
        
        return self._db_conn
    
    def classify_product(self, name: str, brand: str = "") -> Dict[str, Any]:
        """Классифицирует продукт"""
        if not name or not isinstance(name, str):
            return {'uni_cat': '', 'code_cat': 0, 'rule_id': '', 'confidence': 0.0}
        
        name_lower = name.lower()
        brand_lower = brand.lower() if brand else ""
        
        # 1. Пробуем найти в БД
        db_match = self._find_in_database(name_lower, brand_lower)
        if db_match:
            return db_match
        
        # 2. Применяем правила
        rule_match = self._apply_rules(name_lower, brand_lower)
        if rule_match:
            return rule_match
        
        return {'uni_cat': '', 'code_cat': 0, 'rule_id': '', 'confidence': 0.0}
    
    def _find_in_database(self, name_lower: str, brand_lower: str) -> Optional[Dict]:
        """Ищет в базе ассоциаций"""
        conn = self.get_db_connection()
        if not conn:
            return None
        
        try:
            cur = conn.cursor()
            
            # Поиск по названию
            cur.execute("""
                SELECT uni_cat, code_cat, rule_id, confidence 
                FROM associations 
                WHERE LOWER(name) LIKE ? 
                ORDER BY confidence DESC, updated DESC 
                LIMIT 1
            """, (f"%{name_lower}%",))
            
            row = cur.fetchone()
            if row:
                return {
                    'uni_cat': row[0] or '',
                    'code_cat': row[1] or 0,
                    'rule_id': row[2] or '',
                    'confidence': float(row[3]) if row[3] else 0.0
                }
            
        except Exception as e:
            print(f"⚠️ Ошибка поиска в БД: {e}")
        
        return None
    
    def _apply_rules(self, name_lower: str, brand_lower: str) -> Optional[Dict]:
        """Применяет правила из YAML"""
        rules = self.load_rules()
        
        best_match = None
        best_score = 0.0
        
        for rule_id, rule in rules.items():
            if not isinstance(rule, dict):
                continue
            
            # Проверяем активность
            if rule.get('active', True) is False:
                continue
            
            # Проверяем include слова
            include_words = rule.get('include', [])
            if not include_words:
                continue
            
            matches = 0
            for word in include_words:
                word_lower = str(word).lower()
                if word_lower in name_lower:
                    matches += 1
            
            if matches == 0:
                continue
            
            # Проверяем exclude слова
            exclude_words = rule.get('exclude', [])
            exclude_found = False
            for word in exclude_words:
                word_lower = str(word).lower()
                if word_lower in name_lower:
                    exclude_found = True
                    break
            
            if exclude_found:
                continue
            
            # Вычисляем score
            base_score = float(rule.get('base_score', 0.5))
            include_ratio = matches / len(include_words) if include_words else 0
            score = base_score * include_ratio
            
            if score > best_score:
                best_score = score
                best_match = {
                    'uni_cat': rule.get('uni_cat', ''),
                    'code_cat': int(rule.get('code_cat', 0)),
                    'rule_id': rule_id,
                    'confidence': min(float(score), 1.0)
                }
        
        return best_match
    
    def process_data(self, data: Any, 
                    name_field: str = None, 
                    brand_field: str = None) -> Any:
        """
        Обрабатывает ЛЮБЫЕ данные: классифицирует и нормализует
        
        Args:
            data: любые структурированные данные
            name_field: явное указание поля названия (если None - автоопределение)
            brand_field: явное указание поля бренда (если None - автоопределение)
        
        Returns:
            Обработанные данные в том же формате
        """
        print(f"\n🎯 ОБРАБОТКА ДАННЫХ")
        print(f"{'='*60}")
        
        # Конвертируем в DataFrame для обработки
        df = self._convert_to_dataframe(data)
        if df is None or df.empty:
            print("❌ Нет данных для обработки")
            return data
        
        print(f"📊 Записей для обработки: {len(df):,}")
        print(f"📋 Поля: {list(df.columns)}")
        
        # Определяем поля если не указаны
        if not name_field or not brand_field:
            detected_name, detected_brand = self.detect_fields_smart(df)
            
            if not name_field:
                name_field = detected_name
            
            if not brand_field:
                brand_field = detected_brand
        
        if not name_field:
            print("❌ Не удалось определить поле с названием товара")
            return data
        
        print(f"✅ Поле названия: '{name_field}'")
        print(f"✅ Поле бренда: '{brand_field or 'Нет'}'")
        
        # Добавляем поля категоризации если их нет
        for new_col in ['uni_cat', 'code_cat', 'rule_id', 'confidence']:
            if new_col not in df.columns:
                df[new_col] = ''
        
        # Обрабатываем каждую запись
        processed_count = 0
        normalized_brands = 0
        
        for idx in range(len(df)):
            try:
                name = str(df.at[idx, name_field]) if pd.notna(df.at[idx, name_field]) else ''
                brand = str(df.at[idx, brand_field]) if brand_field and pd.notna(df.at[idx, brand_field]) else ''
                
                if not name or name.lower() in ['nan', 'none', '']:
                    continue
                
                # Нормализуем бренд
                if brand and brand_field:
                    normalized_brand = self.normalize_brand(brand)
                    if normalized_brand != brand:
                        df.at[idx, brand_field] = normalized_brand
                        normalized_brands += 1
                    brand = normalized_brand
                
                # Классифицируем
                result = self.classify_product(name, brand)
                
                # Записываем результат
                df.at[idx, 'uni_cat'] = result.get('uni_cat', '')
                df.at[idx, 'code_cat'] = result.get('code_cat', 0)
                df.at[idx, 'rule_id'] = result.get('rule_id', '')
                df.at[idx, 'confidence'] = result.get('confidence', 0.0)
                
                processed_count += 1
                
                # Выводим примеры первых 3 классификаций
                if idx < 3 and result.get('uni_cat'):
                    print(f"\n📍 Пример обработки {idx+1}:")
                    print(f"   Товар: '{name[:40]}...'")
                    print(f"   Бренд: '{brand[:30] if brand else 'нет'}'")
                    print(f"   Категория: {result.get('uni_cat')}")
                    print(f"   Уверенность: {result.get('confidence'):.2f}")
                    
            except Exception as e:
                if idx < 3:
                    print(f"⚠️ Ошибка в строке {idx}: {e}")
                continue
        
        # Статистика
        print(f"\n📈 СТАТИСТИКА ОБРАБОТКИ:")
        print(f"   ✅ Обработано записей: {processed_count:,}/{len(df):,}")
        print(f"   🏷️  Нормализовано брендов: {normalized_brands:,}")
        
        if processed_count > 0:
            # Только заполненные категории
            filled_df = df[df['uni_cat'] != '']
            if not filled_df.empty:
                unique_cats = filled_df['uni_cat'].unique()
                print(f"   📊 Уникальных категорий: {len(unique_cats)}")
                
                if len(unique_cats) > 0:
                    print(f"   📋 Топ-5 категорий:")
                    cat_counts = filled_df['uni_cat'].value_counts().head(5)
                    for cat, count in cat_counts.items():
                        percentage = (count / processed_count) * 100
                        print(f"      • {cat}: {count:,} ({percentage:.1f}%)")
        
        print(f"{'='*60}")
        
        # Возвращаем данные в исходном формате
        return self._convert_to_original_format(data, df)
    
    def _convert_to_original_format(self, original_data: Any, processed_df: pd.DataFrame) -> Any:
        """
        Конвертирует обработанный DataFrame в исходный формат данных
        """
        # Если исходные данные были DataFrame
        if isinstance(original_data, pd.DataFrame):
            return processed_df
        
        # Если исходные данные были списком словарей
        if isinstance(original_data, list) and len(original_data) > 0 and isinstance(original_data[0], dict):
            return processed_df.to_dict('records')
        
        # Если исходные данные были словарем
        if isinstance(original_data, dict):
            return processed_df.iloc[0].to_dict()
        
        # Если список списков
        if isinstance(original_data, list) and len(original_data) > 1 and isinstance(original_data[0], list):
            # Добавляем новые колонки к заголовкам
            headers = original_data[0]
            headers.extend(['uni_cat', 'code_cat', 'rule_id', 'confidence'])
            
            # Собираем строки
            rows = []
            for idx in range(len(processed_df)):
                row = []
                for col in processed_df.columns:
                    if col in ['uni_cat', 'code_cat', 'rule_id', 'confidence']:
                        row.append(processed_df.at[idx, col])
                    elif col in headers:
                        row.append(processed_df.at[idx, col])
                rows.append(row)
            
            return [headers] + rows
        
        # По умолчанию возвращаем DataFrame
        return processed_df
    
    def process_excel_file(self, file_path: str, backup: bool = True) -> bool:
        """
        Обрабатывает Excel файл (удобная обертка)
        
        Args:
            file_path: путь к Excel файлу
            backup: создавать ли backup
        
        Returns:
            True если успешно
        """
        if not os.path.exists(file_path):
            print(f"❌ Файл не найден: {file_path}")
            return False
        
        print(f"📁 Обработка Excel файла: {Path(file_path).name}")
        
        try:
            # Создаем backup если нужно
            if backup:
                import shutil
                backup_path = file_path.replace('.xlsx', '_backup.xlsx')
                shutil.copy2(file_path, backup_path)
                print(f"✅ Backup создан: {Path(backup_path).name}")
            
            # Читаем файл
            xls = pd.ExcelFile(file_path)
            
            if len(xls.sheet_names) == 0:
                print("❌ Нет листов в файле")
                return False
            
            # Обрабатываем каждый лист
            for sheet in xls.sheet_names:
                print(f"\n📄 Лист: '{sheet}'")
                df = pd.read_excel(xls, sheet_name=sheet)
                
                # Обрабатываем данные
                processed_df = self.process_data(df)
                
                # Сохраняем обратно
                with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    processed_df.to_excel(writer, sheet_name=sheet, index=False)
            
            print(f"\n✅ Файл успешно обработан: {Path(file_path).name}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка обработки файла: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def close(self):
        """Закрывает соединения"""
        if self._db_conn:
            self._db_conn.close()
            self._db_conn = None


# ============================================
# ФАСАДНЫЕ ФУНКЦИИ ДЛЯ УДОБСТВА
# ============================================

def classify_data(data: Any, 
                 name_field: str = None, 
                 brand_field: str = None,
                 rules_path: str = None,
                 db_path: str = None) -> Any:
    """
    Классифицирует данные (главная функция)
    
    Args:
        data: любые структурированные данные
        name_field: поле названия (автоопределение если None)
        brand_field: поле бренда (автоопределение если None)
        rules_path: путь к rules.yaml
        db_path: путь к associations.db
    
    Returns:
        Обработанные данные
    """
    classifier = UniversalDataClassifier(rules_path, db_path)
    try:
        result = classifier.process_data(data, name_field, brand_field)
        return result
    finally:
        classifier.close()

def classify_hot_stream(parser_data: List[Dict], 
                       parser_name: str = "unknown") -> List[Dict]:
    """
    Специальная функция для обработки горячего потока парсера
    
    Args:
        parser_data: данные парсера (список словарей)
        parser_name: имя парсера для логов
    
    Returns:
        Обработанные данные
    """
    print(f"\n🔥 ОБРАБОТКА ГОРЯЧЕГО ПОТОКА: {parser_name}")
    print(f"📦 Входных записей: {len(parser_data)}")
    
    if not parser_data:
        print("⚠️ Нет данных для обработки")
        return parser_data
    
    # Обрабатываем данные
    processed_data = classify_data(parser_data)
    
    if isinstance(processed_data, list):
        print(f"✅ Обработано записей: {len(processed_data)}")
        
        # Анализируем результат
        categorized = sum(1 for item in processed_data if isinstance(item, dict) and item.get('uni_cat'))
        print(f"📊 Категоризировано: {categorized}/{len(processed_data)}")
        
        if categorized > 0:
            # Собираем статистику по категориям
            categories = {}
            for item in processed_data:
                if isinstance(item, dict):
                    cat = item.get('uni_cat')
                    if cat:
                        categories[cat] = categories.get(cat, 0) + 1
            
            print(f"🏷️ Уникальных категорий: {len(categories)}")
            for cat, count in list(categories.items())[:5]:
                print(f"   • {cat}: {count}")
    
    return processed_data

def classify_sql_result(data: Any, 
                       source_type: str = "sqlite") -> Any:
    """
    Обрабатывает результаты SQL запроса
    
    Args:
        data: результат SQL запроса
        source_type: 'sqlite' или 'postgresql'
    
    Returns:
        Обработанные данные
    """
    print(f"🗄️ ОБРАБОТКА РЕЗУЛЬТАТОВ SQL ({source_type.upper()})")
    
    # SQLite возвращает список кортежей или список словарей
    # PostgreSQL через psycopg2 возвращает список кортежей
    # Конвертируем в универсальный формат
    
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], tuple):
            # Конвертируем кортежи в словари
            # Нужно знать названия колонок - для простоты создаем общие
            column_names = [f'col_{i}' for i in range(len(data[0]))]
            dict_data = []
            for row in data:
                dict_row = {column_names[i]: row[i] for i in range(len(row))}
                dict_data.append(dict_row)
            
            print(f"📊 Конвертировано {len(data)} кортежей в словари")
            data = dict_data
    
    return classify_data(data)

# ============================================
# ИНТЕГРАЦИЯ С СУЩЕСТВУЮЩЕЙ СИСТЕМОЙ
# ============================================

def integrate_with_main():
    """
    Пример интеграции с main.py для обработки горячего потока
    """
    # В main.py после получения данных парсера:
    # from parsers_core.universal_classifier import classify_hot_stream
    #
    # if parser_data:
    #     parser_data = classify_hot_stream(parser_data, parser_name)
    
    pass


# ============================================
# ТЕСТИРОВАНИЕ
# ============================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Универсальный классификатор данных')
    parser.add_argument('--file', type=str, help='Обработать Excel файл')
    parser.add_argument('--json', type=str, help='Обработать JSON файл')
    parser.add_argument('--test', action='store_true', help='Запустить тест')
    parser.add_argument('--no-backup', action='store_true', help='Не создавать backup')
    
    args = parser.parse_args()
    
    print("🎯 УНИВЕРСАЛЬНЫЙ КЛАССИФИКАТОР ДАННЫХ")
    print("Версия 2.0 - обработка любых структурированных данных")
    print("=" * 60)
    
    if args.file:
        # Обработка Excel файла
        classifier = UniversalDataClassifier()
        try:
            success = classifier.process_excel_file(args.file, backup=not args.no_backup)
            if success:
                print(f"\n✅ Файл успешно обработан: {args.file}")
            else:
                print(f"\n❌ Ошибка обработки файла: {args.file}")
        finally:
            classifier.close()
    
    elif args.json:
        # Обработка JSON файла
        if not os.path.exists(args.json):
            print(f"❌ Файл не найден: {args.json}")
        else:
            import json
            with open(args.json, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            processed_data = classify_data(json_data)
            
            # Сохраняем результат
            output_file = args.json.replace('.json', '_processed.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(processed_data, f, ensure_ascii=False, indent=2)
            
            print(f"\n✅ Результат сохранен в: {output_file}")
    
    elif args.test:
        # Тестовый запуск
        print("🧪 ТЕСТОВЫЙ РЕЖИМ")
        
        # Тестовые данные (горячий поток парсера)
        test_data = [
            {
                'Название продукта': 'Молоко Домик в деревне пастеризованное 2.5%, 1.4л',
                'Бренд': 'ДОМИК В ДЕРЕВНЕ',
                'Цена': 154
            },
            {
                'Название продукта': 'Масло сливочное President 82%, 180г',
                'Бренд': 'PRESIDENT',
                'Цена': 344
            },
            {
                'Название продукта': 'Колбаса Докторская',
                'Бренд': 'Велком',
                'Цена': 289
            }
        ]
        
        print(f"\n📋 Тестовые данные ({len(test_data)} записей):")
        for item in test_data:
            print(f"  • {item['Название продукта'][:30]}...")
        
        # Обрабатываем
        processed = classify_hot_stream(test_data, "test_parser")
        
        print(f"\n📊 Результат обработки:")
        for i, item in enumerate(processed):
            if isinstance(item, dict):
                print(f"  {i+1}. {item.get('Название продукта', '')[:30]}...")
                print(f"     Бренд: {item.get('Бренд', 'нет')}")
                print(f"     Категория: {item.get('uni_cat', 'нет')}")
                print(f"     Уверенность: {item.get('confidence', 0):.2f}")
    
    else:
        print("🤔 РЕЖИМЫ РАБОТЫ:")
        print("  1. --file <путь>   - обработать Excel файл")
        print("  2. --json <путь>   - обработать JSON файл")
        print("  3. --test          - запустить тест")
        print("  4. --no-backup     - не создавать backup")
        print("\nПримеры:")
        print("  python universal_classifier.py --file ./output/data.xlsx")
        print("  python universal_classifier.py --json ./data.json")
        print("  python universal_classifier.py --test")